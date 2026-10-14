import os
import pytest
from xp_agent.sandbox import DockerRunner

pytestmark = pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Set XP_DOCKER_TESTS=1 for real isolation checks')


def test_actual_container_runs_assertions_and_reports_errors():
    runner = DockerRunner()
    red = runner.test({'test_case.py': 'def test_missing_behavior():\n    assert 2 == 4\n'}, 30)
    assert red['failed'] == ['test_case.py::test_missing_behavior']
    assert not red['errors']
    broken = runner.test({'test_case.py': 'def test_error():\n    raise RuntimeError("broken setup")\n'}, 30)
    assert broken['errors']
    assert not broken['failed']


def test_actual_container_denies_host_reads_writes_network_and_credentials(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-must-not-leak')
    code = '''import os, socket, pathlib, pytest

def test_boundaries():
    assert os.getuid() != 0
    assert 'OPENAI_API_KEY' not in os.environ
    assert not pathlib.Path('/var/run/docker.sock').exists()
    assert not pathlib.Path('/Users').exists()
    with pytest.raises(OSError):
        pathlib.Path('/workspace/escape').write_text('x')
    with pytest.raises(OSError):
        socket.create_connection(('1.1.1.1', 443), timeout=0.2)
'''
    report = DockerRunner().test({'test_boundaries.py': code}, 30)
    assert report['returncode'] == 0, report


def test_hung_container_is_removed():
    from xp_agent.process import ProcessError
    with pytest.raises(ProcessError):
        DockerRunner().test({'test_hung.py': 'def test_hung():\n    while True: pass\n'}, 2)


def test_collection_skips_are_visible_to_xp_gates():
    from xp_agent.workflow import passing
    files = {'test_ok.py': 'def test_ok():\n    assert True\n',
             'test_optional.py': 'import pytest\npytest.skip("missing prerequisite", allow_module_level=True)\n'}
    report = DockerRunner().test(files, 30)
    assert report['skipped']
    assert not passing(report)
