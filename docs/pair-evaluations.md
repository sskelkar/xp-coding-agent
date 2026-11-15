# Evaluating the XP pair workflow

The pair evaluation runs production routing, grades accepted transitions, and checks candidate behavior in Docker. The `--live` option uses the selected hosted model. Graders apply deterministic checks. See the [runtime guide](pair-runtime.md).

## Choose the check you want to run

Run these commands from the agent checkout after building the test image. Use the scripted command to check the graph, controller, and Docker setup without provider credentials.

```sh
uv run --frozen xp-agent eval --output eval-results/pair.json
```

To evaluate a hosted model with an authorized account, choose one provider and sign in to its CLI. These runs use a synthetic task and consume quota.

```sh
uv run --frozen xp-agent eval --live --provider codex --auth cli --output eval-results/codex.json
uv run --frozen xp-agent eval --live --provider claude --auth cli --output eval-results/claude.json
```

Add `--model` to select an account-supported model. Add `--trace` after installing the tracing extra and configuring local Langfuse. [Provider options](providers.md) · [Tracing setup](tracing.md)

The CLI returns exit code 0 when all required checks pass, or 2 for an incomplete, blocked, or failed evaluation. The JSON report has `mode`, `status`, `observed_roles`, and separate results for graph probes, the transition grade, and independent Money acceptance. `verification.live_model_coding` is true only for a passing hosted run. An unanswered business question ends the automated scenario without inventing an answer, and `money_acceptance` can be empty when the run stops before acceptance.

The report points to the private session directory alongside the report. That directory contains the checkpoints, candidate workspace, and source-bearing evidence. [Session artifacts](pair-runtime.md#review-the-result-or-resume) · [Recorded validation](evaluation.md)

## What is implemented

1. A versioned offline controller-record grader for alternating ownership, phase order, snapshot continuity, declared runner binding, red/green requirements, source/test edit separation, distinct continuing context IDs, ordered history delivery, user agreement/feedback, demo samples, duplicate logical actions and bounded check-in cadence.
2. Independent Money acceptance, executed through the existing restricted Docker runner. Positive implementations and deliberately wrong implementations exercise the oracle itself.
3. Five public Money business scenarios, including post-demo clarification, delayed feedback, interface evolution and exchange-rate ambiguity. The production Money integration exercises the bounded public API and role switching; these scenario definitions are not proof that every proposed product scenario, especially test adaptation, is supported.
4. A complete-case suite gate: missing, duplicate, unknown, failed and unrun cases cannot be hidden by averages.
5. A compiled-LangGraph conformance probe with instrumented partner and runner ports, real checkpoint interrupts/resume, and deliberately broken reference graphs.
6. Tests of the evaluators with deliberately corrupted records and real candidate code.

In the managed cloud environment, use `umask 022` so container UID 65534 can read generated fixture directories. [Cloud setup](../environment/README.md)

## Inspect the scenario catalog

```sh
uv run --frozen python -m xp_agent.evaluation.pair catalog
```

The catalog deliberately reports scenarios and remaining qualification scenarios as `not_run`, with `runtime_ready: false`. Implemented capabilities are listed separately; the catalog itself executes no checks. Listing scenarios is a successful CLI operation (exit 0), not a passing evaluation.

## Grade controller records

```sh
uv run --frozen python -m xp_agent.evaluation.pair grade evals/fixtures/pair/valid-records.json \
  --output eval-results/pair-record-grading.json
```

The supplied file is a **synthetic evaluator fixture**, not a recording from collaborating agents. It has two cycles, A-red/B-green then B-red/A-green, cleanup steps, a demonstration and user acceptance. Its snapshot files are placeholders; declared runner results are not independently executed by this command.

Exit 0 means the supplied records satisfy this schema's implemented checks. Exit 2 means a violation, insufficient evidence, a valid but incomplete run, or an execution/input blocker. `runtime_verified` is always false. Do not interpret a passing fixture as evidence that orchestration or model memory works.

### Evidence schema version 1

The JSON envelope contains:

- `version: 1`;
- `status`: `completed`, `blocked`, `cancelled`, or `waiting`;
- `snapshots`: immutable revision identifiers mapped to text file mappings;
- `events`: ordered controller records with unique logical `id`, `kind`, and `actor`.

Supported events:

| Event | Required evidence and checks |
|---|---|
| `agreement` | User actor and positive agreement revision, before coding. |
| `step` | Actor, cycle, phase (`red`, `green`, `refactor`), before/after snapshot IDs, agreement revision, stable distinct context ID, ordered prior event IDs in `history`, and a runner `report`. |
| `question` | A unique ID; affected coding is suspended until corresponding user feedback. |
| `demo` | Controller actor, current green revision at a completed cycle boundary, and nonempty `samples` with `input`, `expected`, `actual`. |
| `feedback` | User actor, matching outstanding question/demo ID in `demo`, a decision (`continue`, `revise`, `accept`, `reject`), and agreement revision. Revision changes must increment explicitly. Completion requires acceptance of a demo. |

Runner reports contain `revision`, integer `returncode`, and lists of test identities: `passed`, `failed`, `errors`, `skipped`, `required`. Behavioral red needs new assertion failures while earlier and declared baseline tests pass. Green/cleanup require all accumulated tests to pass with no errors/skips and no disappearance. Zero-test green is invalid. During red only test paths may change; during green/cleanup accepted tests remain unchanged in this initial schema.

Optional `active_seconds` must be finite, nonnegative and monotonically increasing. With these timestamps supplied, work after the 300-second active-development boundary requires feedback. Cycle cadence defaults to three completed cycles between responses. `active_time_evidence: false` explicitly identifies records that cannot establish time-based cadence. Context IDs/history references establish only declared history delivery, not that models retained or used that information.

The integrated evaluation collects snapshots and reports from the running controller. The standalone grader can check the consistency of supplied records and compare their demo samples. Authenticating those records or independently running the supplied demos is outside its scope. Keep source-bearing records and histories private. The grader emits verdicts and counts.

Unknown event kinds and malformed/missing records fail closed as `insufficient_evidence`. Schema version 1 does **not** model rejected proposal attempts, controlled scaffolding, guarded test adaptation, crash-boundary recovery or actual scheduling. Version 2 adds controlled bootstrap as described below; other limitations remain. Duplicate accepted action IDs are detected, but this alone is not proof of exactly-once recovery. Do not silently discard unsupported events to obtain a pass.

## Runtime evidence schema version 2

The pair runtime writes `pair-evidence.json` and its grade in the private session directory. It uses the same accepted-transition grader, with an explicit versioned bootstrap event. Empty initial file snapshots are allowed without labeling a zero-test run a passing baseline.

A `bootstrap` record identifies its actor, cycle, agreement, before/after source revisions, the checked candidate revision, context/history references and actual red runner report. It must preserve existing source AST statements and tests, change only project source, and leave the pending test failing by assertion while prior regressions pass. The next accepted phase remains red. The original test author is not falsely claimed to have seen a later bootstrap event; its proposal history precedes that event, while subsequent requests receive the recorded outcome.

Version 2 records can include `dispatch_active` separately from accepted-event time so a phase that crosses the time boundary is distinguished from dispatching new work after it. Runtime records grade accepted transitions; rejected-candidate detail and full private conversations are retained in session history/checkpoints, not represented as a complete crash audit by this grader. No LLM judge interprets the records.

The integrated check uses scripted proposals by default, executes tests and business demos in Docker, grades the resulting version-2 records, and independently runs all 33 Money checks.

## Validate actual LangGraph handoffs without an LLM judge

`xp_agent.evaluation.pair.graph_probe.probe_graph(factory, scenario=...)` runs a real
`CompiledStateGraph`, not an event list. The factory receives instrumented
partner/runner ports and returns the compiled graph under test with a checkpointer.
The graph, not the probe, chooses the next node and partner. The probe records
node/step identity from LangGraph execution context and requires distinct graph
steps between partner invocations and test gates. A manual four-call loop inside
one node is rejected even if its actor labels appear in the expected order.

The probe observes calls outside graph state and compares exact sequences:

- Successful routing: `A:red`, runner red, `B:green`, runner green,
  `B:red`, runner red, `A:green`, runner green.
- `red_already_green`: a controlled first test passes unexpectedly. The graph must
  stop before invoking an implementer; a model's claimed red cannot advance it.
- `green_fails`: a controlled implementation fails. The graph must stop before
  handing off the next test. These probes use a single-attempt configuration;
  bounded retry behavior needs additional production integration cases.

A successful routing probe also requires an actual LangGraph interrupt in persisted
state. It resumes using `Command(resume="accept")`, checks that the graph finishes,
and detects any repeated partner/runner calls or coding after business acceptance.
An exclusive instrumentation lease detects overlapping calls; an attempted overlap
fails the probe, even though instrumentation prevents the second stub from running.
This tests invocation ordering, not host-file write isolation.

The reference graphs in `tests/evaluation/test_pair_graph_probe.py` demonstrate that the probe
passes valid scheduling and fails wrong actors, skipped runner calls, ignored red/
green outcomes, absent business interrupts, extra work after feedback and concurrent
partner calls. **These are evaluation-only graphs, not the replacement product.**
The production pair graph has a separate adapter at `xp_agent.evaluation.pair.graph_probe.probe_factory`. It calls the same `build_graph` as real sessions, replacing dependencies, not routing.

A runtime adapter must exercise its actual compiled
routing with these instrumented dependencies. Rebuilding the passing reference graph
inside an adapter would only rerun the self-test and is not runtime qualification.
The probe uses scripted partners/runner outcomes, so routing results do not establish
coding skill, real provider memory, independent Money correctness or all recovery
semantics. Test code itself is deterministic; there is no LLM judge or hosted call.

## Run independent Money acceptance

A trusted toy candidate directory must provide `money_api.py`. It can wrap a different internal design; the evaluator does not require Beck's Java classes. This public adapter contract is part of the task, not a hidden expectation:

| API | Contract |
|---|---|
| `make(value, currency)` | Construct a monetary value. |
| `amount_of(money)` | Return its integer amount. |
| `currency_of(money)` | Return its currency string. |
| `multiply(money, factor)` | Return the multiplication result, preserving currency. |
| `add_money(left, right, rates)` | Exchange stage only: add amounts, returning the left-hand currency. |

Stages are cumulative:

- **`multiplication`**: 25 checks over nonnegative integer amounts and positive integer multipliers in USD. No immutability requirement at this stage. No decimal, negative-input or production financial correctness claim.
- **`reusable`**: adds three checks that repeated multiplication leaves the original unchanged and earlier results remain correct. Apply only after the user has agreed non-mutation.
- **`exchange`**: adds five checks for USD/CHF addition, same-currency addition and explicit missing-rate errors. `rates["CHF/USD"] = 2` means two CHF per USD; all evaluated conversions divide exactly. Missing rates must raise `ValueError`. No rounding or fractional-conversion behavior is inferred.

```sh
umask 022
uv run --frozen python -m xp_agent.evaluation.pair money /path/to/toy-candidate \
  --stage reusable --output eval-results/money-acceptance.json
```

Candidate Python is copied into an isolated read-only, network-disabled test snapshot; it is never imported or executed on the host by this evaluator. Candidate files remain unchanged. The loader rejects symlinks, reserved evaluator/pytest configuration paths, missing adapters and snapshots over 400 KB. It ignores dot-directories, non-Python files and Python caches. The test image must contain any required runtime dependencies.

The independent test module is inserted by the evaluator, not read from candidate-provided tests. Acceptance requires the exact expected count of independent passing checks, no errors/failures/skips anywhere in the run and a successful runner exit. Candidate-owned passing tests cannot inflate the acceptance count. A candidate hash identifies the evaluated source snapshot. The report does not export source or raw runner output.

These checks are independent of the pair's own tests, but candidate code and pytest still share a process inside the container. They are for trusted toy code, not a hostile-code or tamper-proof evaluation boundary. Keep evaluator code and additional input examples out of the coding agents' workspace/context. A wrapper is the evaluated public API; reviewing wrapper changes remains necessary when comparing internal designs.

A passing Money result proves only that this candidate passed the selected independent behavior checks. It does not establish that two agents authored it, used TDD, held a business demo or followed a handoff protocol. The report keeps `runtime_verified: false` for that reason.

## Verify the evaluators

```sh
umask 022
XP_DOCKER_TESTS=1 uv run --frozen pytest \
  tests/evaluation/test_pair_contracts.py tests/evaluation/test_pair_money.py tests/evaluation/test_pair_eval_cli.py \
  tests/evaluation/test_pair_graph_probe.py -q
```

The Docker tests require the existing `xp-agent-tests:0.1` image. Without `XP_DOCKER_TESTS=1`, they are explicitly skipped; do not report that run as independent acceptance validation.

Tests include valid and invalid counterpart fixtures, wrong actors, absent role swaps, stale runner revisions, lost/reset/shared contexts, dropped prior tests, fabricated red/green, missing business answers, silent agreement changes, wrong demo output, duplicate feedback/actions, time/cycle limits and malformed evidence. Real Docker tests reject constant answers, mutation, inverted exchange conversion and missing API behavior while accepting correct implementations.

## What remains before qualifying the new product

The remaining qualification work includes guarded test evolution, model use of prior decisions in repeated live runs, arbitrary crash-window recovery, a human business-feedback pilot and broader project profiles. Production graph routing, controlled bootstrap, conversation replay, SQLite business-boundary reopening, executed demonstrations and safe pair trace metadata now have deterministic integration coverage. Live-provider access must be usable before live Money qualification can pass.

Keep integration evidence specific to the profile and run. The older synthetic pair scores and standalone record fixtures cannot substitute for production graph and Docker results. No model judge or automatic provider fallback is introduced.
