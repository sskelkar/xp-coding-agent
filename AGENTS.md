# Working on XP Coding Agent

This is a learning project and a bounded Python/pytest coding prototype. On this branch the default interface is the outcome-led two-partner flow; explicit `repl`, `plan` and `run` retain the legacy single-agent paths. Read `docs/pair-runtime.md` before changing pair behavior. Preserve a working CLI after each small increment. These instructions apply to the whole repository.

## Read first

1. `README.md`: installation, user workflow, contributor commands and current limitations.
2. `docs/how-it-works.md`: Python entry points, LangGraph nodes/state and module responsibilities.
3. `docs/roadmap.md`: agreed milestone direction, delivered work and the next bounded stories.
4. `docs/providers.md` and `docs/security.md`: adapter, credential and execution boundaries.
5. `docs/evaluation.md`: what has actually been verified, including live-provider gaps.

The public roadmap is the handoff source. Ignored machine-local planning/review notes are historical context, not required inputs. Do not treat the entire roadmap as authorization to implement it. Use the user's current request to choose scope; don't restart completed milestones.

## Development discipline

- Use red–green–refactor for behavior changes and bug fixes: first demonstrate a meaningful failing test, implement the smallest passing change, then refactor. Import errors alone are not behavioral red evidence. Documentation-only corrections need accurate review rather than artificial tests.
- Keep initial planning concise but explicit about scope, acceptance, tradeoffs and verification. After authorization, handle routine implementation and test failures autonomously within scope. Ask only for genuine ambiguity, blockers or unsafe/unapproved actions.
- Preserve existing uncommitted changes. Do not commit, push, merge or deploy unless the user authorizes that action.
- Keep the README and walkthrough accurate to implemented behavior. Put future capabilities in the roadmap, clearly marked as future. Record meaningful validation results without publishing raw source-bearing run output.

## Commands

```sh
uv sync --frozen
uv run pytest
docker build -f Dockerfile.tests -t xp-agent-tests:0.1 .
XP_DOCKER_TESTS=1 uv run pytest
uv build
```

Use `uv run xp-agent --help` for CLI options. Live evals make hosted requests and use account quota; use only synthetic fixtures and an authorized provider/account. The deterministic suite does not need credentials. Runtime dependencies and dev tools are declared in `pyproject.toml` and locked in `uv.lock`; use the project `.venv`.

## Invariants to preserve

- The controller, not a model, approves edits and phase transitions. Meaningful red precedes green. Accepted tests cannot be modified in green/refactor under the current policy.
- Pair greenfield bootstrap is an explicit exception before behavioral red: append source scaffolding without changing existing AST statements or tests, independently verify an assertion failure with prior regressions passing, then enter green. Never count a missing-symbol error or a zero-test run as behavioral red.
- Models return bounded structured proposals. Only the controller writes the accepted checkout; tests run through the restricted Docker runner, never on the host.
- Provider/model/auth mode belong to the confirmed outcome/session (or the approved legacy plan). Never silently fall back to another provider, inherit unapproved transport settings, or put credentials into prompts, plans, reports or Git.
- `verified` means automated gates passed, not human product acceptance. Record failures and rejected candidates honestly. Do not mark a partial run complete.
- The legacy `checkpoint` callback is a JSON-save callback, not a durable LangGraph checkpointer. Pair sessions use SQLite LangGraph checkpoints and explicit conversation replay; neither design promises exactly-once external model calls. Interactive session continuation reconciles saved files/approval and preserves remaining budgets; extend it without blind side-effect replay.
- Keep one controller writer. The pair graph owns all handoffs; A-red/B-green then B-red/A-green. Separate identities and continuing histories must not be reset per turn. Context compaction and guarded test-interface evolution remain unimplemented.
- Preserve original project files. Legacy interactive Git runs use approved linked worktrees; batch/non-Git and the initial pair runtime use independent snapshots. Preserve that distinction and never integrate automatically.

Never add employer/project identifiers, personal machine paths, real profiles, credentials or local run artifacts to public documentation. Use generic projects and synthetic examples.
