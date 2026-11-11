"""Evaluation-only entry point; it never launches a coding agent or live model."""
import argparse
import json
from pathlib import Path
from .contracts import grade_contract
from .scenarios import catalog
from .money import evaluate_money, STAGES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('catalog', help='List business scenarios and unrun runtime checks')
    grade = commands.add_parser('grade', help='Grade offline controller evidence, not its authenticity')
    grade.add_argument('evidence', type=Path)
    money = commands.add_parser('money', help='Run independent acceptance in Docker, never on the host')
    money.add_argument('candidate', type=Path)
    money.add_argument('--stage', choices=STAGES, default='multiplication')
    for command in (grade, money):
        command.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'catalog':
            report = catalog()
        elif args.command == 'grade':
            if args.evidence.stat().st_size > 4_000_000:
                raise ValueError('Evidence exceeds 4 MB')
            report = grade_contract(json.loads(args.evidence.read_text()))
        else:
            report = evaluate_money(args.candidate, stage=args.stage)
        text = json.dumps(report, indent=2)
        if getattr(args, 'output', None):
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            args.output.write_text(text + '\n')
        print(text)
        return 0 if args.command == 'catalog' or report.get('passed') is True else 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'status': 'blocked', 'passed': False,
                          'runtime_verified': False, 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
