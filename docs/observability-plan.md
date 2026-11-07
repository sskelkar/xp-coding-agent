> Implementation status: optional local tracing, deterministic execution scores and SDK scripted experiments are implemented. See [current behavior](tracing.md). This document preserves the reviewed design; proposed richer handoff/ownership/budget evidence and actual pairing remain future work. Real local ingestion/retrieval and the experiment UI have been verified with synthetic fixtures; see [evaluation evidence](evaluation.md).

# Local Langfuse observability and TDD evaluation plan

Status: proposed for human review; implementation has not started.

## Goal

Make XP execution observable and measurable before introducing two-agent TDD ping-pong. We should be able to inspect the sequence and identities of model proposals, controller decisions and test outcomes as distinct events, and detect when accepted work violates the protocol.

The first delivery instruments the current single-agent REPL and existing evals. It also defines/tests the evidence contract needed for pairing. Real two-agent execution remains roadmap milestone 6; synthetic role-sequence checks must not be presented as a working pair implementation.

The controller and Docker test runner continue to enforce correctness boundaries. Langfuse stores and displays observations/scores; asynchronous telemetry is not permission to advance a coding phase. Model-written claims and agreement between two agents are insufficient evidence.

## Current starting point

- The REPL, approved plans, linked worktrees, sequential XP increments and selected-session continuation exist.
- `workflow.py` enforces baseline/red/green/refactor/final gates. Evidence records include reports and whole-candidate hashes. Accepted tests are immutable during implementation/refactoring.
- Nine deterministic eval cases already cover success, invalid progression and primary REPL approval/rejection. A withheld numeric acceptance test checks successful fixture implementations.
- Pair identities, context separation, handoff ownership and role swaps are not implemented.
- LangSmith tracing is explicitly disabled. Keep it disabled.
- A local Langfuse instance is already available on loopback port 4000. Reuse the service rather than start another database/storage stack. Configure an XP project and project keys separately; do not silently reuse another application's credentials.

## Free Langfuse features to use

| Feature | Use in this project |
|---|---|
| Traces and nested observations | One trace per planning/execution attempt, with discovery, increments, coding proposals, test runs and controller decisions underneath it. An observation is a recorded operation with timing and metadata. |
| Sessions | Group planning, initial execution and resumed attempts for one approved coding session under an opaque ID. |
| Tree/timeline and Agent Graph | Inspect the actual order of calls and retries. Use expanded graph view for individual calls; an aggregated graph alone can hide repeated attempts. Neither view certifies TDD. |
| Programmatic scores | Compute deterministic checks in our Python harness and attach boolean/categorical results to the relevant observation/trace. |
| Datasets and experiments | Run fixed synthetic tasks through the actual REPL, compare application/prompt/model/pairing versions and inspect failures per case. Local dataset inputs can still be exported to the configured Langfuse instance. |
| Score analytics and dashboards | Show accepted protocol violations, valid/invalid attempts, correctness, completion, time and reported usage separately. |
| Human annotation | Record whether tests express the intended requirement and whether the delivered behavior is acceptable. Human review is distinct from automated gate success. |

These are core self-hosted features. Their software availability does not make model requests, model judges or machine resources free.

### Where deterministic checks run

Start with our own Python evaluator functions and upload their results using Langfuse's score API/SDK. This reuses pytest/CI and needs no extra evaluator execution service.

Langfuse can execute code evaluators itself, but on self-hosted installations they are disabled without a dispatcher. The current local in-process dispatcher runs JavaScript/TypeScript and is explicitly unsandboxed; Python execution uses the Lambda dispatcher. Do not add that infrastructure for this first delivery, and never run generated project tests inside a Langfuse worker.

LLM-as-a-judge is optional future assistance for semantic test quality, not the judge of red-before-green, ownership or immutable tests. It would need authorized model access and calibration against reviewed examples.

## Proposed metric set for approval

Existing below means underlying controller checks/eval evidence exist, not that Langfuse scores already exist. New scores are proposed. Pair-only scores are not applicable to current single-agent runs.

| Priority | Status | Metric | Source/evidence | Decision it informs | Measurability |
|---|---|---|---|---|---|
| P0 | Existing gate; new score | `red_execution_valid` | Same production-source hash as pre-red; newly failing assertion IDs; baseline tests still passing; no errors/skips | Permit an implementation handoff only after verified red | Deterministic execution/protocol check; does not prove test intent |
| P0 | Existing gate; new score | `green_execution_valid` | Passing run on accepted candidate; unchanged accepted-test hash; all required test identities present | Accept implementation only when target/regression tests pass | Deterministic under the trusted-runner assumption |
| P0 | Existing restriction; richer evidence needed | `edit_scope_preserved` | Declared edit scope, actual changed paths/kinds, source/test hashes and controller decision | Reject source writes during red or test weakening during green/refactor | Deterministic structural check |
| P0 | New; pairing prerequisite | `pair_ownership_valid` | Stable actor identity/context assignment and controller-owned write permission for each accepted action | Prevent a test author implementing its own cycle, competing writers or missed swaps | Deterministic once actual pair identities/ownership exist; N/A today |
| P0 | New; pairing prerequisite | `handoff_state_valid` | Handoff sequence, accepted artifact/test hashes and remaining grant/budget | Refuse stale handoffs or authority/budget expansion | Deterministic once actual handoffs exist; N/A today |
| P0 | Existing fixture oracle; new score | `independent_acceptance_passed` | Withheld fixture acceptance tests, separate from generated tests | Detect implementations that pass generated tests but miss required behavior | Executable on known fixtures; no universal semantic guarantee |
| P0 | New | `evidence_complete` | Schema version, ordered event IDs, expected phase/gate references, no required missing/truncated evidence | Prevent unknown/missing results from counting as passes | Deterministic; required for a complete compliance judgment |
| P0 | New summary | `tdd_sequence` | Replay of accepted controller transitions and linked evidence | Distinguish complete, valid-partial, violated and insufficient-evidence runs | Categorical; do not collapse a cancelled run into complete success |
| P1 | Existing counters; new comparison | Completion, rejected proposals, attempts and elapsed time | Controller records and timed observations | Compare usefulness/overhead without hiding violations behind averages | Deterministic; rejected invalid proposals differ from accepted violations |
| P1 | New capture where supported | Reported token usage | Validated provider CLI usage fields | Compare single-agent and future paired/context-reset modes | Only provider-reported values; missing is unknown; no inferred subscription invoice |

A genuine assertion failure is necessary but not sufficient: a meaningless test can fail too. Keep independent acceptance and human review alongside the protocol checks. Test coverage/mutation testing could strengthen the semantic signal later, but neither is an initial hard gate.

### Ping-pong contract to instrument when pairing is added

```text
Cycle 1: A proposes test → controller verifies red → B implements → controller verifies green/refactor/final
Cycle 2: B proposes test → controller verifies red → A implements → controller verifies green/refactor/final
Cycle 3: A proposes test → ...
```

Retries retain the same owner and consume the existing budget. Role swaps occur only after a completed accepted cycle. The controller remains the only process that materializes accepted code. Distinct A/B labels alone do not prove distinct contexts: the pairing implementation must actually manage separate partner contexts and record their assignment.

Record an explicit controller sequence number and artifact references. Do not infer causality from timestamps, span nesting or when Langfuse happens to ingest observations.

## Trace structure and evidence

Use stable operation names, typed observations and opaque IDs. A trace records one attempt; a resumed attempt gets a new trace linked to the same session and prior checkpoint. Waiting for human review is not active model/test time.

Illustrative future pair execution structure (current runs have one actor):

```text
xp.execute                         [agent/controller root]
  increment                        [span: one behavior cycle]
    partner-a                      [agent: role=test-author]
      propose-tests                [generation: bounded provider invocation]
    verify-red                     [tool: actual Docker tests]
    validate-handoff               [span: controller decision]
    partner-b                      [agent: role=implementer]
      implement                    [generation: bounded provider invocation]
    verify-green                   [tool: actual Docker tests]
    consider-refactor              [agent/generation as actually executed]
    verify-final                   [tool: actual Docker tests]
```

An agent observation represents a partner's execution; a generation represents a model invocation; a tool represents controller-owned execution such as testing. Do not invent provider-internal model turns/tools: the CLI adapters expose bounded calls, not full internal conversations. Where only aggregate usage is available, mark that visibility explicitly.

Proposed evidence fields:

- Opaque session/attempt/event IDs; schema/evaluator/application versions; sequence number; parent and prior-attempt references.
- Increment/phase/attempt number; execution mode; actor and role when known; provider, model and auth mode, never credentials.
- Pre/post source, test and full-candidate fingerprints; image identity; opaque required/passed/failed test identities; error/skip counts; result code.
- Proposal accepted/rejected, controller gate outcome and closed reason code; remaining budgets; whether evidence is complete.

The local controller journal is authoritative. Langfuse receives a bounded allowlisted representation. Critical code/test identities must be captured at execution time; existing reports must not be backfilled with invented actor or red-state evidence.

For a rule depending on several operations, compute from the complete local journal or expose an explicit controller summary observation. A server evaluator given one isolated observation cannot safely infer the full run by looking only at its final text.

## Privacy and local operation

- Opt-in via `--trace` / `--no-trace` and REPL `/trace on|off`; default off. A visible status identifies whether recording/export succeeded. Exact option plumbing is part of implementation, not existing CLI behavior.
- Use an optional tracing dependency pinned initially to **`langfuse==5.1.0`**, the latest SDK checked during research. Existing local server version 4.72.0 must pass an actual ingestion test before the feature is marked verified. Use current OpenTelemetry ingestion rather than legacy APIs.
- Fixed loopback export destination `http://127.0.0.1:4000`; no implicit Langfuse Cloud fallback, ambient exporter destination, proxy redirection or HTTP redirects.
- Start with metadata only: counts, identities/fingerprints, decisions, timings, role/provider/model and meaningful safe root input/output summaries. Exclude prompts, source/diffs, task text, raw replies, file/repository names, exception messages, credentials and model reasoning.
- This privacy choice deliberately limits semantic diagnosis in the UI. Full model-context inspection would require a later explicit capture policy; do not claim metadata can reconstruct the whole conversation.
- Keep private trace JSON with session/run artifacts, outside published code. Generated tests and provider CLI environments receive no Langfuse credentials or extra networking.
- Record in the trusted controller and export after an operation using an isolated, deadline-bounded host exporter. Avoid automatic whole-state LangGraph callbacks that could export source dictionaries.
- Missing keys, unavailable SDK/service or export failure produce a visible warning and retained local records. They do not alter the accepted code, test results or XP decision. A truncated/missing required journal cannot yield a complete compliance score.
- Keep LangSmith disabled and runtime approval/resume identities intact. Trace preferences do not rewrite an existing approved grant.
- SDK, keys, model credentials and local instance state stay outside Git; telemetry remains local. Local metadata storage still needs a retention policy; no automatic unlimited-history promise.

## Iteration 1 — useful local trace of the existing agent

Deliver the optional bounded recorder/exporter and instrument discovery, plan/approval outcome, session execution, increment/phase attempts, model calls, test runs and report/finalization. Include rejection, cancellation, provider failure and resumed-attempt grouping. Retain batch support without creating a second workflow implementation.

Likely code areas: new tracing module/package, `repl.py`, `cli.py`, `session.py`, `workflow.py`, both provider adapters, `sandbox.py`, optional dependency/lock metadata and artifact ignore rules. Actual instrument names/fields must remain within the reviewed evidence contract.

Acceptance:

1. The same deterministic REPL tasks return the same outcomes with tracing off/on and with the exporter unavailable.
2. A synthetic real-Docker REPL run produces a local trace link with correct ordering, hierarchy, model labels, test outcomes and safe root summaries.
3. A rejected plan, handled cancellation and resumed run remain inspectable without false completion or refunded budgets.
4. Privacy tests inject synthetic secret/source/path values and prove they cannot enter exported records. Exporter tests refuse nonlocal destinations, redirects and credential inheritance.
5. Fetch the exported observations from the local service and audit actual stored parent links, types and metadata against current Langfuse best practices. A successful HTTP submission alone is insufficient.

## Iteration 2 — deterministic TDD scores and experiment baseline

Implement versioned pure-Python checkers over the controller evidence; apply the metric set above to applicable current behavior. Export scores with stable identities so replay/re-export does not duplicate evaluations. Mark pair-only checks N/A on single-agent runs.

Use the nine existing synthetic eval cases as the initial reviewable experiment data. Keep stable case IDs, expected outcomes and evaluator versions in Git; no real work-project data. Every case runs through its existing appropriate harness, with primary-REPL cases preserved. Baseline comparisons must use the same case IDs and evaluator versions.

Acceptance:

1. Existing premature green, errors-as-red, scope escape, test weakening and refactoring regression are detected; a controller correctly blocking them passes its adversarial case.
2. Independently test that an accepted invalid transition is scored as a violation, while an invalid proposal rejected by the controller is recorded as a rejection, not accepted unsafe work.
3. A valid run can still fail independent acceptance if it overfits its generated tests; both results are visible.
4. Missing/truncated evidence, missing cases, evaluator errors or duplicate case IDs cannot pass the quality gate. No averaging can hide a critical accepted protocol violation.
5. All required deterministic cases pass locally without Langfuse availability. CI keeps its existing no-model-credential path. Langfuse export/dashboard failure is reported separately from domain quality failure.
6. Create a baseline experiment locally, retrieve observations/scores and verify that the UI/API result matches the local evaluator report. Run a controlled intentionally bad candidate and demonstrate a real failing comparison.

## Iteration 3 — pair-ready protocol checks before implementing pairing

Add synthetic event-sequence unit cases for A-red/B-green then B-red/A-green, same-author implementation, missing role swap, stale handoff, competing writers and interrupted/resumed handoffs. These test the evaluator/evidence contract; they are not paired live task runs.

Acceptance: valid sequences and invalid sequences receive the expected scores; single-agent sessions remain N/A for pair-only checks; documentation clearly distinguishes simulated protocol coverage from actual role/context enforcement.

When milestone 6 implements pairing, connect real controller ownership/handoff events to these checks and add real two-cycle REPL integration plus independent acceptance. Compare pairing against the single-agent baseline on repeated equivalent tasks under comparable total budgets. Pairing does not ship on the strength of a trace visualization alone.

## Review and verification discipline

For each behavior change, demonstrate a meaningful failing test, implement the smallest passing change, then refactor. Keep the REPL usable at each iteration. Run focused tests followed by the full deterministic/Docker suite for execution changes. Use only synthetic fixtures for hosted calls and local ingestion checks.

Update README, the Java-oriented explainer, provider/security/evaluation docs and milestone status with implemented behavior. Leave future items visibly proposed. This plan-review step changes only this proposed document. Implementation after approval covers the three iterations above. Actual pairing, prompt migration, LLM-judge setup, Langfuse-hosted code-execution services and cloud export remain separate scope. No commit, push or external publication is authorized.

## Alternatives and tradeoffs

- **Automatic LangGraph tracing callbacks:** convenient graph coverage, but potentially export whole state/source and do not reveal strict XP semantics automatically. Prefer explicit controller observations with a closed schema for v0.
- **Langfuse-hosted code evaluators:** reusable UI-managed checks, but add dispatcher/runtime infrastructure. Start with application-side Python scores.
- **LLM judge for TDD compliance:** flexible narrative assessment, but unnecessary uncertainty/cost for ordering, hashes and test status. Use deterministic checks for protocol; reserve human/calibrated semantic judgment for test intent.
- **Raw prompts and code in traces:** richer debugging, but a larger sensitive-data surface. Start with metadata and keep code/evidence locally; reconsider capture only through an explicit policy change.
- **A single combined quality number:** easy to chart, but hides incomplete runs, safely blocked attacks and semantic failures. Keep protocol, controller-guard correctness, completion, acceptance and cost/time separate.

## Official sources checked

- [Free self-hosted features](https://langfuse.com/pricing-self-host)
- [Tracing best practices](https://langfuse.com/docs/observability/best-practices)
- [Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs)
- [Programmatic scores](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk)
- [Code evaluators](https://langfuse.com/docs/evaluation/evaluation-methods/code-evaluators) and [self-hosted dispatcher requirements](https://langfuse.com/self-hosting/configuration/code-evaluators)
- [Experiments using local or hosted data](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
- [Comparing experiment versions](https://langfuse.com/docs/evaluation/experiments/compare-experiments) and [CI release policies](https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd)
- [SDK/server compatibility](https://langfuse.com/docs/compatibility)
