# Local tracing and deterministic experiments

Tracing is optional and off by default. It sends bounded metadata to **http://127.0.0.1:4000** only. It does not upload source code, task text, prompts, replies, filenames, test names, command output, exception text or credentials. Hosted inference through the selected Codex/Claude CLI is a separate boundary; local tracing does not make inference local.

## Install and configure

Install the optional SDK in the agent checkout:

```sh
uv sync --frozen --extra tracing
# For the globally available editable executable:
uv tool install --editable '.[tracing]' --force
```

This installs Langfuse Python SDK 5.1.0 into the relevant isolated environment. `uv sync --frozen` alone does not install the extra. Contributor CI includes it so SDK contract tests cannot silently skip.

Run a local Langfuse v4 deployment exposed only on loopback at port 4000. An existing local deployment can serve a separate XP project; this repository neither starts nor stops another application's stack. For a new installation, follow the [official Docker Compose instructions](https://langfuse.com/self-hosting/deployment/docker-compose), keep credentials outside Git, and bind the web port to `127.0.0.1:4000` rather than all interfaces. Langfuse's database/worker services are observability infrastructure; the separate `Dockerfile.tests` image is the agent's test sandbox. Local hardware/storage still have a cost.

Create an **XP Coding Agent** project and project API keys in the local UI. Set those keys in the terminal from which you launch the agent. Do not reuse another project's keys implicitly or paste keys into a chat/task:

```sh
read -s LANGFUSE_PUBLIC_KEY
export LANGFUSE_PUBLIC_KEY
read -s LANGFUSE_SECRET_KEY
export LANGFUSE_SECRET_KEY
```

These commands are for a zsh/bash terminal. Enter the requested value at each hidden prompt. This project does not load `.env` files. Credentials are read only when an export or experiment is requested; they do not enter plans, reports, prompts or test containers.

The destination is deliberately fixed. `LANGFUSE_HOST`, `LANGFUSE_BASE_URL`, ambient OpenTelemetry exporter settings and proxy variables cannot redirect this integration. Remote/cloud/custom-endpoint tracing is unsupported. The exporter disables HTTP redirects and environment proxies and uses its own OpenTelemetry provider in a separate process.

## Trace a coding session

From a target project:

```sh
xp-coding-agent --trace
```

Or enter `/trace on` in the REPL; `/trace off` disables subsequent operations. The preference persists alongside provider/model/auth preferences, without credentials. `--no-trace` overrides the preference for that shell invocation. Changing tracing does not change an approved coding grant.

The plan attempt and approved execution have separate traces grouped by an opaque session ID. The plan trace includes the human review prompt; its total wall time includes that wait. Model and test child durations measure their own calls. Rejection records a rejected plan and executes nothing. Resume creates another execution trace with the same session ID and a prior-trace reference when available; it does not replay earlier side effects or replenish budgets.

Batch `plan`, `run` and `eval` also accept `--trace` / `--no-trace`. Batch plan/run traces are independent; interactive session grouping belongs to the REPL. For example, from the agent checkout:

```sh
uv run --extra tracing xp-agent eval --trace --output eval-results/traced.json
```

A completed attempt prints a local trace link and opaque trace ID (the dashboard URL if project lookup could not resolve a direct link). Metadata JSON is retained even if export fails: REPL planning records go under the state directory's `traces/`; execution records live beside the session artifacts. Batch planning records go beside its output under `traces/`; batch execution records go inside its output directory. Direct controller eval traces use `~/.local/state/xp-coding-agent/traces/`. REPL fixture traces are disposable along with their temporary fixtures. Filenames are `trace-<opaque-id>.json`, with a `.export.json` receipt after successful export. All such records are Git-ignored.

Export waits at most 20 seconds per attempt. Missing keys, an unavailable server or missing optional SDK produce a warning; the coding outcome is unchanged. A receipt means the transport accepted the request, not that a later database read has verified ingestion. Export is not automatic retry/durable delivery. A crash before finalization can lose the in-memory trace. The coding session's own checkpoints remain the recovery mechanism.

## Read a trace

A **trace** groups one attempt. An **observation** is a timed operation within it. Observations have types: `agent` for the controller attempt, `span` for a workflow step, `generation` for a bounded model invocation and `tool` for an actual test-runner invocation.

```text
xp.execute                         agent: approved execution attempt
  prepare-workspace                span: new sessions only
  execute-session                  span: session orchestration
    execute-increment              span: one XP cycle
      baseline                     span
        run-tests                  tool
        controller-gate            span
      coding-phase                 span: phase=red, then green, then refactor
        model.propose              generation
        run-tests                  tool, only if edits passed policy
        controller-gate            span
      final                        span
        run-tests                  tool
        controller-gate            span
```

This is observation nesting, not another LangGraph graph. Actual registered nodes remain `baseline`, `red`, `green`, `refactor`, `final`. Discovery/planning has separate `model.select` and `model.propose` generation observations. A generation represents a CLI request, not every hidden provider-internal turn. Usage is captured only from validated CLI-reported counts; absent or malformed counts remain unknown. Cache counts remain metadata. Billing is unknown: explicit zero cost suppresses inferred API prices, and **must not be read as a free request or actual invoice**.

Only closed, validated metadata fields are retained: phase, status, counts, provider/model/auth mode, opaque identities and artifact hashes. Model identifiers must match a short safe character set. Records are limited to 2,000 observations and 1 MB; dropped observations set `evidence_complete=false`. Hashes reveal equality and can allow guessing low-entropy content: treat metadata as private too. No user or project identity is assigned.

## What the scores mean

Python functions in `xp_agent/tracing/evaluation.py` inspect controller evidence, not model statements or timing order. Local evidence retains test identities and before/after artifact hashes; only verdicts, counts and hashes are traced. Each evidence row has schema version 1 and a sequence number. Accepted rows must form baseline → red → green → refactor → final, with linked accepted artifact hashes.

| Score | Meaning |
|---|---|
| `red_execution_valid` | Accepted red has new assertion failures, unchanged source, changed tests, all baseline tests passing and no errors/skips |
| `green_execution_valid` | Accepted implementation/refactor/final checks pass and retain required test identities |
| `edit_scope_preserved` | Accepted candidates satisfy phase edit scope and hash continuity; green/refactor preserve accepted tests |
| `evidence_complete` | Required local execution evidence has the supported schema and ordering; trace truncation additionally makes it false |
| `tdd_sequence` | `complete`, `valid_partial`, `violation`, or `insufficient_evidence` |
| `independent_acceptance_passed` | Withheld fixture tests passed; unknown for ordinary coding sessions |
| `pair_ownership_valid`, `handoff_state_valid` | `not_applicable` in real single-agent runs; exercised only by synthetic future-protocol fixtures |

Missing observations/evidence do not become a pass. Boolean unknowns are omitted from Langfuse scores. A blocked/cancelled session can have a valid partial sequence. Invalid proposals that the controller rejected are not accepted TDD violations. Multi-increment sessions combine evidence conservatively; old session records lacking new evidence fields yield `insufficient_evidence` rather than fabricated provenance. Scores observe the controller; they do not replace its approval, policy or XP gates.

These checks assume the runner's reports are trustworthy. They cannot prove assertion strength, business correctness, hostile-code safety, or independent partner contexts. User sessions still require human acceptance.

## Run idiomatic SDK experiments

The existing nine deterministic evals still work without Langfuse or keys. To run them as a local-data Langfuse experiment:

```sh
uv run --extra tracing xp-agent eval --experiment --output eval-results/experiment.json
```

This uses the SDK's `run_experiment`: a list of fixture IDs, a task function executing the fixture, per-item `Evaluation` results, and a run-level evaluator. The task exercises the existing controller and primary REPL/Git/Docker paths, then attaches metadata observations under the SDK task. Only safe fixture IDs and summaries enter SDK input/output; source-bearing session dictionaries never do.

The dataset has nine controller/REPL cases plus four **synthetic protocol** cases: valid A-red/B-green/B-red/A-green, self-implementation, missed role swap and stale artifact reference. Detecting an intentionally invalid fixture is a passing case even though its protocol score is false. This does not implement two agents, context isolation, complete handoff budgets, or a pairing write lease.

The suite gate requires every expected case exactly once and every case/evaluator to pass. Missing/duplicate/failed cases cannot be hidden by a good average. Return code 0 means the suite passed; 2 means a case or experiment/export requirement failed. `--experiment --live` is refused. These experiments consume no hosted model quota; ordinary `eval --live` remains a separate authorized-provider operation.

Experiments use a separate process with a fresh SDK/OpenTelemetry setup and a 15-minute execution deadline. Cancellation/timeout gives the worker up to 15 additional seconds to unwind Docker/SDK cleanup before forced termination; abrupt failure can still require inspecting owned test containers. Keys stay in memory; model credentials are excluded, while local Docker connection settings are forwarded. Unlike optional session export, an explicitly requested experiment requires a working local Langfuse service. Use the printed/saved local experiment URL to compare runs. No hosted dataset or UI code-evaluator dispatcher is required. SDK experiments and scores are [documented core features](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk); [self-host feature availability](https://langfuse.com/pricing-self-host) differs from hosted paid plans.

## Contributor verification and remaining setup

```sh
uv sync --frozen --extra tracing
uv run --extra tracing pytest tests/test_tracing.py
XP_DOCKER_TESTS=1 uv run --extra tracing pytest
uv run --extra tracing xp-agent eval --output eval-results/scripted.json
uv build
```

`test_tracing.py` checks metadata privacy, failure isolation, bounds, REPL opt-in/rejection, evidence mutation, future pair-protocol errors, SDK hierarchy/session/timestamps, safe experiment summaries, complete-suite gates, transport restrictions and upload failures. SDK tests use an in-memory exporter and mocked HTTP, not a live server or hosted model. Without the extra, SDK-specific tests skip; CI installs it explicitly.

Live server ingestion, score retrieval and the end-to-end experiment UI still need verification after local project keys are configured. A successful in-memory SDK test is not evidence that this deployment accepted data. The first local audit should send a synthetic fixture, retrieve observations/scores with the Langfuse CLI and check nesting, timings, safe fields, outcome and session/experiment links. See [evaluation evidence](evaluation.md).
