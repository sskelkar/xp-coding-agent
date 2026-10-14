# Security boundaries and limitations

Use only trusted, non-sensitive toy projects in this milestone.

## Implemented controls

- Explicit file lists, bounded text sizes, known-secret-pattern rejection, descriptor-relative no-follow reads, and path validation. Real profiles, dot-directories, credentials and private-key paths are excluded.
- Codex runs with an empty temporary working directory, read-only sandbox, no inherited user configuration/rules, disabled shell/apps/plugins/hooks/browser/image tools, and structured output. Its saved sign-in stays with the host CLI. Attempts reported as command/file/MCP/web tool events reject the proposal.
- Project test execution is a separate unprivileged Docker container: no network, read-only filesystem/workspace, no capabilities, no-new-privileges, bounded CPU/memory/PIDs, and size-limited temporary storage. No home directory, Docker socket, model credential or host environment is passed into the container.
- The trusted controller writes the checkout. Red and green permissions are structural checks, not model promises. All accepted tests remain unchanged during implementation/refactoring.
- Exact-plan hash approval and re-reading the source prevent stale grants. A new run directory prevents accidentally overwriting previous evidence. Hashes protect consistency, not against a compromised local operator.
- Parent-enforced request/tool deadlines and bounded output; process-group termination; explicit Docker cleanup after success/failure/cancellation.
- Tracing disabled for the workflow. Raw Codex event streams and credentials are not saved. Local state may contain source/test output and must remain private.

## Not guaranteed

Secret detection is incomplete. Semantic correctness and assertion strength cannot be proven by AST checks. Pytest and project code run in the same container process; malicious code may subvert its test reporter. Container isolation is not a formal security proof. Codex CLI behavior depends on the installed version; disabling tools and validating events is not a general-purpose data-loss-prevention boundary. The hosted provider receives the explicit context. No corporate-provider qualification has been done.

No arbitrary repositories, production data, remote services, automated merges/deployments, or provider fallback are supported. Company use requires separately approved inference access, policy mapping, stronger evaluation, and a validated execution profile.

## Publishing hygiene

Only implementation, synthetic fixtures, portable docs, tests, CI and dependency metadata are tracked. `.venv`, local planning notes, `.env`, credentials, authentication files, run records, eval result files and logs stay out of Git. Review `git diff --cached` and run a secret scanner before publishing changes; ignore rules alone are not a guarantee.
