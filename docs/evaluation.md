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
