from copy import deepcopy
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from xp_agent.pairing.graph import build_graph
from xp_agent.pairing.controller import PairController
from xp_agent.workspace import reconcile_workspace


def reply(action='comment', message='Discuss the next behavior.', edits=None, examples=None):
    return dict(action=action,
                message=message,
                edits=[{
                    'path': p,
                    'content': c
                } for p, c in (edits or {}).items()],
                examples=examples or [])


class Dummy:

    def __init__(self, identity):
        self.identity = identity
        self.seen = []

    def reply(self, phase, state):
        self.seen.append(deepcopy(state))
        if phase == 'discuss':
            return reply(action='question', message='Should the original amount remain unchanged?')
        return reply()


def test_confirm_and_business_question_are_real_interrupts_without_project_execution(tmp_path):

    class Runner:

        def test(self, *args):
            raise AssertionError('No tests before a coding proposal')

    a, b = Dummy('A'), Dummy('B')
    ops = PairController({'A': a, 'B': b}, Runner(), tmp_path, 'Money', {})
    graph = build_graph(ops, InMemorySaver())
    config = {'configurable': {'thread_id': 'question'}}
    result = graph.invoke({}, config)
    assert result['__interrupt__'][0].value['kind'] == 'confirm_goal'
    assert not a.seen and not b.seen
    result = graph.invoke(Command(resume='confirm'), config)
    assert result['__interrupt__'][0].value['kind'] == 'business_question'
    assert len(a.seen) == 1 and not b.seen
    assert not list(tmp_path.iterdir())
    graph.invoke(Command(resume='Original stays unchanged'), config)
    assert 'Business clarification' in a.seen[-1]['goal']
    assert any('Original stays unchanged' in m['message'] for m in a.seen[-1]['histories']['A'])


def test_red_retry_can_route_a_follow_up_question_to_the_user(tmp_path):
    question = 'Should the result be a timezone-aware datetime?'

    class Partner(Dummy):

        def reply(self, phase, state):
            if phase == 'discuss':
                return reply()
            assert phase == 'red'
            if 'action="question"' in state['feedback']:
                return reply('question', message=question)
            return reply('comment', message=question)

    class Runner:

        def test(self, *args):
            raise AssertionError('A business question must pause before running tests')

    partners = {actor: Partner(actor) for actor in ('A', 'B')}
    ops = PairController(partners, Runner(), tmp_path, 'Convert a datetime', {})
    graph = build_graph(ops, InMemorySaver())
    config = {'configurable': {'thread_id': 'red-question'}}
    graph.invoke({}, config)
    result = graph.invoke(Command(resume='confirm'), config)

    assert result['status'] == 'question', result['reason']
    assert result['__interrupt__'][0].value['message'] == question
    assert result['phase'] == 'red'
    assert not list(tmp_path.iterdir())


def test_controller_refuses_external_workspace_changes_and_keeps_test_rules(tmp_path):
    a, b = Dummy('A'), Dummy('B')
    (tmp_path / 'intruder.py').write_text('human change')
    with pytest.raises(ValueError, match='externally'):
        reconcile_workspace(tmp_path, {}, {'money.py': 'pass'})
    with pytest.raises(ValueError, match='distinct'):
        PairController({'A': a, 'B': a}, None, tmp_path, 'Money', {})


def test_dynamic_source_scope_does_not_allow_overriding_pytest_or_demo_harness(tmp_path):

    class Partner(Dummy):

        def reply(self, phase, state):
            return reply('edit', edits={'pytest.py': 'def fake():\n    return True\n'})

    a, b = Partner('A'), Partner('B')
    ops = PairController({'A': a, 'B': b}, None, tmp_path, 'Money', {})
    state = ops.initialize({})
    state['phase'] = 'green'
    result = ops.propose('B', 'green', state)
    assert result['status'] in {'retry', 'blocked'}
    assert 'reserved' in result['reason'].lower()
    assert not list(tmp_path.iterdir())


def test_last_allowed_cycle_can_still_generate_its_business_demo(tmp_path):
    a, b = Dummy('A'), Dummy('B')
    ops = PairController({'A': a, 'B': b}, None, tmp_path, 'Money', {}, max_cycles=1)
    state = ops.initialize({})
    state['cycle'] = 2
    result, proposal = ops._call('A', 'demo', state)
    assert proposal is not None
    assert result['status'] != 'blocked'
