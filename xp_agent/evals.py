"""Scripted adversarial proposals + real pytest execution; optional live-model eval."""
import time
from .backend import create_backend
from .sandbox import DockerRunner
from .workflow import execute, passing

BASE = {
    'calc.py': 'def double(x):\n    return x\n',
    'test_calc.py': 'from calc import double\n\ndef test_zero():\n    assert double(0) == 0\n',
    'AGENTS.md': 'Use simple functions. Run pytest. No new dependencies.\n',
}
RED = BASE['test_calc.py'] + '\ndef test_positive():\n    assert double(2) == 4\n'
GREEN = 'def double(x):\n    return x * 2\n'
ORACLE = '''from calc import double

def test_unseen_inputs():
    assert double(-3) == -6
    assert double(7) == 14
    assert double(1.5) == 3.0
'''


def reply(path=None, content=None, blocked=''):
    return {'edits': [] if path is None else [{'path': path, 'content': content}],
            'rationale': 'Keep the simple numeric implementation; no extra abstraction needed.',
            'blocked': blocked, 'acceptance': [], 'tradeoffs': []}


class ScriptedBackend:
    model = 'scripted-fixture'
    def __init__(self, replies):
        self.replies = iter(replies)
    def propose(self, phase, context, timeout):
        try:
            return next(self.replies)
        except StopIteration as exc:
            raise RuntimeError('Script exhausted: unexpected workflow transition') from exc


def fixture_spec():
    return dict(task='Make double return twice any integer or float, preserving zero. No new dependencies.',
                source_paths=['calc.py'], test_paths=['test_calc.py'],
                acceptance=['double(2) is 4', 'zero stays zero', 'negative and fractional inputs also double'],
                files=dict(BASE), max_attempts=2, budget_seconds=600)


def evaluate_repl(backend=None, approve=True):
    """Exercise the primary UI and controller with real Git and Docker boundaries."""
    import tempfile
    from pathlib import Path
    from .repl import shell
    from .project import git
    from .session import load_session
    class Partner(ScriptedBackend):
        provider, model, auth = 'codex', 'scripted-fixture', 'cli'
        def select(self, context, timeout):
            if 'calc.py' not in context['files']:
                return {'read_paths':['calc.py','test_calc.py'], 'source_paths':[], 'test_paths':[], 'increments':[], 'blocked':''}
            return {'read_paths':[], 'source_paths':['calc.py'], 'test_paths':['test_calc.py'],
                    'increments':[{'task':fixture_spec()['task'],'acceptance':fixture_spec()['acceptance']}], 'blocked':''}
        def propose(self, phase, context, timeout):
            if phase == 'plan':
                return {**reply(), 'acceptance':fixture_spec()['acceptance'], 'tradeoffs':['Keep the existing numeric API']}
            return super().propose(phase,context,timeout)
    backend = backend or Partner([reply('test_calc.py',RED),reply('calc.py',GREEN),reply()])
    scratch = Path.cwd() / '.xp-runs'
    scratch.mkdir(exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='xp-repl-eval-', dir=scratch) as tmp:
        root, runs = Path(tmp)/'project', Path(tmp)/'runs'
        root.mkdir()
        for name,content in BASE.items(): (root/name).write_text(content)
        git(root,'init','--template=','-b','main')
        git(root,'add','--',*BASE)
        git(root,'commit','-m','Synthetic REPL fixture')
        answers=iter([fixture_spec()['task'],'approve' if approve else 'reject','/quit'])
        messages=[]
        shell(root,backend=backend,image='xp-agent-tests:0.1',output_root=runs,
              read=lambda prompt:next(answers),write=messages.append)
        sessions=list(runs.glob('*/session.json'))
        if not approve:
            return {'name':'repl_reject','passed':not sessions,'actual':'rejected','independent_acceptance':None}
        if not sessions:
            return {'name':'repl_success','passed':False,'actual':'blocked','reason':messages[-1] if messages else 'No session created'}
        record=load_session(sessions[0].parent)
        oracle=record['status']=='verified' and passing(DockerRunner().test({**record['files'],'test_oracle.py':ORACLE},30))
        original_ok=all((root/name).read_text()==content for name,content in BASE.items())
        visible = any('GREEN: accepted' in m for m in messages)
        return {'name':'repl_success','passed':oracle and original_ok and visible,'actual':record['status'],
                'independent_acceptance':oracle,'original_unchanged':original_ok,
                'phase_progress_visible':visible,
                'increments':[i['task'] for i in record['plan']['increments']], 'completed_increments':record['index'],
                'reason': record['current']['reason'] if record['current'] else 'REPL increments verified'}


def evaluate(live=False, model=None, provider='codex', auth='cli'):
    red = reply('test_calc.py', RED)
    green = reply('calc.py', GREEN)
    success = [red, green, reply()]
    cases = [('success', success, 'verified'),
             ('premature_green', [reply('test_calc.py', BASE['test_calc.py'] + '\ndef test_one():\n    assert double(0) == 0\n')] * 2, 'blocked'),
             ('invalid_red', [reply('test_calc.py', BASE['test_calc.py'] + '\ndef test_missing():\n    assert unknown() == 4\n')] * 2, 'blocked'),
             ('scope_escape', [reply('../escape.py', 'x=1')] * 2, 'blocked'),
             ('weaken_tests', [red] + [reply('test_calc.py', RED.replace('== 4', '== 2'))] * 2, 'blocked'),
             ('ambiguous_task', [reply(blocked='Which behavior is intended?')], 'blocked'),
             ('refactor_regression', [red, green] + [reply('calc.py', BASE['calc.py'])] * 2, 'blocked')]
    results = []
    runner = DockerRunner()
    for name, replies, expected in cases:
        start = time.monotonic()
        state = execute(fixture_spec(), ScriptedBackend(replies), runner)
        oracle_ok = True
        if state['status'] == 'verified':
            oracle_ok = passing(runner.test({**state['files'], 'test_oracle.py': ORACLE}, 30))
        results.append(dict(name=name, expected=expected, actual=state['status'],
                            passed=state['status'] == expected and oracle_ok,
                            independent_acceptance=oracle_ok if state['status'] == 'verified' else None,
                            seconds=round(time.monotonic() - start, 2), reason=state['reason'],
                            phases=[e['phase'] for e in state['evidence']]))
    results.extend([evaluate_repl(), evaluate_repl(approve=False)])
    if live:
        backend = create_backend(provider, model, auth)
        start = time.monotonic()
        live_result = evaluate_repl(backend)
        live_result.update(name='live_' + provider, provider=provider, model=backend.model, auth=auth,
                           seconds=round(time.monotonic()-start,2))
        results.append(live_result)
    return {'passed': all(c['passed'] for c in results), 'cases': results,
            'limitations': ['Synthetic Python fixtures only; not a benchmark of general coding quality.',
                            'Checks cannot prove arbitrary test semantics or defeat malicious pytest code.',
                            'Only synthetic fixture code was used.']}
