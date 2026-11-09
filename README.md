# XP Coding Agent

A local interactive coding agent for small Python/pytest projects. Describe a goal, review the plan, and type `approve`. The controller runs **red → green → refactor** for each approved increment, verifies tests in Docker, and delivers a reviewable Git branch and evidence.

The model proposes code; the controller validates edits, runs tests and decides whether a phase passed. Codex and Claude Code use the same workflow. This is a learning project and a bounded prototype, not a claim of production readiness.

## Install

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Git, a running Docker engine, and the selected provider CLI on `PATH`. macOS and Linux are supported.

From this repository:

```sh
uv sync --frozen
docker build -f Dockerfile.tests -t xp-agent-tests:0.1 .
uv tool install --editable .
```

The tool install places `xp-coding-agent` and the shorter alias `xp-agent` in uv's executable directory. If the command is unavailable, run `uv tool update-shell`, then open a new terminal. The editable installation uses this checkout; keep it in place. Development/test dependencies remain in the project's `.venv`.

Authenticate locally with your selected provider:

```sh
codex login
# Or Claude, using your authorized account/organization:
claude auth login
# Explicit enterprise SSO where required:
claude auth login --sso
```

See [provider configuration](docs/providers.md) for API keys, Claude OAuth tokens and account limitations. Credentials never belong in tasks, plans, Git or chat.

## Use the interactive shell

```sh
cd /absolute/path/to/your-project
xp-coding-agent
```

A typical session:

```text
xp> Make whitespace normalization collapse runs to one space and strip the ends.
Discovery round 1: ...
[Task, acceptance criteria, selected edit scope, increments and tradeoffs]
Review the plan. Type approve to execute ...: approve
Increment 1/2: ...
  BASELINE: accepted; ...
  RED: accepted; ... assertion failures ...
  GREEN: accepted; ... passed ...
  REFACTOR: accepted; ...
  FINAL: accepted; ...
Session verified. Review .../result.md; workspace: .../workspace
xp> /quit
```

Actual increments and test counts depend on the task. The shell displays your provider/model/auth mode before discovery. It reads project guidance and asks the model which relevant files to inspect. You do not need to supply source/test lists. `/hint path/to/module` provides an optional starting point; it is not a complete dependency declaration.

The controller inventories tracked files in a Git project. It captures safe text files for test execution, while sending selected guidance/source/test context to the model. It excludes sensitive paths, known secret patterns, symlinks, oversized/non-text files and untracked files. Review the runtime/disclosure/edit scopes in the plan; exclusions may make some projects unsupported. This version limits the safe runtime snapshot to 400KB, inventory to 3000 paths and discovery to six rounds. It is intended for small toy projects.

A rejected plan executes nothing. Enter a clarification or corrected goal to replan; `/new` clears pending context. After approval, routine XP phases proceed automatically. Genuine blockers, invalid provider responses, exhausted limits or unavailable prerequisites stop the run. The REPL remains available for inspection or continuation. No merge, push or deployment occurs.

### Shell commands

| Command | Purpose |
|---|---|
| Plain-language text | Plan a new goal, or clarify the pending goal |
| `approve` at the review prompt | Execute the displayed plan; the exact approval ID is recorded internally |
| `/hint PATH` | Add an optional discovery starting point |
| `/provider claude haiku cli` | Select and save defaults for new plans |
| `/provider claude sonnet oauth-token` | Select Claude Sonnet with an explicitly exported OAuth token |
| `/provider codex gpt-6-luna cli` | Select Codex with saved CLI authentication |
| `/trace on`, `/trace off` | Enable/disable optional local metadata tracing |
| `/status` | Display the latest session location and selected provider |
| `/resume` | Continue the latest session in this shell |
| `/resume /absolute/path/to/session` | Select a saved session after restarting the shell |
| `/new` | Clear the pending goal and discovery hints |
| `/help`, `/quit` | Help or exit |

You can also set startup defaults with `xp-coding-agent --provider claude --model haiku --auth cli`. Saved preferences contain provider/model/auth mode and the tracing preference only. They are stored alongside the session directory and do not contain credentials. Default provider is Codex (`gpt-6-luna`); Claude defaults to `haiku`. There is no silent provider fallback.

### Workspace and review

Git projects require a clean **tracked** baseline. The agent refuses tracked edits rather than stashing, resetting or committing your existing work. Untracked/ignored files remain in your original checkout and are excluded from the run. Tracked checkout-filter attributes and private Git attributes require a separately validated profile and are refused here; system/global attribute files are disabled for controller Git commands. Repositories and their Git configuration must still be trusted.

An approved Git task creates a linked worktree on a new `xp/...` branch at the approved commit. The original checkout remains on its branch. The controller writes accepted changes in the worktree; tests receive a separate filtered, read-only snapshot in an unprivileged network-disabled container. The worktree itself is not a sandbox.

Successful interactive runs commit their approved changes on that branch. After human review, use your normal merge/cherry-pick process, project checks and CI to integrate it. Blocked/cancelled runs retain partial accepted work. Do not remove a worktree containing work you need.

Non-Git projects use the original independent snapshot repository strategy. The explicit batch API also retains snapshot execution. It delivers a patch for manual integration.

### Records and continuation

Records default to `$XDG_STATE_HOME/xp-coding-agent/sessions/`, or `~/.local/state/xp-coding-agent/sessions/` when that variable is unset. Every run prints its location.

| Artifact | Contents |
|---|---|
| `plan.md`, `approved-plan.json` | Preserved agreement, scopes, provider, limits and increments |
| `session.json` | Checksummed session record, accepted files, increment position, current phase and remaining budgets |
| `workspace/` | Linked worktree or independent snapshot checkout |
| `state.json`, `changes.patch` | Aggregate final/partial evidence and diff against the session baseline |
| `result.md`, `divergence.json` | Accepted work, rejected attempts, pending human acceptance and selected-original-file divergence |

`/resume` checks the approval, record checksum, workspace branch/revision and accepted file content. It checks completed commit identity and edits outside scope, including excluded tracked/index files, and refuses changed/unrecorded files and preserves attempts and remaining execution time. It can resume a phase interrupted by cancellation or an external failure when budget remains, or continue between completed increments. An attempt started before cancellation still counts. Exhausted budgets require a new plan; resuming does not replenish them.

This uses explicit application state and graph entry routing, not a LangGraph durable checkpointer or exact model conversation replay. Material scope/provider changes require a new plan; there is no automatic amendment or semantic feedback revision of an existing grant. Human acceptance remains pending even when automated gates say `verified`.

Abrupt process termination or filesystem failures can leave incomplete artifacts; saved state must reconcile before continuation. Model requests are fresh per phase, and inference is hosted. Check account/provider authorization before disclosing code. Claude has adapter contract coverage but still needs a successful authenticated live cycle in your configuration.

## Optional local Langfuse tracing

Tracing is off by default. It records model-call timings, controller decisions, test counts, artifact hashes and deterministic TDD scores; source, prompts, task text and test output are excluded. Install the optional SDK with `uv sync --frozen --extra tracing` (or `uv tool install --editable '.[tracing]' --force` for the global executable), configure a local Langfuse project at `http://127.0.0.1:4000`, then start `xp-coding-agent --trace` or enter `/trace on`.

[Local tracing and experiments](docs/tracing.md) explains keys, safe metadata, failure behavior and the SDK experiment command. Ordinary coding/evals work without Langfuse. Export errors warn without changing the coding result. Local ingestion, score retrieval and the experiment UI have been verified with synthetic fixtures; see [evaluation evidence](docs/evaluation.md).

## Understand and enhance the project

- [Product walkthrough](docs/product-guide.md): the user journey, complete workflow diagrams, how code gets written, your choices, and what gets delivered.
- [How it works](docs/how-it-works.md): Python entry points, REPL/session execution, LangGraph nodes/state and storage.
- [Testing and eval walkthrough](docs/how-it-works.md#walkthrough-testing-the-agent-and-evaluating-its-output): follow unit tests through REPL/Docker/live evals.
- [Architecture](docs/architecture.md): layers, workflow and decisions.
- [Provider configuration](docs/providers.md): models, credentials and switching.
- [Security boundaries](docs/security.md): implemented controls and limits.
- [AGENTS.md](AGENTS.md): contributor discipline and reading order.
- [Milestone handoff](docs/roadmap.md): implemented capabilities and future work. MCP remains deferred.

The shell uses `repl.py` and `session.py`; both providers implement the same adapter contract. The session controller discovers context, records approval, prepares a workspace and runs the LangGraph XP cycle for each increment. The existing edit policy, Docker runner and subprocess supervisor enforce the execution boundaries. An accepted red test fails by assertion while old tests pass; accepted tests are frozen during implementation/refactoring.

## Develop and evaluate

```sh
uv sync --frozen
uv run pytest
XP_DOCKER_TESTS=1 uv run pytest
uv run xp-agent eval --output eval-results/scripted.json
uv build
```

Normal tests need no credentials; Docker integration tests require the prepared image. Evals retain seven adversarial controller scenarios and add the primary REPL path: discovery, in-shell approval/rejection, linked worktree, progress, independent acceptance and original-checkout preservation. Unit tests additionally cover multiple increments, cancellation/restart continuation and refusal to resume changed files.

Live evals now enter through the REPL too:

```sh
uv run xp-agent eval --live --provider codex --auth cli --output eval-results/codex.json
uv run xp-agent eval --live --provider claude --model haiku --auth cli --output eval-results/claude.json
```

Choose the authentication mode you configured. Live evals use synthetic fixtures and consume the selected account's quota. Controlled model responses establish transport/controller behavior, not live model quality. See [evaluation evidence](docs/evaluation.md).

For dependency changes, use `uv add PACKAGE` or `uv add --dev PACKAGE`, then review `pyproject.toml` and `uv.lock`. Rebuild the image after changing `Dockerfile.tests`; host `.venv` dependencies are separate from the test image. Add a meaningful failing behavior test, implement to green, refactor, and update docs. CI installs locked dependencies, builds Docker and runs the full deterministic suite without model credentials.

The batch `plan`, `run` and `eval` subcommands remain available for automation. [Batch reference](docs/batch-reference.md) documents the explicit-file interface; ordinary interactive use does not require those flags.

## Practical limits

Python/pytest only; existing source files (new test files are allowed); small safe-text snapshots; prepared dependencies; trusted non-sensitive projects. No arbitrary host shell execution, dependency provisioning, service setup, browser tests, pairing or MCP. Core checks cannot prove assertion strength or business intent; malicious project code can manipulate the pytest reporter inside its container. A local CLI and enterprise login alone do not establish production security compliance.

Known local artifacts, logs, credential state and runtime records are ignored by Git. Custom outputs and Git metadata still require review; private AI notes are not covered by `.gitignore`. Publish the intended branch explicitly and review staged content. Secret scanning is incomplete.
