# XP Coding Agent

A local Python/LangGraph agent that implements one small approved behavior through **red → green → refactor**, using Codex for bounded proposals and Docker for independent tests.

Milestone 1 is a constrained prototype for trusted, small Python/pytest projects. It is not a general-purpose coding agent or a company-security certification. Finance Simulator and company repositories have not been used in its evals.

## Requirements and setup

- Python 3.11+, Git, [uv](https://docs.astral.sh/uv/), a working Docker engine (Docker Desktop or Colima), and the Codex CLI for model-backed runs.
- Use your existing `codex login` session. **Do not put API keys in source files or paste them into chat.** This version uses the CLI's saved sign-in; it does not require an API key.
- Local orchestration does not mean local inference: selected task/code context is sent to the configured hosted provider.

```sh
uv sync --frozen
docker build -f Dockerfile.tests -t xp-agent-tests:0.1 .
uv run xp-agent --help
```

The `.venv` is local to this checkout. `uv run` uses it automatically. The lockfile is checked in; environments and runtime records are not.

## Run the evals first

```sh
uv run pytest
XP_DOCKER_TESTS=1 uv run pytest
uv run xp-agent eval --output eval-results/scripted.json
# Optional: uses your Codex sign-in and account allowance on synthetic code.
uv run xp-agent eval --live --model gpt-6-luna --output eval-results/live.json
```

The deterministic evals supply scripted proposals but execute **real pytest containers**. They test success, premature green, invalid red, path escape, test weakening, ambiguity, and refactoring regression. A held-out acceptance test checks unseen numeric inputs outside model context. Live evals use the same gates with an actual model; availability varies by account. There is no silent model fallback.

## Plan, review once, then execute

The bundled fixture is deliberately incomplete and already has a passing baseline test.

```sh
uv run xp-agent plan evals/fixtures/counter \
  --task 'Make double return twice any integer or float, preserving zero.' \
  --source calc.py --tests test_calc.py \
  --model gpt-6-luna --output .xp-runs/double-plan.json
```

Read `.xp-runs/double-plan.md`. It contains acceptance criteria, source guidance, scope, tradeoffs, a layer map, runtime diagram, increments, permissions and budgets. The JSON is the exact grant, including the selected files, model and container image ID. Explicit `--read` paths can add task-relevant documents. Applicable README/AGENTS/CONTRIBUTING files within the project are discovered automatically along selected path ancestors; the agent does not read your entire filesystem or follow every documentation link.

```sh
uv run xp-agent run .xp-runs/double-plan.json \
  --approve FULL_APPROVAL_ID_FROM_THE_PLAN \
  --output .xp-runs/double-run
```

The agent proceeds without routine human prompts. Stale source files or a changed plan invalidate approval. It stops on unresolved ambiguity, phase/scope violations after bounded retries, infrastructure failures, cancellation, or exhausted limits.

Outputs:

- `workspace/`: a dedicated `xp/...` branch in an **independent snapshot Git repository**, with only explicitly selected files. It is not a linked worktree and does not inherit project history, hooks, remotes, or credentials.
- `changes.patch`: reviewable diff against the selected baseline. No automatic application to the original repository, push, merge, or deployment.
- `state.json`: meaningful red, green, refactor and final test reports tied to code hashes; preserved last accepted state on failure.
- `events.jsonl`, `approved-plan.json`, `result.md`: local decisions/progress/result evidence. Keep these private; they may contain source code and test output.

Review the patch and behavior before integrating. The original project is never changed. Failed candidate edits are discarded; accepted red tests or verified implementation remain available. Do not delete a run directory until you have retained any needed changes. Resume and feedback-driven continuation are later milestones.

## What is enforced

- Models propose complete file contents; they never receive the writable project checkout.
- Red may only append new assertion-based top-level test functions. Existing test/setup AST statements are preserved. Syntax/collection/setup errors and skipped tests do not count as meaningful red. At least one new assertion must fail while existing tests pass.
- Green may only edit declared source files; accepted tests cannot change. Target and baseline test identities must remain present and passing.
- Refactor may improve source code or record a no-change rationale; tests remain immutable in this milestone. Behavior/test refactoring beyond this restriction needs later controls.
- Every candidate and final result is tested separately from the model. The graph promotes only validated candidates. Final green means automated checks passed, not human product acceptance.
- Deadlines and output limits are enforced by the parent process even when a worker is silent. Ctrl-C kills the worker process group and removes the owned test container. Cleanup failures are surfaced.

See [architecture](docs/architecture.md), [security boundaries](docs/security.md), and [evaluation notes](docs/evaluation.md).

## Current limits

One behavior increment per run; Python files; pytest-only execution with the prepared image. No automatic package installation, arbitrary shell commands, external services, UI/browser automation, provider switching, pairing, or crash resume. Relevant non-code files can be read but cannot be edited. Source files must already exist; tests may be added at explicitly approved paths.

Known-pattern secret checks are only a precaution. Generated code and pytest share a process inside the container, so malicious tests can forge or manipulate reports; AST preservation is not proof that a test measures the intended behavior. Start with trusted toy projects. The live-model check is a smoke test, not a statistical quality benchmark.
