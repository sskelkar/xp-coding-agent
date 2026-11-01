# Security boundaries and limitations

Use only trusted, non-sensitive toy projects in this milestone.

## Implemented controls

- Explicit file lists, bounded text sizes, known-secret-pattern rejection, descriptor-relative no-follow reads, and path validation. Real profiles, dot-directories, credentials and private-key paths are excluded.
- Codex runs with an empty temporary working directory, read-only sandbox, no inherited user configuration/rules, disabled shell/apps/plugins/hooks/browser/image tools, and structured output. Its saved sign-in stays with the host CLI. Attempts reported as command/file/MCP/web tool events reject the proposal.
- Claude Code runs in a temporary directory with an empty tool list, strict empty MCP configuration, disabled skills/hooks, no ordinary settings sources and requested no session persistence. Unexpected tool-use events are rejected; only the internal structured-output mechanism is permitted. API-key mode uses bare mode; saved-login/token modes retain CLI authentication. These are CLI restrictions, not a host OS sandbox. Managed policies can still constrain execution.
- Provider/model/auth mode are bound to approval. Explicit credential environment allowlists prevent ambient API-key/token overrides in saved-login mode. No automatic provider fallback occurs. Keys and tokens never enter prompts or plan/state records; raw failure diagnostics are withheld.
- Project test execution is a separate unprivileged Docker container: no network, read-only filesystem/workspace, no capabilities, no-new-privileges, bounded CPU/memory/PIDs, and size-limited temporary storage. No home directory, Docker socket, model credential or host environment is passed into the container.
- The trusted controller writes the checkout. Red and green permissions are structural checks, not model promises. All accepted tests remain unchanged during implementation/refactoring.
- Exact-plan hash approval and re-reading the source detect stale grants; interactive worktrees also bind the base commit. Selected-session continuation checks accepted files, record consistency and remaining budgets. A new run directory prevents accidentally overwriting previous evidence. Hashes protect consistency, not against a compromised local operator.
- Parent-enforced request/tool deadlines and bounded output; process-group termination; explicit Docker cleanup after success/failure/cancellation.
- Tracing disabled for the workflow. Raw provider event streams and credentials are not saved. Local state may contain source/test output and must remain private.

## Not guaranteed

Secret detection is incomplete. Semantic correctness and assertion strength cannot be proven by AST checks. Pytest and project code run in the same container process; malicious code may subvert its test reporter. Container isolation is not a formal security proof. Provider CLI behavior depends on the installed version; disabling tools and validating events is not a general-purpose data-loss-prevention boundary. The hosted provider receives the explicit context. No corporate-provider qualification has been done.

No arbitrary repositories, production data, remote services, automated merges/deployments, or provider fallback are supported. Company use requires separately approved inference access, policy mapping, stronger evaluation, and a validated execution profile.

## Publishing hygiene

Only implementation, synthetic fixtures, portable docs, tests, CI and dependency metadata are tracked. `.venv`, local planning notes, `.env`, credentials, authentication files, run records, eval result files and logs stay out of Git. Review `git diff --cached` and run a secret scanner before publishing changes; ignore rules alone are not a guarantee.

Git ignore rules cover working files, not Git notes, other refs or existing history. Local assistant tooling may record private contextual metadata under refs such as `refs/notes/ai`. Review the actual branch contents and publish that branch explicitly; do not include private notes or mirror every ref without a separate metadata review. Ignored files must not be force-added. Custom plan filenames outside ignored output directories still require an explicit publishing review.

Interactive Git discovery inventories tracked files only; clean tracked state is required. Runtime text capture is bounded and filtered separately from model context. Worktrees share repository metadata, and are not execution sandboxes; project tests receive a read-only filtered snapshot in Docker. Git hooks/fsmonitor are disabled for controller Git operations, and checkout-filter attributes are refused. Broader repository configurations are not qualified. Session records normally live outside the project under the user state directory and contain source; keep them private.

Worktree continuation/finalization checks the recorded branch and commit (including completed sessions), accepted file content and all tracked/index differences against the approved edit scope. Commits explicitly name approved paths. Private Git attributes are refused, system/global attribute sources are disabled, and tracked filter attributes are refused. This reduces accidental host-side filter execution; it does not qualify arbitrary hostile Git configurations. The supported profile remains trusted toy repositories.

## Optional local observability

Tracing is opt-in. The recorder excludes source, prompts, task text, paths, test names/output, raw replies, exception diagnostics and credentials. It accepts a fixed metadata schema, caps records/bytes and marks truncation. Artifact hashes reveal equality and can permit guessing low-entropy contents; metadata is still private. Trace files are Git-ignored, not encrypted or tamper-proof.

A separate exporter process reads explicitly configured local project keys from private stdin, with no model credentials, proxy variables or ambient OpenTelemetry configuration. It uses a private SDK/OpenTelemetry provider, fixed `http://127.0.0.1:4000`, restricted request destinations and no redirects/proxies. It cannot select cloud tracing through environment overrides. Regular export has a 20-second deadline and never changes the coding outcome. SDK auto-instrumentation of prompts/graph state is deliberately absent; LangSmith remains disabled.

Explicit scripted experiments require the optional SDK and local service. They execute synthetic fixtures through the existing Docker runner, transmit safe fixture IDs/summaries and keep keys out of environment/containers. Local Docker connection settings are forwarded to that isolated process. Neither local tracing nor CLI enterprise login establishes organizational compliance. Real ingestion/retrieval remains unverified until project keys are configured. See [setup and limitations](tracing.md).
