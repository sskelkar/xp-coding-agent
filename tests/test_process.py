import os
import sys
import time
import pytest
from xp_agent.process import run, ProcessError


def test_deadline_stops_silent_worker():
    start = time.monotonic()
    with pytest.raises(ProcessError, match='deadline'):
        run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.15)
    assert time.monotonic() - start < 3


def test_output_limit_stops_runaway_worker():
    with pytest.raises(ProcessError, match='output'):
        run([sys.executable, '-c', 'print("x" * 100000)'], timeout=3, max_output=1000)


def test_explicit_environment_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv('EXAMPLE_SECRET', 'do-not-pass')
    result = run([sys.executable, '-c', 'import os; print(os.getenv("EXAMPLE_SECRET", "absent"))'], timeout=3, env={})
    assert result.stdout.strip() == 'absent'


def test_worker_closing_output_cannot_escape_deadline():
    with pytest.raises(ProcessError, match='deadline'):
        run([sys.executable, '-c', 'import os,time; os.close(1); os.close(2); time.sleep(30)'], timeout=0.15)
