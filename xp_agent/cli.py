"""Two-step human approval: plan first; execute only an exact reviewed grant."""
import argparse
import json
from pathlib import Path
import sys
from .backend import create_backend
from .policy import PolicyError
from .process import run
from .project import create_plan, verify_approval, write_json, render_plan, make_workspace, write_files, git
from .sandbox import DockerRunner
from .workflow import execute
from .reporting import render_report, source_divergence


def heartbeat(seconds):
    print(f'  Worker active for {seconds:.0f}s; waiting for verified evidence', file=sys.stderr, flush=True)


def perform_run(plan, output, backend=None):
    output = Path(output).resolve()
    if output.exists():
        raise PolicyError('Output already exists; use a new run directory to preserve existing work')
    output.mkdir(parents=True, mode=0o700)
    write_json(output / 'approved-plan.json', plan)
    (output / 'plan.md').write_text(render_plan(plan))
    root = make_workspace(output, plan['files'])
    backend = backend or create_backend(plan.get('provider', 'codex'), plan['model'], plan.get('auth', 'cli'), status=heartbeat)
    runner = DockerRunner(plan['image'], scratch=output / 'scratch', status=heartbeat)
    previous = None

    def checkpoint(state):
        nonlocal previous
        write_files(root, state['files'])
        write_json(output / 'state.json', state)
        phase = state.get('phase', 'baseline')
        if phase != previous:
            print(f'Phase: {phase}; status: {state["status"]}', file=sys.stderr, flush=True)
            previous = phase
        with (output / 'events.jsonl').open('a') as f:
            f.write(json.dumps({'phase': phase, 'status': state['status'], 'attempts': state['attempts'],
                                'evidence_count': len(state['evidence'])}) + '\n')

    state = execute(plan, backend, runner, checkpoint)
    git(root, 'add', '--', *state['files'])
    diff = git(root, 'diff', '--cached', '--no-ext-diff', '--no-textconv', '--binary')
    (output / 'changes.patch').write_text(diff)
    if state['status'] == 'verified' and diff:
        git(root, 'commit', '-m', 'Implement approved behavior through red-green-refactor')
    branch = git(root, 'branch', '--show-current').strip()
    divergence = source_divergence(plan)
    write_json(output / 'divergence.json', divergence)
    summary = render_report(plan, state, branch, divergence)
    (output / 'result.md').write_text(summary)
    print(summary)
    print(f'Results: {output}')
    return 0 if state['status'] == 'verified' else 2


def backend_arguments(parser):
    parser.add_argument('--provider', choices=('codex', 'claude'), default=None)
    parser.add_argument('--model', help='Provider model ID or alias; default: gpt-6-luna for codex, haiku for claude')
    parser.add_argument('--auth', choices=('cli', 'api-key', 'oauth-token'), default=None,
                        help='Saved CLI credentials (default), provider API key, or Claude OAuth token environment variable')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local XP agent: approve once, execute verified red/green/refactor phases.')
    commands = parser.add_subparsers(dest='command', required=True)
    plan_cmd = commands.add_parser('plan', help='Discover selected files and write a reviewable plan; no project execution')
    plan_cmd.add_argument('project', type=Path)
    plan_cmd.add_argument('--task', required=True)
    plan_cmd.add_argument('--source', nargs='+', required=True)
    plan_cmd.add_argument('--tests', nargs='+', required=True)
    plan_cmd.add_argument('--read', nargs='*', default=[])
    backend_arguments(plan_cmd)
    plan_cmd.add_argument('--image', default='xp-agent-tests:0.1')
    plan_cmd.add_argument('--budget', type=int, default=600)
    plan_cmd.add_argument('--attempts', type=int, default=2)
    plan_cmd.add_argument('--output', type=Path, default=Path('.xp-runs/plan.json'))
    run_cmd = commands.add_parser('run', help='Execute an exact approved plan in a new branch/snapshot')
    run_cmd.add_argument('plan', type=Path)
    run_cmd.add_argument('--approve', required=True, help='Full approval ID printed in plan.md')
    run_cmd.add_argument('--output', type=Path, required=True)
    eval_cmd = commands.add_parser('eval', help='Disposable fixture evals; no credentials needed unless --live')
    eval_cmd.add_argument('--live', action='store_true', help='Use selected provider on synthetic code')
    backend_arguments(eval_cmd)
    eval_cmd.add_argument('--output', type=Path, default=Path('eval-results/latest.json'))
    repl_cmd = commands.add_parser('repl', help='Interactive coding shell (default when no subcommand is supplied)')
    repl_cmd.add_argument('project', nargs='?', type=Path, default=Path.cwd())
    backend_arguments(repl_cmd)
    repl_cmd.add_argument('--budget', type=int, default=600)
    repl_cmd.add_argument('--attempts', type=int, default=2)
    actual = list(sys.argv[1:] if argv is None else argv)
    if not actual or actual[0] not in {'plan','run','eval','repl','-h','--help'}:
        actual.insert(0, 'repl')
    args = parser.parse_args(actual)
    try:
        if args.command == 'repl':
            from .repl import shell
            return shell(args.project,provider=args.provider,model=args.model,auth=args.auth,budget=args.budget,attempts=args.attempts)
        if args.command == 'plan':
            if args.output.exists():
                raise PolicyError('Plan output exists; choose a new output path')
            image = run(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}'], timeout=10)
            if image.returncode:
                raise PolicyError('Build Dockerfile.tests first; image is unavailable')
            plan = create_plan(args.project, args.task, args.source, args.tests, create_backend(args.provider or 'codex', args.model, args.auth or 'cli', status=heartbeat),
                               read_paths=args.read, budget=args.budget, attempts=args.attempts, image=image.stdout.strip())
            write_json(args.output, plan)
            markdown = args.output.with_suffix('.md')
            markdown.write_text(render_plan(plan))
            print(f'Review {markdown}\nApproval ID: {plan["approval_id"]}')
            return 0
        if args.command == 'run':
            plan = json.loads(args.plan.read_text())
            verify_approval(plan, args.approve)
            return perform_run(plan, args.output)
        from .evals import evaluate
        report = evaluate(live=args.live, model=args.model, provider=args.provider or 'codex', auth=args.auth or 'cli')
        write_json(args.output, report)
        print(json.dumps(report, indent=2))
        return 0 if report['passed'] else 2
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f'Blocked: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Cancelled. Existing artifacts are preserved.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
