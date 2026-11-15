# Local tracing with Langfuse

Add `--trace` to an interactive pair run or the scripted evaluation. Install the optional SDK and configure a local Langfuse project at `http://127.0.0.1:4000`.

```sh
uv sync --frozen --extra tracing
uv run --frozen --extra tracing xp-agent pair /path/to/project --trace
uv run --frozen --extra tracing xp-agent eval --trace --output eval-results/pair.json
```

Provide the local project's `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in the shell. These keys are separate from provider authentication. For the managed setup, see [environment instructions](../environment/README.md).

The [recorder](../xp_agent/tracing/__init__.py) writes `trace-<id>.json` under the session's `traces/` directory. An interactive run writes one trace per advance of the graph, grouped by the session ID. Enable `--trace` again when resuming if you want to record the new invocation. Evaluation records a run under `pair-eval-traces/` beside the report and includes the trace ID in its JSON result.

The recording includes allowlisted metadata such as phase, partner identity, timestamps, and validated provider token counts. Source, prompts, conversation, test output, and secrets stay outside the trace. Usage stays unknown when the provider omits valid counts.

The [exporter](../xp_agent/tracing/exporter.py) runs in a separate process with a restricted environment and fixed loopback destination. Successful export writes `trace-<id>.export.json` alongside the recording. On export failure, inspect the local trace, check that Langfuse is reachable at `127.0.0.1:4000`, and confirm that the shell has the project's keys and the tracing extra installed. Export failure leaves the session or evaluation verdict intact.

Evaluation scores come from evidence grading and independent acceptance. The trace can report role ownership, handoff validity, independent acceptance, completeness, and TDD sequence. Truncation marks the evidence incomplete.
