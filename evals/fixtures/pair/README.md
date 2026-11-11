# Pair evaluator fixture

`valid-records.json` is a deliberately synthetic positive input for the offline
record grader. Placeholder source snapshots and declared runner reports are not
real two-agent execution evidence. Do not use this fixture as a runtime pass.

Business scripts live in `xp_agent/pair_evals/scenarios.py`; the Money oracle is
inserted separately by `xp_agent/pair_evals/money.py` inside Docker. Neither should
be copied into a coding partner's candidate workspace as solution guidance.

See [evaluation tools](../../../docs/pair-evaluations.md) for commands, the schema,
limitations, and runtime checks that remain unrun.
