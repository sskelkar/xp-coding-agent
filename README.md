# XP Coding Agent

Two model partners work on a small Python project through test-driven development. You confirm the desired outcome. The partners discuss the next behavior, write a failing test and implement it, then swap roles. You can clarify requirements and accept the result after seeing a working demo.

Choose **OpenAI Codex** or **Anthropic Claude Code** for each session. Both partners use the selected provider and model, with separate identities and continuing histories. Provider choice applies to the whole pair. [Provider setup and verification](docs/providers.md)

## Install and run

Use Python 3.11 or newer, uv, Git, a running Docker engine, and either the Codex or Claude Code CLI on your PATH. From this checkout, install dependencies and build the test image.

```sh
uv sync --frozen
docker build -f Dockerfile.tests -t xp-agent-tests:0.1 .
```

Sign in to your selected provider CLI. Then pass a small Python project directory or try a new module in an empty folder.

```sh
toy_project=$(mktemp -d "$HOME/xp-agent-demo.XXXXXX")
uv run --frozen xp-agent pair "$toy_project" --provider codex --auth cli \
  --goal 'Implement slugify(text) in slug.py for ASCII input. Lowercase letters, replace runs of non-alphanumeric characters with one hyphen, and trim leading and trailing hyphens. For example, "Hello, World!" becomes "hello-world".'
```

To use Claude Code, select `--provider claude --auth cli` after signing in to Claude. Use `--model` to select a model supported by your account. [Sign-in commands and API key options](docs/providers.md#use-either-provider)

At the first prompt, type `confirm` or clarify the outcome. At a demo, type `accept`, `continue`, or explain what should change. The agent prints the private session directory. Accepted changes are committed in that session's `workspace/`, with a `changes.patch` for manual integration.

```sh
uv run xp-agent pair --resume /path/to/pair-session
uv run xp-agent pair --help
```

Defaults are Codex with `gpt-6-luna` and saved CLI login, 900 active seconds, two attempts per coding phase, up to 12 cycles, and a demo after two completed cycles. For a demo after the first completed cycle, pass `--demo-every 1`. The agent works on small, trusted Python/pytest projects with prepared dependencies. [All settings, session artifacts, and troubleshooting](docs/pair-runtime.md) · [Security boundaries](docs/security.md)

Both `xp-agent` and `xp-coding-agent` launch pairing by default. To use them outside the checkout, install with `uv tool install --editable .` and run the command from your target project.

## Source layout

| Location | Responsibility |
| --- | --- |
| [xp_agent/cli.py](xp_agent/cli.py) | Dispatches pairing and evaluation commands. |
| [xp_agent/pairing/](xp_agent/pairing/) | Interactive session, LangGraph role rotation, test gates, partner history, and demos. |
| [xp_agent/providers/](xp_agent/providers/) | Codex and Claude transports, model selection, and authentication. |
| [xp_agent/evaluation/pair/](xp_agent/evaluation/pair/) | Production graph probes, evidence grading, scripted Money scenario, and independent acceptance. |
| [xp_agent/tracing/](xp_agent/tracing/) | Bounded metadata capture and local Langfuse export. |
| [xp_agent/workspace.py](xp_agent/workspace.py), [policy.py](xp_agent/policy.py), [sandbox.py](xp_agent/sandbox.py), [process.py](xp_agent/process.py) | Shared file, Git, edit, Docker, and subprocess boundaries. |
| [tests/](tests/) | Tests grouped by subsystem. |
| [evals/fixtures/](evals/fixtures/) | Data fixtures for evaluation. |

See [how it works](docs/how-it-works.md) for a source walkthrough and [architecture](docs/architecture.md) for component boundaries.

## Verify changes

```sh
uv run --frozen pytest
XP_DOCKER_TESTS=1 uv run --frozen --extra tracing pytest
uv run --frozen xp-agent eval --output eval-results/pair.json
uv build
```

The default evaluation uses scripted partners and real Docker execution. It checks graph routing, grades the recorded transitions, and runs 33 independent Money acceptance checks. `--live` uses the chosen hosted provider and consumes quota. See [evaluation commands](docs/pair-evaluations.md) and [recorded results](docs/evaluation.md).

Tracing is off by default. Add `--trace` to pairing or evaluation after configuring [local Langfuse](docs/tracing.md). For the managed cloud setup, see [environment instructions](environment/README.md).
