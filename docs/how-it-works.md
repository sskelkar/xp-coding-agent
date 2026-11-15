# Read the agent from the entry point

1. [cli.py](../xp_agent/cli.py) dispatches to the [pair CLI](../xp_agent/pairing/cli.py). The pair CLI creates or opens a session and turns graph interrupts into terminal prompts.
2. [session.py](../xp_agent/pairing/session.py) captures the safe content of the target project, creates a private Git snapshot, and opens a SQLite checkpointer under a writer lock. Each advance reads the current graph state and either reports a pending prompt or resumes the graph with the supplied answer.
3. [graph.py](../xp_agent/pairing/graph.py) controls the sequence. It confirms the outcome, checks the baseline, calls both partners to discuss the next behavior, and alternates test author and implementer across cycles. The node names and saved state fields are the keys used in checkpoints.
4. [controller.py](../xp_agent/pairing/controller.py) implements each action. It gives the proposed files to the [Docker runner](../xp_agent/sandbox.py) and changes the accepted snapshot only after the graph says the test gate passed. Greenfield bootstrap can add scaffolding so the test can import and call the new API. The scaffold must leave a real assertion failure.
5. [partners.py](../xp_agent/pairing/partners.py) builds a structured request from the confirmed outcome, current files, assigned phase, prior messages, and execution feedback. The [provider adapters](../xp_agent/providers/) handle transport, auth, and bounded execution. The graph controls all actions after a response.

Demos and business questions use the same graph interrupt mechanism as outcome confirmation. The session writes a patch and commits accepted output in the private snapshot repository after the user accepts a working demo. [Runtime guide](pair-runtime.md)

## What passes between components

| Data | Where to look |
| --- | --- |
| Accepted files, current phase, cycle number, pending proposal, required tests, and remaining budget | `PairState` in [graph.py](../xp_agent/pairing/graph.py). The controller reads these values at each step and returns updates for LangGraph to checkpoint. |
| Model action, explanation, file edits, and demo examples | `SCHEMA` and `parse_reply()` in [partners.py](../xp_agent/pairing/partners.py). Actions are `comment`, `question`, `edit`, and `demo`. Edits carry complete file contents. |
| CLI JSON response | `request(prompt, schema, timeout)` on either [CodexBackend](../xp_agent/providers/codex.py) or [ClaudeBackend](../xp_agent/providers/claude.py). Both satisfy the same interface for `Partner`. |
| Test outcome | [DockerRunner](../xp_agent/sandbox.py) reports pytest's exit code and the identities of passing, assertion-failing, errored, and skipped tests. The graph checks these before the controller accepts a candidate. |
| Demo output | [demos.py](../xp_agent/pairing/demos.py) turns examples into temporary tests and reads their observed results. |
| Checkpoint versus evidence | The SQLite database is used to resume a session. The JSON evidence is used for offline grading of accepted transitions. [Session artifacts](pair-runtime.md#review-the-result-or-resume) |

## Follow a test or evaluation

- [Pair controller tests](../tests/pairing/test_pair_operations.py) substitute partner and runner dependencies, then verify interruption and edit boundaries.
- [Pair integration tests](../tests/pairing/test_pair_money_runtime.py) drive production sessions with scripted partners and real Docker. They cover bootstrap retries, role rotation, independent acceptance, and reopening a waiting session.
- [Evaluation tests](../tests/evaluation/) feed the graders malformed evidence and use known correct and incorrect Money implementations.
- [Tracing tests](../tests/tracing/) verify allowlisting, parent-child timing, bounded recordings, and exporter behavior with mock HTTP and in-memory spans.

The [evaluation runner](../xp_agent/evaluation/pair/runtime.py) starts the same pair session used by the terminal. It applies the [evidence grader](../xp_agent/evaluation/pair/contracts.py), observes production routing through the [graph probe](../xp_agent/evaluation/pair/graph_probe.py), and uses an [independent Docker oracle](../xp_agent/evaluation/pair/money.py) for candidate correctness. [Evaluation commands](pair-evaluations.md)
