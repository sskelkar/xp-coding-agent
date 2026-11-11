import json
from xp_agent.cli import main


def test_cli_help_lists_plan_run_and_evals(capsys):
    import pytest
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert all(name in output for name in ('plan', 'run', 'eval'))


def test_cli_rejects_unapproved_run_before_backend_or_workspace(tmp_path, capsys):
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps({'approval_id': 'not-approved'}))
    code = main(['run', str(path), '--approve', 'wrong', '--output', str(tmp_path / 'result')])
    assert code == 2
    assert not (tmp_path / 'result').exists()


def test_run_preserves_plan_and_reports_partial_cancelled_work(tmp_path, monkeypatch):
    from xp_agent import cli
    from xp_agent.project import create_plan
    from xp_agent.evals import BASE, RED, GREEN, ScriptedBackend, reply

    project = tmp_path / 'project'
    project.mkdir()
    for name, content in BASE.items():
        (project / name).write_text(content)
    class Planner:
        model = 'fixture'
        def propose(self, *args):
            return {'edits': [], 'rationale': 'Small change', 'blocked': '',
                    'acceptance': ['Double inputs'], 'tradeoffs': ['No new dependencies']}
    plan = create_plan(project, 'Double inputs', ['calc.py'], ['test_calc.py'], Planner())
    original_plan = json.dumps(plan, sort_keys=True)
    class Runner:
        def __init__(self, *args, **kwargs):
            self.calls = 0
        def test(self, files, timeout):
            self.calls += 1
            if self.calls == 4:
                (project / 'calc.py').write_text('# external change\n')
                raise KeyboardInterrupt
            return {'passed': ['zero'] if self.calls < 3 else ['zero', 'positive'],
                    'failed': ['positive'] if self.calls == 2 else [], 'errors': [], 'skipped': [],
                    'returncode': 1 if self.calls == 2 else 0, 'output': ''}
    monkeypatch.setattr(cli, 'DockerRunner', Runner)
    output = tmp_path / 'run'
    assert cli.perform_run(plan, output, ScriptedBackend([reply('test_calc.py', RED), reply('calc.py', GREEN), reply()])) == 2
    assert json.dumps(plan, sort_keys=True) == original_plan
    assert json.loads((output / 'approved-plan.json').read_text()) == plan
    assert plan['approval_id'] in (output / 'plan.md').read_text()
    report = (output / 'result.md').read_text()
    assert '# Run result: cancelled' in report
    assert '- green (attempt 1): calc.py' in report
    assert '- refactor (attempt' not in report
    assert json.loads((output / 'divergence.json').read_text())['changed'] == ['calc.py']
    assert 'return x * 2' in (output / 'changes.patch').read_text()


def test_cli_routes_provider_model_and_auth_to_planning(tmp_path, monkeypatch):
    from xp_agent import cli
    from xp_agent.process import Result
    called = {}
    def factory(provider='codex', model=None, auth='cli', status=None):
        called.update(provider=provider, model=model, auth=auth)
        return object()
    monkeypatch.setattr(cli, 'create_backend', factory, raising=False)
    monkeypatch.setattr(cli, 'run', lambda *a, **k: Result(0, 'image-id'))
    monkeypatch.setattr(cli, 'create_plan', lambda *a, **k: {'approval_id': 'test'})
    monkeypatch.setattr(cli, 'render_plan', lambda p: 'plan')
    assert main(['plan', str(tmp_path), '--task', 'Change', '--source', 'calc.py', '--tests', 'test_calc.py',
                 '--provider', 'claude', '--model', 'sonnet', '--auth', 'api-key',
                 '--output', str(tmp_path / 'plan.json')]) == 0
    assert called == {'provider': 'claude', 'model': 'sonnet', 'auth': 'api-key'}


def test_run_uses_approved_provider_without_falling_back(tmp_path, monkeypatch):
    from xp_agent import cli
    from xp_agent.project import create_plan
    from xp_agent.backend import BackendError
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'calc.py').write_text('x = 1\n')
    (project / 'test_calc.py').write_text('def test_x():\n    assert True\n')
    class Planner:
        provider, model, auth = 'claude', 'sonnet', 'api-key'
        def propose(self, *args):
            return {'edits': [], 'rationale': 'Simple', 'blocked': '', 'acceptance': ['Expected behavior'],
                    'tradeoffs': ['No dependencies']}
    plan = create_plan(project, 'Task', ['calc.py'], ['test_calc.py'], Planner())
    calls = []
    class Unavailable:
        def propose(self, *args):
            raise BackendError('Provider quota unavailable')
    def factory(provider, model, auth, status=None):
        calls.append((provider, model, auth))
        return Unavailable()
    class Runner:
        def __init__(self, *args, **kwargs): pass
        def test(self, *args):
            return {'returncode': 0, 'passed': ['test_x'], 'failed': [], 'errors': [], 'skipped': []}
    monkeypatch.setattr(cli, 'create_backend', factory)
    monkeypatch.setattr(cli, 'DockerRunner', Runner)
    output = tmp_path / 'run'
    assert cli.perform_run(plan, output) == 2
    assert calls == [('claude', 'sonnet', 'api-key')]
    assert 'Provider quota unavailable' in (output / 'result.md').read_text()
    assert json.loads((output / 'state.json').read_text())['files'] == plan['files']


def test_experiment_refuses_live_or_explicit_no_trace_before_any_request(capsys):
    assert main(['eval','--experiment','--live'])==2
    assert main(['eval','--experiment','--no-trace'])==2
    assert 'requires tracing' in capsys.readouterr().err


def test_default_entry_point_uses_pair_flow_and_legacy_repl_is_explicit(monkeypatch):
    from xp_agent.pairing import cli as pair_cli
    from xp_agent import repl
    monkeypatch.setattr(pair_cli,'main',lambda args:23)
    monkeypatch.setattr(repl,'shell',lambda *a,**k:17)
    assert main([])==23
    assert main(['repl'])==17
