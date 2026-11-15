"""Shared project inventory, Git operations, and workspace file writes."""
import json
import os
from pathlib import Path
import tempfile

from .policy import PolicyError, discover, safe_path
from .process import run


def inventory(project):
    project = Path(project).resolve()
    is_git = (project / '.git').exists()
    if is_git:
        names = git(project, 'ls-files', '-z').split('\0')
    else:
        names = [str(p.relative_to(project)) for p in project.rglob('*') if p.is_file()]
    allowed = []
    for name in sorted(set(filter(None, names))):
        try:
            safe_path(name)
        except PolicyError:
            continue
        if name.startswith(('xp-coding-agent-plan', 'eval-results/')):
            continue
        allowed.append(name)
    if len(allowed) > 3000:
        raise PolicyError('Repository inventory exceeds 3000 files; use a smaller project root')
    return allowed, is_git


def require_safe_checkout(project):
    private_attributes = Path(git(project, 'rev-parse', '--git-path', 'info/attributes').strip())
    if not private_attributes.is_absolute():
        private_attributes = Path(project) / private_attributes
    if private_attributes.exists() or private_attributes.is_symlink():
        raise PolicyError('Private Git attributes require a separately validated workspace profile')
    for attr in git(project, 'ls-files', '-z').split('\0'):
        if attr and Path(attr).name == '.gitattributes' and 'filter' in git(
                project, 'show', 'HEAD:' + attr):
            raise PolicyError(
                'Git checkout filters require a separately validated workspace profile')


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
    env['TMPDIR'] = '/private/tmp' if Path('/private/tmp').exists() else tempfile.gettempdir()
    env.update(GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0',
               GIT_ATTR_NOSYSTEM='1')
    result = run([
        'git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c',
        'core.attributesFile=/dev/null', '-c', 'commit.gpgsign=false', '-c', 'user.name=XP Agent',
        '-c', 'user.email=xp-agent@localhost', *args
    ],
                 cwd=root,
                 env=env,
                 timeout=15)
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


def reconcile_workspace(workspace, before, after):
    # Private snapshot only. Never overwrite unexplained human edits or symlinks.
    names = []
    for path in workspace.rglob('*'):
        if '.git' in path.relative_to(workspace).parts:
            continue
        if path.is_symlink():
            raise PolicyError('Workspace contains a symlink')
        if path.is_file():
            names.append(path.relative_to(workspace).as_posix())
    current = discover(workspace, names) if names else {}
    if current not in (before, after):
        raise PolicyError('Workspace changed externally; reconcile before continuing')
    write_files(workspace, after)
