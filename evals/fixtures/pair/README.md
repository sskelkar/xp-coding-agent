# Pair evaluator fixture

`valid-records.json` is a deliberately synthetic positive input for the offline
record grader. Placeholder source snapshots and declared runner reports are not
real two-agent execution evidence. Do not use this fixture as a runtime pass.

The [scenario catalog](../../../xp_agent/evaluation/pair/scenarios.py) describes
the Money business scenarios. The [Money evaluator](../../../xp_agent/evaluation/pair/money.py)
runs its acceptance tests inside Docker, separately from the coding pair's
own tests.

See [evaluation tools](../../../docs/pair-evaluations.md) for commands, the schema,
limitations, and runtime checks that remain unrun.
