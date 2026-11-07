#!/usr/bin/env bash
set -euo pipefail
cd /workspace/xp-coding-agent
export UV_CACHE_DIR=/workspace/.cache/uv
export XDG_STATE_HOME=/workspace/.cloud-setup/state
umask 022
bash /workspace/.cloud-setup/langfuse/start.sh
set -a
source /workspace/.cloud-setup/langfuse/agent.env
set +a
uv run --frozen --extra tracing xp-agent eval --experiment --output eval-results/langfuse-local-experiment.json
uv run --frozen --extra tracing python - <<'PY'
from xp_agent.evals import evaluate_repl
assert evaluate_repl(trace=True)['passed']
assert evaluate_repl(approve=False, trace=True)['passed']
print('Traced REPL success and rejection checks passed.')
PY
audit_log="$(mktemp)"
trap 'rm -f "$audit_log"' EXIT
for attempt in {1..30}; do
  if python /workspace/.cloud-setup/langfuse/audit.py >"$audit_log" 2>&1; then
    cat "$audit_log"
    exit 0
  fi
  sleep 2
done
cat "$audit_log" >&2
exit 1

