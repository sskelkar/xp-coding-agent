# Outcome-led XP pair runtime

This branch is building the replacement workflow described in the [redesign plan](xp-ping-pong-redesign-plan.md). The legacy interactive/batch agent remains available while integration proceeds.

## Checkpoint 1: production graph routing

`xp_agent/pairing/graph.py` owns the phase transitions and actor selection. Agent A authors the first test, B implements it; after green/cleanup, B authors the next test and A implements. Candidate tests run in a separate graph node. Neither partner chooses who acts next. Business feedback uses an actual LangGraph interrupt.

The same `build_graph` function is used by the runtime and the conformance adapter. `ProbeOperations` replaces partner/runner operations with instrumented doubles, not a separate passing reference graph. The production routing passes the existing compiled-graph probe for normal role reversal, premature-green rejection, failed-green rejection, business interrupt and resume.

The probe runner originally reused a test identity across cycles. Production red validation correctly rejected that as a regression. Its controlled reports now preserve prior passing identities and introduce a distinct failing identity per cycle.

This routing checkpoint alone does not demonstrate model coding, workspace writes, persistent partner conversations or the Money result. Those operations and their integration evidence are being added in subsequent commits. SQLite checkpoint support is installed for durable local sessions.

## Checkpoint 2: partners, code and durable business boundaries

Two `Partner` objects have fixed A/B identities. Each request includes that partner's continuing conversation from graph state, the current source snapshot, the agreement revision and actual execution feedback. Provider processes may be fresh, but the application replays accumulated conversation instead of resetting the partner's history. Finite context limits stop explicitly rather than silently truncate.

`Operations` mediates all edits. Tests are append-only during red; green and cleanup cannot change accepted tests. A controlled bootstrap path handles missing modules/symbols: source scaffolding must preserve existing source and leave an actual assertion failure before green can begin. Project code and demonstrations execute only in Docker.

`Session` uses SQLite LangGraph checkpoints and a session writer lock. Business interrupts can be resumed through new database connections. The original project is captured into a private snapshot repository; accepted output is committed there for manual integration. This initial pair flow uses snapshots, not linked worktrees, and never writes the original project.

The scripted Money integration builds multiplication, reusable values and exact USD/CHF addition from an empty project through the production graph. It observes A-red/B-green, B-red/A-green, then A-red/B-green, executes real demonstrations, and passes all 33 independent Money acceptance checks. Scripted partners supply known proposals; this verifies runtime wiring, not live model coding quality. More recovery and evaluator bindings follow in the next checkpoint.
