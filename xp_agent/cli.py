"""Dispatch interactive pair sessions and evaluation runs."""

import argparse
import json
from pathlib import Path
import sys

from .workspace import write_json


def _command_parser():
    parser = argparse.ArgumentParser(description="Outcome-led XP pair programming.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pair", help="Start or resume a session with two XP partners")
    evaluation = commands.add_parser("eval", help="Run pair graph and Money acceptance checks")
    evaluation.add_argument("--pair", action="store_true", help=argparse.SUPPRESS)
    evaluation.add_argument("--live",
                            action="store_true",
                            help="Use a hosted provider on synthetic code")
    evaluation.add_argument("--provider", choices=("codex", "claude"), default="codex")
    evaluation.add_argument("--model", help="Model ID or provider alias")
    evaluation.add_argument("--auth", choices=("cli", "api-key", "oauth-token"), default="cli")
    evaluation.add_argument("--trace", action=argparse.BooleanOptionalAction, default=False)
    evaluation.add_argument("--output", type=Path, default=Path("eval-results/latest.json"))
    return parser


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = arguments[0] if arguments else None
    if command in {"plan", "run", "repl"}:
        print("Pairing is the only coding workflow. Use xp-agent pair or xp-agent eval.",
              file=sys.stderr)
        return 2

    if command not in {"eval", "-h", "--help"}:
        from .pairing.cli import main as pair_main

        return pair_main(arguments[1:] if command == "pair" else arguments)

    args = _command_parser().parse_args(arguments)
    from .evaluation.pair.runtime import evaluate

    try:
        report = evaluate(
            args.output,
            live=args.live,
            provider=args.provider,
            model=args.model,
            auth=args.auth,
            trace=args.trace,
        )
        write_json(args.output, report)
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 2
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"Blocked: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled. Existing artifacts are preserved.", file=sys.stderr)
        return 130
