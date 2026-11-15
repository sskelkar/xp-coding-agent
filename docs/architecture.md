# Architecture

The CLI starts a pair session or runs an evaluation. The session supplies a controller and a SQLite checkpointer to the production LangGraph. The graph selects the partner, runs the controller's gates, and pauses for business feedback. See [the routing diagram](pair-runtime.md#production-graph-routing).

| Component | Responsibility |
| --- | --- |
| [Pair graph](../xp_agent/pairing/graph.py) | Registers the decision nodes and assigns the test author and implementer for each cycle. |
| [Pair controller](../xp_agent/pairing/controller.py) | Requests proposals, validates phase-specific edits, runs tests, and records accepted evidence. |
| [Session](../xp_agent/pairing/session.py) | Owns the snapshot repository, writer lock, SQLite checkpoints, and delivery artifacts. |
| [Partner](../xp_agent/pairing/partners.py) | Sends phase instructions and the continuing history to the selected provider. |
| [Providers](../xp_agent/providers/) | Call Codex or Claude with a schema, an explicit auth mode, and a bounded subprocess. |
| [Workspace](../xp_agent/workspace.py), [policy](../xp_agent/policy.py), and [sandbox](../xp_agent/sandbox.py) | Filter project files, validate edits, write the private checkout, and run pytest in Docker. |
| [Evaluation](../xp_agent/evaluation/pair/) | Probes production routing with test doubles, grades saved evidence, and checks the candidate independently. |
| [Tracing](../xp_agent/tracing/) | Captures allowlisted metadata and exports it through a separate local-only process. |

The original project is read into a private snapshot. The controller writes that snapshot, while Docker receives a separate read-only copy of the candidate files without Git metadata. The model provider receives the selected context via its tool-restricted CLI. [Security boundaries](security.md)

A working demo is a test run against the current accepted files. The graph pauses with the actual values for user feedback. SQLite persists the pending interrupt and the continuing conversation. Resumption binds the response to the current interrupt and retains the original settings. [Runtime details](pair-runtime.md)
