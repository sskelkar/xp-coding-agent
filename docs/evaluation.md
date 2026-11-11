# Evaluation design

The agent and its checks were developed in small test-first increments: executable failing cases for missing policy, process supervision, graph gates, project records, adapter validation, CLI, and fixture evals; implementation to green; then review/refactoring and regression checks. Import failures during initial test scaffolding were not treated as meaningful product red evidence.

## Layers

1. **Unit/workflow checks:** controlled proposals/reports exercise phase transitions, path/secret filtering, immutable tests, stale approvals, independent snapshot branches, deadlines, output bounds and CLI rejection.
2. **Real isolation checks:** run pytest in the actual configured container and test denied filesystem/network/credential access; distinguish assertion failure from setup exceptions; terminate a runaway test.
3. **Scripted adversarial evals:** real containers with deterministic model proposals for success, premature green, invalid red, path escape, test weakening, ambiguity and refactor regression.
4. **Live Codex smoke eval:** the same numeric behavior task uses actual model proposals. An independent acceptance test, withheld from model context, checks negative, fractional and additional positive inputs.

Failures and blocked runs are outcomes, not necessarily agent failures: adversarial cases pass the eval only if execution refuses the unsafe progression. Reports distinguish expected and actual status and include phase sequences and wall time.

The suite is intentionally small. No claim is made about general coding performance, production readiness or statistical superiority over another agent. Measure repeated runs and held-out tasks before drawing such conclusions. Exact monetary cost is not currently measured; account usage applies to live requests.

Run output is private/ignored. The checked-in documentation should summarize results without committing raw transcripts, source-bearing state or machine paths.

## Initial validation (2026-10-14)

- Full local suite: 31 tests passed with real Docker checks enabled.
- Scripted eval: all 7 scenarios passed their expected outcomes.
- Live `gpt-6-luna` fixture: baseline → red → green → refactor → final verified; additional withheld acceptance passed. This is one smoke run, not statistical evidence.
- User-facing plan/run smoke: created the review document, dedicated snapshot branch, final patch and local state; original fixture remained unchanged.
- Packaging: locked editable installation and CLI help verified.
- Publishing review: tracked-file secret scan identified only the intentionally synthetic key-pattern fixtures in `tests/test_policy.py`; no real credentials were identified. Local plans, model output, runtime records and environments are ignored.

## Session reporting validation (2026-10-14)

- New reporting behavior was developed from failing assertions for truthful rejected/accepted work reporting and source divergence detection.
- Regression coverage includes a cancelled run after green: the approved plan remains unchanged, the patch retains accepted work, and an external source change appears in the final report records.
- Full suite after reporting changes: 36 tests passed, including Docker isolation checks and all seven scripted adversarial scenarios. No live model rerun was needed; the model adapter and prompt were unchanged.

## Provider adapter validation (2026-10-14)

- Added provider selection, credential-environment separation, approval binding and error-output privacy checks through red–green development.
- Full suite: 51 tests passed, including real Docker isolation and scripted adversarial scenarios.
- A Claude transport contract eval uses controlled Claude-format responses with real Docker red/green/refactor/final gates and the held-out numeric oracle. This tests integration of the adapter and controller without claiming live model quality.
- Claude Code 2.1.150 accepted the configured command flags in a live startup check, but no live Claude XP cycle completed: the isolated saved-login mode was unauthenticated, and an explicit OAuth-token eval lacked the required exported token. No credentials were copied from CLI configuration. API-key modes and enterprise account qualification remain unverified against live accounts.
- The prior live Codex smoke remains the model-quality evidence for Codex. This change shares its existing prompt/schema through the abstraction without changing the XP contract; no additional Codex quota was intentionally consumed for a live eval.

## Pre-check-in review (2026-10-14)

- Full suite: 56 tests passed with Docker enabled. Review fixes cover pytest collection skips, malformed Codex event shapes and newly created broken symlinks invalidating approval. Each bug was reproduced with failing assertions before its fix.
- All five public/generated Mermaid diagrams rendered successfully with Mermaid 11.12.0, including the generated review plan. The runtime diagrams now show baseline/final failure, bounded retries, cancellation and blocked results without implying automatic resume.
- Local documentation links resolved. Source and wheel distributions built successfully; the source distribution includes the public contributor handoff/roadmap and excludes local planning notes and run records. The wheel includes both adapters.
- Git's candidate file list and representative ignore rules were checked. `detect-secrets` 1.5.0 scanned all tracked and unignored candidate files without network verification; its only findings were two deliberate synthetic fixtures in `tests/test_policy.py`. No employer identifiers or personal machine paths were found in candidate files.
- Git metadata is a separate publication surface: local AI notes contain private contextual references, while the ordinary project branch scan did not find employer identifiers. A normal explicit branch push does not include notes; do not publish private notes or use a mirror push without reviewing all refs. This review did not delete notes or publish anything.
- Claude's authenticated live cycle and live API-key modes remain unverified; see the provider validation section. Passing contract tests is not a substitute for that qualification.

## Interactive interface validation (2026-10-14)

The primary user path is now `xp-coding-agent` → REPL → bounded discovery → displayed plan → human approval → linked worktree/snapshot → sequential XP increments → report. Tests and evals exercise this path, not just the lower-level graph.

- Behavioral failing tests preceded discovery/worktree, resumable phase entry, REPL approval/progress and provider-preference fixes.
- The scripted eval retains seven adversarial controller cases and adds REPL success/rejection with real Git worktrees, Docker execution and an independent withheld acceptance test. Live evals use the same REPL path with the selected real provider.
- A real Docker integration test runs two independent behavior increments through the REPL, cancels before implementation, resumes with preserved attempts, verifies both behaviors on additional inputs and checks the main checkout is unchanged.
- The installed global editable executable was exercised from a terminal with startup and `/quit`, without a hosted request. An authenticated Codex cycle was subsequently verified as recorded below; existing Claude qualification limits remain.
- Current runtime bounds are small trusted Python/pytest projects, clean tracked Git baselines, tracked-only inventory, 400KB safe textual snapshots and six model-directed discovery rounds. Broader dependency environments and material feedback amendments remain unsupported.

Final interactive regression suite: **67 tests passed**, including Docker checks, primary-REPL success/rejection evals and the two-increment cancellation/resume integration. Packaging and public local documentation links were verified after the interface update.

## Final live REPL smoke (2026-10-14)

The final `gpt-6-luna`/saved-Codex-login eval passed through discovery, planning, in-shell approval, linked worktree execution, visible XP progress and independent withheld acceptance, preserving the original fixture. The live portion completed in approximately 29 seconds. Two preceding attempts exposed missing planning fields and redundant per-input increments; bounded planning feedback and clearer decomposition guidance were added without weakening XP gates. All nine deterministic eval cases also passed. This is one successful synthetic smoke, not a general coding-quality guarantee. Claude's authenticated live cycle remains unverified.

Final regression suite after the planning-repair behavior: **68 tests passed**, including real Docker integration. Both executable aliases are installed locally, distributions build, public documentation links resolve, diagrams render, and the secret scanner identifies only deliberately synthetic policy-test markers. No project commit or push was performed.

## Interactive pre-check-in review (2026-10-14)

- Final suite: **72 tests passed** with Docker enabled. Regression cases reproduced and fixed out-of-scope staged/excluded-file changes, unexpected revisions after verification, and private Git attributes bypassing the checkout-profile check. Commit finalization now explicitly names approved paths; completed revision identity is recorded.
- The actual Claude adapter now has primary-REPL integration coverage: controlled CLI events exercise discovery, planning, approval, progress, real worktree/Docker execution and withheld acceptance. Authenticated live Claude and live API-key modes remain unverified. The earlier successful live Codex REPL smoke remains valid evidence; this review changed Git reconciliation/finalization, not model prompts.
- The explainer includes a step-by-step testing/eval walkthrough covering pytest fixtures/test doubles, real REPL tests, Docker integration, nine scripted eval cases, live-provider evals, report interpretation and CI. Roadmap wording now distinguishes current interactive worktrees from retained batch snapshots and delivered continuation from future semantic feedback amendments.
- All five Mermaid diagrams (including generated plans) rendered. Public file links/heading anchors resolved, locked dependency sync and source/wheel builds passed. Public candidate files contained no personal machine paths or employer identifiers. The secret scanner found only the two deliberate synthetic policy fixtures.
- Git ignore checks cover credential/configuration state, logs, local plans/reviews, runtime records, eval outputs, caches and builds; no already-tracked file matched ignore rules. Ignore rules cannot protect arbitrary custom filenames, forced additions or Git metadata. Private AI notes remain separate from the intended branch publication and must not be pushed with a mirror/all-ref operation.

## Local observability foundation (2026-11-01)

- Meaningful failing assertions preceded the recorder, execution-evidence integration, REPL trace command, validated usage capture, truncation classification, failed score-upload handling, direct SDK trace links and experiment cancellation cleanup behavior.
- Full deterministic suite with the optional tracing dependency and Docker enabled: **92 tests passed**. No hosted inference requests were made. Locked dependency sync and source/wheel builds passed; local documentation links resolved, and packaged artifacts contained all four tracing modules without local run artifacts.
- The SDK contract tests use in-memory OpenTelemetry export and mocked HTTP. They verify original timestamps/parent identities, session grouping, typed generation observations, safe fixture inputs/results, score creation, complete-suite gating and trace URL construction. They do not establish server ingestion.
- A primary-REPL test enables tracing, approves a plan, cancels in green and resumes. Attempts remain consumed, session identity persists, the resumed trace references its predecessor, and scores move from valid partial to complete only after the remaining gates. Simulated export failures do not prevent continuation or expose raw errors.
- The SDK experiment was also exercised against all **13 real scripted fixtures**: nine existing controller/REPL cases using Git/Docker, plus four synthetic future pair-contract cases. Controller child observations and withheld acceptance were verified using memory export/mocked HTTP, without local project keys. No actual two-agent execution or context isolation was implemented or claimed.
- Metadata allowlists, record/byte caps, environment isolation, local destination restrictions, ignored trace artifacts and failure/cancellation paths have deterministic coverage. Hash-based evidence assumes trusted controller/runner reports and cannot prove test semantics or supply a tamper-proof audit trail.
- **Pending by user choice:** configure a dedicated local Langfuse project/key pair, send a synthetic trace/experiment, retrieve observations/scores with the Langfuse CLI, and audit hierarchy, safe fields, session links and experiment UI. No successful live ingestion/score retrieval is claimed. Claude/live account qualification remains as previously recorded.

## Local Langfuse ingestion audit

- Created a dedicated local XP project and project-scoped key pair using the existing local operator account. Keys are stored in an ignored, owner-readable-only local environment file; no real credential values or deployment identifiers are recorded here. Other applications' keys/configuration were preserved.
- On Langfuse **4.72.0 OSS**, exercised actual REPL success/rejection plus the **13-case SDK experiment**, using real Git/Docker fixtures and no hosted LLM requests. Retrieved observations, experiment items and scores through the Langfuse CLI, then checked the experiment UI and successful trace page.
- The audited successful set contains **16 traces, 215 observations and 78 scores**. Every locally recorded REPL observation arrived with its original parent/type, safe metadata and timestamps within API precision. Plan/execution session identities matched; approved/rejected planning outcomes and complete TDD execution scores were retrieved. All 13 experiment cases and the required suite gate passed; independent fixture acceptance passed. Deliberately invalid synthetic pair cases correctly have false protocol scores while their detection cases pass.
- The first experiment exposed the SDK's automatic `public_key` instrumentation-scope attribute becoming observation metadata. A failing regression test reproduced it. The transport now copies spans with scope attributes removed, preserving scope name/version, timing, ancestry and safe observation data. A corrected full experiment was sent and retrieved; its observations contained neither project key values nor source/task text, filenames or personal paths. The initial diagnostic experiment remains local historical test data; the privacy result above applies to the corrected run.
- Ordinary traces use environment `local`; the SDK's experiment runner uses `sdk-experiment`. Both were verified against the same loopback-only service. Synthetic model usage stays unknown; this audit establishes ingestion/integration, not live-provider token accuracy or coding quality.
- Full regression suite after the metadata fix: **93 tests passed**, including Docker integration and SDK experiments with mocked HTTP. Public docs now describe the verified setup and explicit loading of an optional private environment file. Local audit records/screenshots remain ignored; real provider/account qualification remains separate.


## Pair-redesign evaluation foundation

- Added an offline versioned controller-record grader, five public Money business scenario scripts, and independent Docker Money acceptance through an explicit public adapter contract. This does not change the single-agent runtime or implement two-agent orchestration.
- Evaluator self-tests distinguish valid records from wrong ownership, missing role rotation, stale revisions, false red/green, lost or reset context references, weakened tests, missing business responses, invalid demos, duplicate actions and cadence violations. Importable stubs first produced meaningful failing assertions before implementations were added.
- The new evaluation coverage comprises **49 tests**, including **seven real Docker integration cases** and **seven compiled-LangGraph probe tests**. Correct Money implementations passed; constant results, unintended mutation, inverted exchange conversion and missing API behavior failed independent acceptance. No hosted model calls were made.
- The complete deterministic suite, with tracing dependencies and Docker tests enabled, passed **142 tests**. Source/wheel builds passed, and the wheel contains all six new evaluation modules. A separate CLI exchange smoke passed **33 independent checks**; offline grading of the clearly labeled synthetic positive record fixture also passed.
- The compiled-graph probe observed actual partner invocations and runner calls in distinct LangGraph node/step execution contexts, plus a real checkpoint interrupt and resume. Deliberately broken graphs failed for incorrect handoffs, missing tests, ignored gate failures, missing interrupts, extra post-feedback work and overlapping calls. A correct-looking manual loop inside one node also failed: call order alone cannot establish graph orchestration. No LLM judge was used.
- These results establish evaluator behavior and candidate acceptance, not a successful pair runtime. The catalog reports actual graph scheduling, persistent provider histories, memory use, guarded test evolution, crash recovery, real business demos, pair-specific Langfuse readback and live qualification as unrun. All tool reports keep runtime qualification false. See [commands, evidence schema and limitations](pair-evaluations.md).
