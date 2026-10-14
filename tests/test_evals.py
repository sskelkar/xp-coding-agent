import os
import pytest
from xp_agent.evals import evaluate

@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Requires real Docker execution')
def test_adversarial_fixture_evals_pass():
    report = evaluate()
    assert report['passed'], report
    names = {case['name'] for case in report['cases']}
    assert {'success', 'premature_green', 'scope_escape', 'weaken_tests', 'ambiguous_task', 'refactor_regression'} <= names


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Requires real Docker execution')
def test_claude_transport_contract_drives_real_xp_gates(monkeypatch):
    import json
    from xp_agent import claude_backend
    from xp_agent.backend import create_backend
    from xp_agent.evals import fixture_spec, reply, RED, GREEN, ORACLE
    from xp_agent.process import Result
    from xp_agent.sandbox import DockerRunner
    from xp_agent.workflow import execute, passing
    phases = []
    def transport(argv, **kwargs):
        context = json.loads(kwargs['stdin'].splitlines()[-1])
        phase = context['phase']
        phases.append(phase)
        proposal = {'red': reply('test_calc.py', RED), 'green': reply('calc.py', GREEN), 'refactor': reply()}[phase]
        return Result(0, json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                                     'structured_output': proposal}))
    monkeypatch.setattr(claude_backend, 'run', transport)
    runner = DockerRunner()
    state = execute(fixture_spec(), create_backend('claude', 'haiku'), runner)
    assert state['status'] == 'verified'
    assert phases == ['red', 'green', 'refactor']
    assert passing(runner.test({**state['files'], 'test_oracle.py': ORACLE}, 30))


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Requires Docker')
def test_claude_adapter_drives_primary_repl_discovery_approval_and_execution(monkeypatch):
    import json
    from xp_agent import claude_backend
    from xp_agent.backend import create_backend
    from xp_agent.evals import evaluate_repl, fixture_spec, reply, RED, GREEN
    from xp_agent.process import Result
    stages=[]
    def transport(argv, **kwargs):
        context=json.loads(kwargs['stdin'].splitlines()[-1])
        if 'inventory' in context:
            stages.append('discover')
            if 'calc.py' not in context['files']:
                value={'read_paths':['calc.py','test_calc.py'],'source_paths':[], 'test_paths':[], 'increments':[], 'blocked':''}
            else:
                value={'read_paths':[], 'source_paths':['calc.py'],'test_paths':['test_calc.py'],
                       'increments':[{'task':fixture_spec()['task'],'acceptance':fixture_spec()['acceptance']}], 'blocked':''}
        else:
            phase=context['phase']; stages.append(phase)
            value={'plan':{**reply(),'acceptance':fixture_spec()['acceptance'],'tradeoffs':['Keep numeric API']},
                   'red':reply('test_calc.py',RED),'green':reply('calc.py',GREEN),'refactor':reply()}[phase]
        return Result(0,json.dumps({'type':'result','subtype':'success','is_error':False,'structured_output':value}))
    monkeypatch.setattr(claude_backend,'run',transport)
    report=evaluate_repl(create_backend('claude','haiku','cli'))
    assert report['passed'], report
    assert report['original_unchanged'] and report['phase_progress_visible']
    assert stages==['discover','discover','plan','red','green','refactor']
