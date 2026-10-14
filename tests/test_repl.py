from xp_agent import repl
from test_session import project, Planner
from test_workflow import Backend, Runner, change, result


def test_repl_task_discovery_approval_and_real_worktree(tmp_path):
    root = project(tmp_path)
    replies = iter(['Double inputs', 'approve', '/quit'])
    messages = []
    class Partner(Planner):
        def __init__(self): self.coding = Backend([])
        def propose(self, phase, *args):
            if phase == 'plan': return super().propose(phase, *args)
            if phase == 'red': return change('test_calc.py', (root / 'test_calc.py').read_text() + '\ndef test_two():\n    assert double(2) == 4\n')
            if phase == 'green': return change('calc.py', 'def double(x):\n    return x * 2\n')
            return change()
    green = result(passed=('test_calc.py::test_zero','test_calc.py::test_two'))
    code = repl.shell(root, backend=Partner(), image='fixture', output_root=tmp_path / 'runs',
                      runner_factory=lambda *a, **k: Runner([result(),result(failed=('test_calc.py::test_two',)),green,green,green]),
                      read=lambda prompt: next(replies), write=messages.append)
    assert code == 0
    assert any('GREEN: accepted' in m for m in messages)
    assert any('verified' in m for m in messages)
    assert (root / 'calc.py').read_text() == 'def double(x):\n    return x\n'


def test_repl_does_not_execute_without_human_approval(tmp_path):
    root = project(tmp_path)
    replies = iter(['Double inputs', 'reject', '/quit'])
    def forbidden(*args, **kwargs): raise AssertionError('Tests must not execute before approval')
    repl.shell(root, backend=Planner(), image='fixture', output_root=tmp_path/'runs',
               runner_factory=forbidden, read=lambda p: next(replies), write=lambda m: None)
    assert not list((tmp_path/'runs').glob('*/workspace')) if (tmp_path/'runs').exists() else True


def test_repl_multiple_increments_and_restart_resume(tmp_path):
    root = project(tmp_path)
    class Partner(Planner):
        def __init__(self): self.interrupted = False
        def select(self, context, timeout):
            choice = super().select(context, timeout)
            if choice['increments']:
                choice['increments'].append({'task':'Double three','acceptance':['double(3) == 6']})
            return choice
        def propose(self, phase, context, timeout):
            if phase == 'plan': return super().propose(phase, context, timeout)
            if phase == 'red':
                number = 2 if 'two' in context['task'].lower() else 3
                content = context['files']['test_calc.py'] + f'\ndef test_{number}():\n    assert double({number}) == {number*2}\n'
                return change('test_calc.py', content)
            if phase == 'green':
                if not self.interrupted:
                    self.interrupted = True
                    raise KeyboardInterrupt
                return change('calc.py','def double(x):\n    return x * 2\n' if 'two' in context['task'].lower() else 'def double(x):\n    return x + x\n')
            return change()
    # The second increment below is a deliberately controlled failing-test report;
    # real Docker evals separately establish meaningful red against actual code.
    green = result(passed=('test_calc.py::test_zero','test_2'))
    second_green = result(passed=('test_calc.py::test_zero','test_2','test_3'))
    partner = Partner()
    runs = tmp_path/'runs'
    answers = iter(['Double inputs','approve','/quit'])
    repl.shell(root,backend=partner,image='fixture',output_root=runs,read=lambda p:next(answers),write=lambda m:None,
               runner_factory=lambda *a,**k:Runner([result(),result(failed=('test_2',))]))
    saved = next(runs.iterdir())
    from xp_agent.session import load_session
    first = load_session(saved)
    assert first['status'] == 'cancelled'
    answers = iter([f'/resume {saved}','/quit'])
    repl.shell(root,backend=partner,image='fixture',output_root=runs,read=lambda p:next(answers),write=lambda m:None,
               runner_factory=lambda *a,**k:Runner([green,green,green,green,result(passed=green['passed'],failed=('test_3',)),second_green,second_green,second_green]))
    finished = load_session(saved)
    assert finished['status'] == 'verified'
    assert len(finished['states']) == 2
    assert finished['states'][0]['attempts']['green'] == 2
    assert finished['remaining_seconds'] <= first['remaining_seconds']


def test_changed_workspace_cannot_resume(tmp_path):
    from xp_agent.session import prepare, start, load_session
    from xp_agent.policy import PolicyError
    import pytest
    root = project(tmp_path)
    plan = prepare(root,'Double inputs',Planner(),image='fixture',progress=lambda m:None)
    saved = start(plan,tmp_path/'run')
    workspace = saved/'workspace'
    (workspace/'calc.py').write_text('# external edits\n')
    with pytest.raises(PolicyError,match='changed'):
        load_session(saved)


def test_provider_override_does_not_reuse_other_provider_preferences(tmp_path, monkeypatch):
    from xp_agent.project import write_json
    runs = tmp_path/'runs'
    write_json(tmp_path/'settings.json',{'provider':'claude','model':'sonnet','auth':'oauth-token'})
    selected=[]
    def factory(provider,model,auth,status=None):
        selected.append((provider,model,auth))
        class Partner:
            provider,model,auth='codex','fixture','cli'
        return Partner()
    monkeypatch.setattr(repl,'create_backend',factory)
    repl.shell(tmp_path,provider='codex',output_root=runs,read=lambda p:'/quit',write=lambda m:None)
    assert selected == [('codex',None,'cli')]


import os
import pytest
@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Requires Docker')
def test_primary_repl_multiple_real_xp_cycles_with_cancellation_and_resume(tmp_path):
    from pathlib import Path
    from xp_agent.project import git
    from xp_agent.sandbox import DockerRunner
    from xp_agent.session import load_session
    from xp_agent.workflow import passing
    root = project(tmp_path)
    (root/'calc.py').write_text('def double(x):\n    return x\n\ndef triple(x):\n    return x\n')
    git(root,'add','calc.py'); git(root,'commit','-m','Second fixture behavior')
    original = (root/'calc.py').read_text()
    class Partner(Planner):
        def __init__(self): self.cancel_once=True
        def select(self, context, timeout):
            choice=super().select(context,timeout)
            if choice['increments']:
                choice['increments']=[{'task':'Implement double','acceptance':['double(2) is 4']},
                                      {'task':'Implement triple','acceptance':['triple(3) is 9']}]
            return choice
        def propose(self, phase, context, timeout):
            if phase=='plan': return super().propose(phase,context,timeout)
            function='double' if 'double' in context['task'] else 'triple'
            if phase=='red':
                expected=4 if function=='double' else 6
                return change('test_calc.py',context['files']['test_calc.py'] + f'\ndef test_{function}():\n    from calc import {function}\n    assert {function}(2) == {expected}\n')
            if phase=='green':
                if self.cancel_once:
                    self.cancel_once=False
                    raise KeyboardInterrupt
                source=context['files']['calc.py'].replace(f'def {function}(x):\n    return x\n',f'def {function}(x):\n    return x * {2 if function=="double" else 3}\n')
                return change('calc.py',source)
            return change()
    partner=Partner()
    outputs=[]
    answers=iter(['Implement double and triple','approve','/resume','/quit'])
    runner=lambda image,**kwargs:DockerRunner(image,scratch=Path.cwd()/'.xp-runs/scratch')
    repl.shell(root,backend=partner,image='xp-agent-tests:0.1',output_root=tmp_path/'runs',
               read=lambda p:next(answers),write=outputs.append,runner_factory=runner)
    saved=next((tmp_path/'runs').iterdir())
    record=load_session(saved)
    assert record['status']=='verified', record.get('current')
    assert len(record['states'])==2
    assert record['states'][0]['attempts']['green']==2
    assert sum('RED: accepted' in line for line in outputs)==2
    assert (root/'calc.py').read_text()==original
    assert passing(runner('xp-agent-tests:0.1').test({**record['files'],'test_oracle.py':
        'from calc import double, triple\ndef test_unseen():\n    assert double(-3) == -6\n    assert triple(-3) == -9\n'},30))
