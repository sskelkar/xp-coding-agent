"""The allowlist shared by the recorder and the isolated exporter."""

import math
import re

BASE_URL = "http://127.0.0.1:4000"
NAMES = {"xp.execute", "xp.evaluation", "model.propose", "run-tests"}
ENUMS = {
    "phase": {"baseline", "red", "green", "refactor", "final", "discuss", "bootstrap", "demo"},
    "provider": {"codex", "claude"},
    "auth": {"cli", "api-key", "oauth-token"},
    "status": {"ready", "verified", "blocked"},
    "outcome": {"ok", "error", "cancelled"},
    "actor": {"A", "B"},
    "mode": {"pair"},
}
NUMBERS = {
    "passed",
    "failed",
    "errors",
    "skipped",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
}
SCORE_NAMES = {
    "pair_ownership_valid",
    "handoff_state_valid",
    "independent_acceptance_passed",
    "evidence_complete",
    "tdd_sequence",
}
TDD_SEQUENCES = {"complete", "valid_partial", "violation", "insufficient_evidence"}


def attributes(values):
    safe = {}
    for name, value in values.items():
        if name in ENUMS and isinstance(value, str) and value in ENUMS[name]:
            safe[name] = value
        elif name in NUMBERS and type(value) in (
                int, float) and math.isfinite(value) and 0 <= value <= 10**12:
            safe[name] = value
        elif name == "usage_known" and type(value) is bool:
            safe[name] = value
        elif name == "model" and isinstance(value, str) and re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}", value):
            safe[name] = value
    return safe


def valid_score(name, value):
    if name == "tdd_sequence":
        return isinstance(value, str) and value in TDD_SEQUENCES
    return name in SCORE_NAMES and (value is None or type(value) is bool)
