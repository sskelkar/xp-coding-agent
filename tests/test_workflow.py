import pytest
from xp_agent.workflow import execute

BASE = {'calc.py': 'def double(x):\n    return x\n',
        'test_calc.py': 'from calc import double\n\ndef test_zero():\n    assert double(0) == 0\n'}
TEST = BASE['test_calc.py'] + '\ndef test_two():\n    assert double(2) == 4\n'

class Backend:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.phases = []
    def propose(self, phase, context, timeout):
        self.phases.append(phase)
        return next(self.replies)

class Runner:
    def __init__(self, results):
        self.results = iter(results)
    def test(self, files, timeout):
        return next(self.results)

def result(passed=('test_calc.py::test_zero',), failed=(), errors=()):
    return {'passed': list(passed), 'failed': list(failed), 'errors': list(errors), 'skipped': [],
            'returncode': 1 if failed else 2 if errors else 0, 'output': 'fixture evidence'}

def change(path=None, content=None):
    return {'edits': [] if path is None else [{'path': path, 'content': content}],
            'rationale': 'Small behavior change' if path else 'No further useful refactoring', 'blocked': ''}

def spec():
    return {'task': 'Double positive integers', 'source_paths': ['calc.py'],
            'test_paths': ['test_calc.py'], 'acceptance': ['double(2) is 4'],
            'files': dict(BASE), 'max_attempts': 2, 'budget_seconds': 30}

def test_graph_requires_red_before_implementation_and_keeps_evidence():
    backend = Backend([change('test_calc.py', TEST), change('calc.py', 'def double(x):\n    return x * 2\n'), change()])
    runner = Runner([result(), result(failed=('test_calc.py::test_two',)),
                     result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two')),
                     result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two')),
                     result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two'))])
    outcome = execute(spec(), backend, runner)
    assert outcome['status'] == 'verified'
    assert backend.phases == ['red', 'green', 'refactor']
    assert [e['phase'] for e in outcome['evidence']] == ['baseline', 'red', 'green', 'refactor', 'final']
    assert all(e['code_hash'] for e in outcome['evidence'])
    assert outcome['files']['test_calc.py'] == TEST

@pytest.mark.parametrize('bad_red', [result(), result(errors=('collection error',))])
def test_green_is_unreachable_without_meaningful_red(bad_red):
    backend = Backend([change('test_calc.py', TEST)] * 2)
    outcome = execute(spec(), backend, Runner([result(), bad_red, bad_red]))
    assert outcome['status'] == 'blocked'
    assert backend.phases == ['red', 'red']
    assert outcome['files'] == BASE


def test_phase_violation_cannot_change_files():
    backend = Backend([change('calc.py', 'def double(x):\n    return x * 2\n')] * 2)
    outcome = execute(spec(), backend, Runner([result()]))
    assert outcome['status'] == 'blocked'
    assert outcome['files'] == BASE


def test_baseline_failure_blocks_without_model_calls():
    backend = Backend([])
    outcome = execute(spec(), backend, Runner([result(failed=('test_calc.py::test_zero',))]))
    assert outcome['status'] == 'blocked'
    assert not backend.phases


def test_ambiguity_stops_instead_of_guessing():
    backend = Backend([{'edits': [], 'rationale': '', 'blocked': 'Should negative inputs raise?'}])
    outcome = execute(spec(), backend, Runner([result()]))
    assert outcome['status'] == 'blocked'
    assert 'negative' in outcome['reason']


def test_refactor_no_change_rationale_is_recorded():
    backend = Backend([change('test_calc.py', TEST), change('calc.py', 'def double(x):\n    return x * 2\n'), change()])
    green = result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two'))
    state = execute(spec(), backend, Runner([result(), result(failed=('test_calc.py::test_two',)), green, green, green]))
    refactor = next(e for e in state['evidence'] if e['phase'] == 'refactor')
    assert refactor.get('rationale') == 'No further useful refactoring'


def test_records_accepted_work_separately_from_rejected_attempts():
    backend = Backend([change('calc.py', 'x = 2\n'), change('test_calc.py', TEST),
                       change('calc.py', 'def double(x):\n    return x * 2\n'), change()])
    green = result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two'))
    state = execute(spec(), backend, Runner([result(), result(failed=('test_calc.py::test_two',)), green, green, green]))
    assert [c['phase'] for c in state.get('changes', [])] == ['red', 'green', 'refactor']
    assert state['changes'][-1]['paths'] == []
    assert state['rejections'][0]['phase'] == 'red'
    assert 'may not edit' in state['rejections'][0]['reason']
    assert all(e['accepted'] for e in state['evidence'])


def test_resume_preserves_red_tests_and_remaining_attempt_budget():
    backend = Backend([change('test_calc.py', TEST), change('calc.py', 'def double(x):\n    return x * 2\n'), change()])
    class Interrupted(Runner):
        def test(self, files, timeout):
            if files['calc.py'] != BASE['calc.py']:
                raise KeyboardInterrupt
            return super().test(files, timeout)
    first = execute(spec(), backend, Interrupted([result(), result(failed=('test_calc.py::test_two',))]))
    assert first['status'] == 'cancelled'
    green = result(passed=('test_calc.py::test_zero', 'test_calc.py::test_two'))
    retry = Backend([change('calc.py', 'def double(x):\n    return x * 2\n'), change()])
    resumed = execute(spec(), retry, Runner([green, green, green]), initial_state=first)
    assert resumed['status'] == 'verified'
    assert resumed['attempts']['green'] == 2
    assert retry.phases == ['green', 'refactor']
    assert resumed['remaining_seconds'] <= first['remaining_seconds']
