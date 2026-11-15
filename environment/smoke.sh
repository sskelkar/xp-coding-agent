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

report=eval-results/pair-trace-smoke.json
uv run --frozen --extra tracing xp-agent eval --trace --output "$report"
uv run --frozen python - "$report" <<'PY'
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
report = json.loads(report_path.read_text())
trace_id = report["trace_id"]
export_path = report_path.parent / "pair-eval-traces" / f"trace-{trace_id}.export.json"
export = json.loads(export_path.read_text())
assert report["passed"] and export["exported"]
print("Pair evaluation and local trace export passed.")
PY
