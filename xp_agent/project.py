"""Reviewable grants and disposable snapshot repositories, without copying history."""
import json
import os
from pathlib import Path
import tempfile
import uuid
from .policy import PolicyError, discover, digest, safe_path, check_content
from .process import run


def create_plan(project, task, source_paths, test_paths, backend, *, read_paths=(), budget=600, attempts=2, image='xp-agent-tests:0.1'):
    project = Path(project).resolve()
    if not source_paths or not test_paths or set(source_paths) & set(test_paths):
        raise PolicyError('Select disjoint source and test paths')
    if not 1 <= attempts <= 5 or not 1 <= budget <= 3600:
        raise PolicyError('Limits: 1..5 attempts per phase; 1..3600 seconds')
    check_content(task)
    paths = set(source_paths + test_paths + list(read_paths))
    for path in list(paths):
        safe_path(path)
        for parent in (Path(path).parent, *Path(path).parent.parents):
            for name in ('AGENTS.md', 'README.md', 'CONTRIBUTING.md'):
                relative = str(parent / name)
                if (project / relative).exists():
                    paths.add(relative)
    existing = sorted(p for p in paths if (project / p).exists() or (project / p).is_symlink())
    if not set(source_paths).issubset(existing):
        raise PolicyError('Source files must exist; select a small existing behavior')
    files = discover(project, existing)
    proposal = backend.propose('plan', {'task': task, 'source_paths': source_paths, 'test_paths': test_paths, 'files': files}, min(budget, 180))
    if proposal.get('blocked'):
        raise PolicyError(proposal['blocked'])
    if proposal.get('edits') or not proposal.get('acceptance') or not proposal.get('tradeoffs'):
        raise PolicyError('Plan must include acceptance and tradeoffs, with no edits')
    plan = dict(version=1, project=str(project), task=task, model=backend.model,
                source_paths=source_paths, test_paths=test_paths, read_paths=existing,
                missing_paths=sorted(paths - set(existing)), files=files,
                acceptance=proposal['acceptance'], tradeoffs=proposal['tradeoffs'],
                rationale=proposal['rationale'], max_attempts=attempts,
                budget_seconds=budget, image=image,
                milestones=['Meaningful red', 'Smallest green implementation', 'Refactor and verify'])
    plan['approval_id'] = digest(plan)
    return plan


def verify_approval(plan, approval_id):
    body = {k: v for k, v in plan.items() if k != 'approval_id'}
    if digest(body) != approval_id or plan.get('approval_id') != approval_id:
        raise PolicyError('Approval does not match the exact plan')
    if discover(Path(plan['project']), plan['read_paths']) != plan['files'] or any(
            (Path(plan['project']) / p).exists() for p in plan['missing_paths']):
        raise PolicyError('Project changed since discovery; generate a fresh plan')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def git(root, *args):
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    result = run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                  '-c', 'user.name=XP Agent', '-c', 'user.email=xp-agent@localhost', *args],
                 cwd=root, env=env, timeout=15)
    if result.returncode:
        raise PolicyError('Git operation failed: ' + result.stdout[-500:])
    return result.stdout


def write_files(root, files):
    for name, content in files.items():
        safe_path(name)
        path = root / name
        # Workspace is controller-owned and never mounted writable into a worker.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def make_workspace(run_dir, files):
    root = Path(run_dir) / 'workspace'
    root.mkdir(parents=True, mode=0o700)
    write_files(root, files)
    git(root, 'init', '--template=', '-b', 'xp/' + uuid.uuid4().hex[:12])
    git(root, 'add', '--', *files)
    git(root, 'commit', '-m', 'Baseline: explicitly selected project snapshot')
    return root


def render_plan(plan):
    bullets = lambda values: '\n'.join('- ' + v for v in values)
    return f'''# Initial review plan

Task: {plan['task']}

## Acceptance criteria

{bullets(plan['acceptance'])}

## Discovery and scope

Read: {', '.join(plan['read_paths'])}
Source edits: {', '.join(plan['source_paths'])}
Test edits: {', '.join(plan['test_paths'])}
Model: {plan['model']}; image: {plan['image']}
Limits: {plan['max_attempts']} attempts per phase; {plan['budget_seconds']} seconds total.
Only the selected snapshot is copied. Original files are never modified.

## Alternatives and tradeoffs

{bullets(plan['tradeoffs'])}

{plan['rationale']}

## Layer map

| Layer | Component / operation | Status |
|---|---|---|
| Product | Selected source files | MODIFIED |
| Specification | Behavior tests / assertions | MODIFIED or NEW |
| Controller | plan, approve, red, green, refactor, final | UNCHANGED |
| Backend | propose bounded file contents | UNCHANGED |
| Isolation | network-disabled pytest container | UNCHANGED |

## Runtime and trust boundaries

```mermaid
flowchart TD
    H[Human approves this plan] --> C[Trusted controller]
    C --> M[Hosted model proposes edits; no project execution]
    M --> V[Controller validates phase and paths]
    V --> T[Restricted container executes tests]
    T --> G{{XP gate}}
    G -->|Within-budget repair| M
    G -->|Verified| N[Next approved phase]
    G -->|Unsafe or blocked| H
    N --> R[Final branch, diff and evidence]
```

## Implementation increments

{bullets(plan['milestones'])}

Verification: baseline pytest, new assertion failure on unchanged source, all tests green,
refactoring with accepted tests immutable, final independent regression run.
No merge, push, deployment, dependency changes, or additional provider disclosure is authorized.
Review semantic correctness; automated evidence cannot prove business intent or resist arbitrary malicious tests.

Approval ID: `{plan['approval_id']}`
'''
