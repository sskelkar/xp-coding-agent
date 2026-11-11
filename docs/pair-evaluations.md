# Evaluating the proposed XP pair workflow

This is the first executable evaluation foundation for the [redesign plan](xp-ping-pong-redesign-plan.md). It does not replace the shipped single-agent flow, create two persistent model sessions, or qualify a two-agent runtime. No hosted model calls are made by these tools.

## What is implemented

1. A versioned offline controller-record grader for alternating ownership, phase order, snapshot continuity, declared runner binding, red/green requirements, source/test edit separation, distinct continuing context IDs, ordered history delivery, user agreement/feedback, demo samples, duplicate logical actions and bounded check-in cadence.
2. Independent Money acceptance, executed through the existing restricted Docker runner. Positive implementations and deliberately wrong implementations exercise the oracle itself.
3. Five public Money business scenarios, including post-demo clarification, delayed feedback, interface evolution and exchange-rate ambiguity. Scenario definitions are inputs for a future runtime integration, not claims that those flows already run.
4. A complete-case suite gate: missing, duplicate, unknown, failed and unrun cases cannot be hidden by averages.
5. A compiled-LangGraph conformance probe with instrumented partner and runner ports, real checkpoint interrupts/resume, and deliberately broken reference graphs.
6. Tests of the evaluators with deliberately corrupted records and real candidate code.

Run commands from the agent checkout. The test image must already exist; prepare it with the repository/environment setup instructions. Use `umask 022` in the managed cloud environment so container UID 65534 can read generated fixture directories.

## Inspect the scenario catalog

```sh
UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --extra tracing \
  python -m xp_agent.pair_evals catalog
```

The catalog deliberately reports scenarios and pending runtime capabilities as `not_run`, with `runtime_ready: false`. Listing scenarios is a successful CLI operation (exit 0), not a passing evaluation.

## Grade controller records

```sh
UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --extra tracing \
  python -m xp_agent.pair_evals grade evals/fixtures/pair/valid-records.json \
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

Snapshots and reports must be collected from the controller, with execution bindings independently established by the future integration harness. This grader checks consistency of supplied records, not their authenticity. Likewise it compares supplied demo samples; it does not execute them. Source-bearing records and histories must stay private. The grader emits verdicts and counts, not snapshots or conversations.

Unknown event kinds and malformed/missing records fail closed as `insufficient_evidence`. The current schema intentionally does **not** model rejected proposal attempts, controlled scaffolding, guarded test adaptation, crash-boundary recovery or actual scheduling. Duplicate accepted action IDs are detected, but this alone is not proof of exactly-once recovery. Do not silently discard unsupported events to obtain a pass.

## Validate actual LangGraph handoffs without an LLM judge

`xp_agent.pair_evals.graph_probe.probe_graph(factory, scenario=...)` runs a real
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

The reference graphs in `tests/test_pair_graph_probe.py` demonstrate that the probe
passes valid scheduling and fails wrong actors, skipped runner calls, ignored red/
green outcomes, absent business interrupts, extra work after feedback and concurrent
partner calls. **These are evaluation-only graphs, not the replacement product.**
The shipped single-agent graph is not passed off as a pair graph.

When implementing the pair runtime, its adapter must exercise its actual compiled
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
UV_CACHE_DIR=/workspace/.cache/uv uv run --frozen --extra tracing \
  python -m xp_agent.pair_evals money /path/to/toy-candidate \
  --stage reusable --output eval-results/money-acceptance.json
```

Candidate Python is copied into an isolated read-only, network-disabled test snapshot; it is never imported or executed on the host by this evaluator. Candidate files remain unchanged. The loader rejects symlinks, reserved evaluator/pytest configuration paths, missing adapters and snapshots over 400 KB. It ignores dot-directories, non-Python files and Python caches. The test image must contain any required runtime dependencies.

The independent test module is inserted by the evaluator, not read from candidate-provided tests. Acceptance requires the exact expected count of independent passing checks, no errors/failures/skips anywhere in the run and a successful runner exit. Candidate-owned passing tests cannot inflate the acceptance count. A candidate hash identifies the evaluated source snapshot. The report does not export source or raw runner output.

These checks are independent of the pair's own tests, but candidate code and pytest still share a process inside the container. They are for trusted toy code, not a hostile-code or tamper-proof evaluation boundary. Keep evaluator code and additional input examples out of the coding agents' workspace/context. A wrapper is the evaluated public API; reviewing wrapper changes remains necessary when comparing internal designs.

A passing Money result proves only that this candidate passed the selected independent behavior checks. It does not establish that two agents authored it, used TDD, held a business demo or followed a handoff protocol. The report keeps `runtime_verified: false` for that reason.

## Verify the evaluators

```sh
umask 022
UV_CACHE_DIR=/workspace/.cache/uv XP_DOCKER_TESTS=1 \
  uv run --frozen --extra tracing pytest \
  tests/test_pair_contracts.py tests/test_pair_money.py tests/test_pair_eval_cli.py \
  tests/test_pair_graph_probe.py -q
```

The Docker tests require the existing `xp-agent-tests:0.1` image. Without `XP_DOCKER_TESTS=1`, they are explicitly skipped; do not report that run as independent acceptance validation.

Tests include valid and invalid counterpart fixtures, wrong actors, absent role swaps, stale runner revisions, lost/reset/shared contexts, dropped prior tests, fabricated red/green, missing business answers, silent agreement changes, wrong demo output, duplicate feedback/actions, time/cycle limits and malformed evidence. Real Docker tests reject constant answers, mutation, inverted exchange conversion and missing API behavior while accepting correct implementations.

## What remains before qualifying the new product

The catalog records production qualification as unrun: actual pair-runtime scheduling and concurrent-write rejection; greenfield bootstrap; safe test evolution; persistent provider sessions and memory use; interrupted-node recovery and budget preservation; actual demo execution binding; fresh pair-specific Langfuse readback; repeated live model runs and a human business pilot.

Implement those integrations against the actual replacement runtime as it is built. Extend the versioned evidence schema with failing tests before accepting new event types or relaxing frozen-test rules. The existing synthetic pair scores and these offline record fixtures must never stand in for that integration evidence. Live calls require a separately authorized provider/account; none are triggered by this module.
