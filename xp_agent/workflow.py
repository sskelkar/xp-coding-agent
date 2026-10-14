"""Explicit LangGraph XP transitions. Backend suggestions never promote themselves."""
import os
import time
from typing import TypedDict
from .policy import PolicyError, digest, validate_edits
from .process import ProcessError
from .backend import ProposalBackend

# Neither graph state nor code may be sent to tracing services implicitly.
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
from langgraph.graph import StateGraph, START, END


class State(TypedDict, total=False):
    files: dict
    evidence: list
    status: str
    reason: str
    phase: str
    attempts: dict
    baseline_tests: list
    red_tests: list
    last_feedback: str
    changes: list
    rejections: list
    remaining_seconds: float


def passing(report, required=()):
    return (report['returncode'] == 0 and bool(report['passed']) and
            not report['failed'] and not report['errors'] and not report['skipped'] and
            set(required).issubset(report['passed']))


def execute(spec, backend: ProposalBackend, runner, checkpoint=None, *, initial_state=None):
    deadline = time.monotonic() + (initial_state.get('remaining_seconds', 0) if initial_state else spec['budget_seconds'])
    snapshot = {}

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise ProcessError('Run deadline exceeded')
        return seconds

    def save(state):
        state['remaining_seconds'] = max(0, deadline - time.monotonic())
        snapshot.update(state)
        if checkpoint:
            checkpoint(dict(state))
        return state

    def evidence(state, phase, files, report):
        state['evidence'] = state['evidence'] + [{'phase': phase, 'code_hash': digest(files), 'accepted': False, **report}]

    def baseline(state):
        report = runner.test(state['files'], remaining())
        evidence(state, 'baseline', state['files'], report)
        state['evidence'][-1]['accepted'] = passing(report)
        if not passing(report):
            state.update(status='blocked', reason='Baseline is not green; resolve existing failures or missing tests')
        else:
            state['baseline_tests'] = report['passed']
            state['phase'] = 'red'
        return save(state)

    def phase_node(phase):
        def node(state):
            state['phase'] = phase
            if state['attempts'].get(phase, 0) >= spec['max_attempts']:
                return save({**state, 'status': 'blocked', 'reason': f'{phase}: attempt budget exhausted'})
            state['attempts'] = {**state['attempts'], phase: state['attempts'].get(phase, 0) + 1}
            save(state)
            reply = backend.propose(phase, {**spec, 'files': state['files'], 'feedback': state.get('last_feedback', '')}, remaining())
            if reply.get('blocked'):
                state.update(status='blocked', reason=reply['blocked'])
                return save(state)
            try:
                if not isinstance(reply.get('rationale'), str) or not reply['rationale'].strip():
                    raise PolicyError('A rationale is required, including no-change refactoring')
                changes = reply['edits']
                edits = {edit['path']: edit['content'] for edit in changes}
                if len(edits) != len(changes):
                    raise PolicyError('Duplicate candidate paths')
                candidate = validate_edits(phase, state['files'], edits, spec['source_paths'], spec['test_paths'])
                report = runner.test(candidate, remaining())
                evidence(state, phase, candidate, {**report, 'rationale': reply['rationale']})
                if phase == 'red':
                    good = (report['returncode'] == 1 and bool(report['failed']) and not report['errors'] and
                            not report['skipped'] and set(state['baseline_tests']).issubset(report['passed']) and
                            not set(report['failed']).intersection(state['baseline_tests']))
                    if not good:
                        raise PolicyError('Red requires NEW assertion failures with all baseline tests passing; errors/skips/premature green are invalid')
                    state['red_tests'] = report['passed'] + report['failed']
                elif not passing(report, state['red_tests']):
                    raise PolicyError('Target and regression tests must all pass without disappearing or skipping tests')
                state['evidence'][-1]['accepted'] = True
                state['changes'] = state['changes'] + [{
                    'phase': phase, 'attempt': state['attempts'][phase],
                    'paths': sorted(path for path in edits if state['files'].get(path) != candidate[path]),
                    'rationale': reply['rationale'],
                }]
                state['files'] = candidate
                state['last_feedback'] = ''
                state['phase'] = {'red': 'green', 'green': 'refactor', 'refactor': 'final'}[phase]
            except (PolicyError, KeyError, TypeError) as exc:
                state['rejections'] = state['rejections'] + [{
                    'phase': phase, 'attempt': state['attempts'][phase], 'reason': str(exc),
                }]
                state['last_feedback'] = str(exc)
                if state['attempts'][phase] >= spec['max_attempts']:
                    state.update(status='blocked', reason=f'{phase}: {exc}; attempt budget exhausted')
            return save(state)
        return node

    def final(state):
        report = runner.test(state['files'], remaining())
        evidence(state, 'final', state['files'], report)
        state['evidence'][-1]['accepted'] = passing(report, state['red_tests'])
        state.update(status='verified' if passing(report, state['red_tests']) else 'blocked',
                     reason='Automated XP checks passed; human product acceptance pending' if passing(report, state['red_tests']) else 'Final verification failed')
        return save(state)

    graph = StateGraph(State)
    graph.add_node('baseline', baseline)
    for phase in ('red', 'green', 'refactor'):
        graph.add_node(phase, phase_node(phase))
    graph.add_node('final', final)
    graph.add_conditional_edges(START, lambda s: s['phase'])
    graph.add_conditional_edges('baseline', lambda s: END if s['status'] == 'blocked' else 'red')
    for phase in ('red', 'green', 'refactor'):
        graph.add_conditional_edges(phase, lambda s: END if s['status'] == 'blocked' else s['phase'])
    graph.add_edge('final', END)
    initial = State(files=dict(spec['files']), evidence=[], status='running', reason='', phase='baseline', attempts={}, changes=[], rejections=[])
    if initial_state:
        initial = {**initial_state, 'status': 'running', 'reason': ''}
    save(initial)
    try:
        return graph.compile().invoke(initial, {'recursion_limit': 10 + 3 * spec['max_attempts']})
    except (ProcessError, OSError, ValueError, RuntimeError) as exc:
        return save({**snapshot, 'status': 'blocked', 'reason': str(exc)})
    except KeyboardInterrupt:
        return save({**snapshot, 'status': 'cancelled', 'reason': 'Cancelled; verified work preserved'})
