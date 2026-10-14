"""Only project execution backend: unprivileged network-disabled Docker tests."""
import json
from pathlib import Path
import tempfile
import uuid
from .policy import check_content, safe_path
from .process import run, ProcessError

HARNESS = r'''
import json, sys, pytest
sys.path.insert(0, '/workspace')
class Reporter:
    def __init__(self):
        self.data = dict(passed=[], failed=[], errors=[], skipped=[])
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        name = report.nodeid.replace('/workspace/', '')
        if report.skipped:
            self.data['skipped'].append(name)
        elif report.failed:
            key = 'failed' if call.when == 'call' and call.excinfo and call.excinfo.errisinstance(AssertionError) else 'errors'
            self.data[key].append(name)
        elif call.when == 'call':
            self.data['passed'].append(name)
    def pytest_collectreport(self, report):
        if report.failed:
            self.data['errors'].append(str(report.nodeid))
        elif report.skipped:
            self.data['skipped'].append(str(report.nodeid))
r = Reporter()
code = pytest.main(['-q', '-p', 'no:cacheprovider', '/workspace'], plugins=[r])
r.data['returncode'] = int(code)
print('\nXP_TEST_REPORT=' + json.dumps(r.data))
sys.exit(int(code))
'''


class DockerRunner:
    def __init__(self, image='xp-agent-tests:0.1', scratch=None, status=None):
        self.image = image
        self.status = status
        self.scratch = Path(scratch or Path.cwd() / '.xp-runs' / 'scratch').resolve()
        self.scratch.mkdir(parents=True, exist_ok=True, mode=0o700)

    def test(self, files, timeout):
        name = 'xp-test-' + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(dir=self.scratch) as tmp:
            workspace = Path(tmp) / 'workspace'
            workspace.mkdir(mode=0o755)
            Path(tmp).chmod(0o755)
            for path, content in files.items():
                safe_path(path)
                target = workspace / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                target.chmod(0o444)
            args = ['docker', 'run', '--rm', '--name', name, '--pull=never',
                    '--network=none', '--read-only', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--pids-limit=64',
                    '--memory=256m', '--cpus=1', '--user=65534:65534',
                    '--tmpfs=/tmp:rw,noexec,nosuid,size=32m',
                    '--mount', f'type=bind,src={workspace},dst=/workspace,readonly',
                    '-e', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                    '-w', '/workspace', '--entrypoint', 'python', self.image, '-c', HARNESS]
            try:
                result = run(args, timeout=min(timeout, 60), tick=self.status)
            finally:
                # Killing docker's client does not terminate its container.
                cleanup = run(['docker', 'rm', '-f', name], timeout=10)
                if cleanup.returncode and 'No such container' not in cleanup.stdout:
                    raise ProcessError('Container cleanup failed; inspect owned xp-test containers')
            marker = 'XP_TEST_REPORT='
            if marker not in result.stdout:
                raise ProcessError('Test runner failed without a report: ' + result.stdout[-1000:])
            raw = result.stdout.rsplit(marker, 1)[1].strip()
            try:
                report = json.loads(raw)
            except ValueError as exc:
                raise ProcessError('Invalid test report') from exc
            if result.returncode != report.get('returncode'):
                raise ProcessError('Test exit status/report mismatch')
            report['output'] = result.stdout[:16000]
            check_content(report['output'])
            return report
