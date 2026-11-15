"""Production pair routing. Agents cannot select a peer or advance a phase."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt


class PairState(TypedDict, total=False):
    phase: str
    cycle: int
    files: dict
    pending: dict
    report: dict
    status: str
    reason: str
    required: list
    baseline: list
    histories: dict
    records: list
    snapshots: dict
    agreement: int
    goal: str
    feedback: str
    attempts: int
    remaining: float
    active: float
    last_feedback_active: float
    since_feedback: int
    demo: dict
    bootstrap_done: bool
    config: dict


def build_graph(controller, checkpointer):
    """One graph for live sessions, scripted integration and instrumented probes.

    The controller handles proposals and execution. This graph owns phase
    transitions and role assignments.
    """
    graph = StateGraph(PairState)

    def initialize(state):
        return controller.initialize(state)

    def confirm(state):
        goal = state['goal']
        if not controller.confirmed:
            while True:
                answer = interrupt({
                    'kind': 'confirm_goal',
                    'goal': goal,
                    'message': 'Confirm this outcome, or supply a clarification.'
                })
                if answer == 'confirm':
                    break
                if not isinstance(answer, str) or not answer.strip() or answer in {
                        'reject', 'quit', 'cancel'
                }:
                    return {'status': 'rejected', 'reason': 'Outcome not confirmed'}
                goal += '\nBusiness clarification: ' + answer
        return controller.confirm({**state, 'goal': goal})

    def baseline(state):
        return controller.baseline(state)

    def discussion_a(state):
        return controller.discuss('A', state)

    def discussion_b(state):
        return controller.discuss('B', state)

    def propose(state):
        author = 'A' if state['cycle'] % 2 else 'B'
        implementer = 'B' if author == 'A' else 'A'
        actor = author if state['phase'] == 'red' else implementer
        return controller.propose(actor, state['phase'], state)

    def test(state):
        return controller.test(state)

    def bootstrap(state):
        return controller.bootstrap(state)

    def accept(state):
        phase = state['phase']
        report = state['report']
        clean = not report.get('errors') and not report.get('skipped')
        passed, failed = set(report['passed']), set(report['failed'])
        required = set(state.get('required', []))
        if phase == 'red':
            valid = (clean and report['returncode'] == 1 and bool(failed) and required <= passed
                     and not required & failed)
        else:
            valid = (clean and report['returncode'] == 0 and bool(passed) and not failed
                     and required <= passed)
        if not valid:
            return controller.reject(state, 'Phase test requirement failed')
        accepted = {**state, **controller.accept(state)}
        if accepted['status'] == 'blocked':
            return accepted
        if phase == 'red':
            return {
                **accepted, 'phase': 'green',
                'required': sorted(passed | failed),
                'attempts': 0
            }
        if phase == 'green' and controller.refactoring:
            return {**accepted, 'phase': 'refactor', 'required': sorted(passed), 'attempts': 0}
        return {
            **accepted, 'phase': 'red',
            'cycle': state['cycle'] + 1,
            'required': sorted(passed),
            'attempts': 0,
            'since_feedback': state.get('since_feedback', 0) + 1
        }

    def prepare_demo(state):
        return controller.prepare_demo(state)

    def business(state):
        answer = interrupt(state['demo'])
        return controller.feedback(state, answer)

    graph.add_node('initialize', initialize)
    graph.add_node('confirm', confirm)
    graph.add_node('baseline', baseline)
    graph.add_node('discuss_a', discussion_a)
    graph.add_node('discuss_b', discussion_b)
    graph.add_node('propose', propose)
    graph.add_node('run_tests', test)
    graph.add_node('bootstrap', bootstrap)
    graph.add_node('accept', accept)
    graph.add_node('prepare_demo', prepare_demo)
    graph.add_node('business', business)
    graph.add_edge(START, 'initialize')
    graph.add_edge('initialize', 'confirm')
    graph.add_conditional_edges('confirm', lambda s: END
                                if s['status'] == 'rejected' else 'baseline')
    graph.add_conditional_edges('baseline', lambda s: END
                                if s['status'] == 'blocked' else 'discuss_a')

    def after_discussion(state, next_node):
        if state['status'] == 'blocked':
            return END
        return 'prepare_demo' if state['status'] in {'question', 'demo'} else next_node

    graph.add_conditional_edges('discuss_a', lambda s: after_discussion(s, 'discuss_b'))
    graph.add_conditional_edges('discuss_b', lambda s: after_discussion(s, 'propose'))
    graph.add_conditional_edges(
        'propose', lambda s: 'propose'
        if s['status'] == 'retry' else after_discussion(s, 'run_tests'))

    def route_scaffolding(state, next_node):
        if state['status'] == 'blocked':
            return END
        if state['status'] == 'scaffold_needed':
            return 'bootstrap'
        return next_node

    graph.add_conditional_edges('run_tests', lambda state: route_scaffolding(state, 'accept'))
    graph.add_conditional_edges('bootstrap', lambda state: route_scaffolding(state, 'run_tests'))

    def after_acceptance(state):
        if state['status'] == 'blocked':
            return END
        if state['status'] == 'retry':
            return 'propose'
        if controller.checkin_due(state):
            return 'prepare_demo'
        if state['phase'] != 'red':
            return 'propose'
        if controller.demo_due(state):
            return 'prepare_demo'
        return 'discuss_a'

    graph.add_conditional_edges('accept', after_acceptance)
    graph.add_conditional_edges('prepare_demo', lambda s: END
                                if s['status'] == 'blocked' else 'business')
    graph.add_conditional_edges(
        'business', lambda s: END
        if s['status'] in {'accepted', 'blocked', 'rejected'} else 'discuss_a')
    return graph.compile(checkpointer=checkpointer)
