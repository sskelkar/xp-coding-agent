# Recreate the XP Coding Agent cloud environment

This kit recreates the development environment and local Langfuse deployment validated with repository commit `75d5a86b8b51eb1277d29d32f53761b6a4214264`. It contains no generated credentials or application data.

## Requirements

- A Linux cloud workspace with the checkout at `/workspace/xp-coding-agent`.
- Python 3.11+, uv, Git, Docker with a working local socket, and Docker Compose v2.
- Approximately 40 GB free disk for image extraction/builds and local service data; the validated host has 5 CPUs and 33 GB RAM.
- HTTPS access to PyPI, Docker Hub and its download hosts. The setup preserves the inherited proxy and CA trust. The managed cloud package-manager network preset was sufficient.
- The system CA bundle at `/etc/ssl/certs/ca-certificates.crt`.

Use the existing checkout. Cloud tasks are already isolated; do not create a Git worktree unless explicitly requested. Do not reset existing work or change application source, tests, manifests or lockfiles for setup.

## Install or refresh

From this checkout:

```bash
bash environment/setup.sh
```

The script installs frozen dependencies with the tracing extra, builds the isolated test image, builds Python distributions, generates private local service credentials if absent, pulls service images, and starts Langfuse. The cloud CA is passed to the test-image build as a temporary BuildKit secret; TLS verification stays enabled.

The checkout path is currently fixed to `/workspace/xp-coding-agent`, and local setup files live in `/workspace/.cloud-setup`. For a different layout, adapt those paths in a copy of the setup script before running it.

Services: Langfuse web/worker 4.72.0, PostgreSQL 17, ClickHouse 25.12, Redis 7, and a digest-pinned official SeaweedFS image for S3-compatible storage. SeaweedFS avoids image registries blocked by this cloud's network policy. Only the web service publishes a port, on loopback port 4000. No external account, hosted model key or paid service is required.

## Restart and use

Live processes do not survive environment restoration. Restart the services:

```bash
bash /workspace/.cloud-setup/langfuse/start.sh
```

Initialize each shell used for development:

```bash
cd /workspace/xp-coding-agent
export UV_CACHE_DIR=/workspace/.cache/uv
export XDG_STATE_HOME=/workspace/.cloud-setup/state
umask 022
set -a
source /workspace/.cloud-setup/langfuse/agent.env
set +a
uv run --frozen --extra tracing xp-agent --trace
```

The cloud default `umask 077` prevents the Docker test user from reading generated fixture directories; use `022` for these commands. Private parent directories still protect run records.

The generated local operator login is stored in the private service `.env` file, using the `LANGFUSE_INIT_USER_EMAIL` and `LANGFUSE_INIT_USER_PASSWORD` entries. Inspect them only in your own terminal if needed for the local UI. Do not paste them into chat or Git. Hosted Codex/Claude calls require their own authorized account and are separate from this local tracing setup.

## Verify

```bash
bash environment/smoke.sh
```

This runs all 13 SDK experiment cases, traced REPL success/rejection using scripted proposals and real Git/Docker, then retrieves observations/scores from the local Langfuse API. It verifies passing suite/TDD scores, trace parent timing, plan/execution session grouping, and absence of local project keys or fixture source in observations. It makes no hosted model calls.

For the complete development suite:

```bash
umask 022
UV_CACHE_DIR=/workspace/.cache/uv XP_DOCKER_TESTS=1 \
  uv run --frozen --extra tracing pytest -q
```

The original local audit retrieved 16 traces, 215 observations and 78 scores. Reruns add records; those counts are not fixed assertions. The audit checks stored project data rather than selecting only the newest run, so use a fresh project when an isolated ingestion audit is required.

## Persistence and secrets

Generated credentials are under `/workspace/.cloud-setup/langfuse` in `.env`, `agent.env` and `s3.json`, with mode 600. Persistent service data is stored in Docker named volumes under Compose project `xp-langfuse`. Preserve both credentials and volumes together. Do not copy generated credentials into this kit or commit them.

To stop services while keeping data:

```bash
docker compose -p xp-langfuse \
  -f /workspace/.cloud-setup/langfuse/compose.yml \
  --env-file /workspace/.cloud-setup/langfuse/.env stop
```

Do not use `down -v` unless intentionally deleting local trace data.

The installation and startup instructions are also stored in the cloud environment configuration. This kit provides a reproducible path independent of a prepared machine snapshot. Keep generated credentials and service data outside Git; only the scripts and this guide belong in the repository.

