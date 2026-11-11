# Outcome-led XP pair runtime

This branch is building the replacement workflow described in the [redesign plan](xp-ping-pong-redesign-plan.md). The legacy interactive/batch agent remains available while integration proceeds.

## Checkpoint 1: production graph routing

`xp_agent/pairing/graph.py` owns the phase transitions and actor selection. Agent A authors the first test, B implements it; after green/cleanup, B authors the next test and A implements. Candidate tests run in a separate graph node. Neither partner chooses who acts next. Business feedback uses an actual LangGraph interrupt.

The same `build_graph` function is used by the runtime and the conformance adapter. `ProbeOperations` replaces partner/runner operations with instrumented doubles, not a separate passing reference graph. The production routing passes the existing compiled-graph probe for normal role reversal, premature-green rejection, failed-green rejection, business interrupt and resume.

The probe runner originally reused a test identity across cycles. Production red validation correctly rejected that as a regression. Its controlled reports now preserve prior passing identities and introduce a distinct failing identity per cycle.

This routing checkpoint alone does not demonstrate model coding, workspace writes, persistent partner conversations or the Money result. Those operations and their integration evidence are being added in subsequent commits. SQLite checkpoint support is installed for durable local sessions.
