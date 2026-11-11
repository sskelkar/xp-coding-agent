"""Observe actual compiled LangGraph calls with deterministic partner/runner ports.

The graph under test owns scheduling. Ports log calls independently of graph
state or agent narratives. This probe does not implement the product workflow,
execute candidate code, call a model, or prove behavior beyond these scenarios.
"""
from copy import deepcopy
from threading import Lock
from uuid import uuid4
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from langgraph.config import get_config


class ProbePorts:
    def __init__(self, scenario, agent_work=None):
        self.scenario = scenario
        self.events = []
        self.violations = set()
        self._lease = Lock()
        self._proposals = {}
        self._tested = set()
        self._work = agent_work

    def agent(self, actor, phase):
        """Instrumented deterministic partner; actor is the actual invoked port."""
        if not self._lease.acquire(blocking=False):
            self.violations.add('concurrent_agent_call')
            raise RuntimeError('Concurrent agent invocation')
        try:
            token = str(len(self._proposals))
            proposal = {'id': token, 'actor': actor, 'phase': phase}
            self._proposals[token] = deepcopy(proposal)
            self.events.append({'kind': 'agent', **proposal, 'graph_task': _task_identity()})
            if self._work:
                self._work(actor)
            return proposal
        finally:
            self._lease.release()

    def run_tests(self, proposal):
        """Controlled runner result; never take a claimed outcome from the graph."""
        token = proposal.get('id')
        if token not in self._proposals or proposal != self._proposals[token] or token in self._tested:
            self.violations.add('invalid_runner_proposal')
            raise ValueError('Unknown, modified or already-tested proposal')
        self._tested.add(token)
        phase = proposal['phase']
        if phase not in {'red', 'green'}:
            raise ValueError('Probe supports red/green routing only')
        code = 1 if phase == 'red' else 0
        if self.scenario == 'red_already_green' and token == '0':
            code = 0
        if self.scenario == 'green_fails' and token == '1':
            code = 1
        cycle = int(token) // 2
        previous = [f'synthetic_{i}' for i in range(cycle)]
        current = f'synthetic_{cycle}'
        report = {'returncode': code, 'failed': [current] if code else [],
                  'passed': previous if code else previous + [current], 'errors': [], 'skipped': []}
        self.events.append({'kind': 'runner', 'proposal': token, 'returncode': code, 'graph_task': _task_identity()})
        return report


def _task_identity():
    try:
        metadata = get_config().get('metadata', {})
        node, step = metadata.get('langgraph_node'), metadata.get('langgraph_step')
        return (node, step) if isinstance(node, str) and type(step) is int else None
    except RuntimeError:
        return None


def probe_graph(factory, *, scenario='success', agent_work=None):
    """Factory(ports) must return the actual compiled graph being evaluated.

    Ports.agent(actor, phase) returns a scripted proposal. Ports.run_tests owns
    the observed outcome. Supply an explicit in-memory checkpointer in the graph
    factory so a real business interrupt and Command(resume=...) can be tested.
    A future adapter must exercise production routing, not rebuild a passing
    reference graph. The test reference graphs are evaluator self-tests only.
    """
    if scenario not in {'success', 'red_already_green', 'green_fails'}:
        raise ValueError('Unknown graph probe scenario')
    ports = ProbePorts(scenario, agent_work)
    violations = ports.violations
    config = {'configurable': {'thread_id': 'pair-probe-' + uuid4().hex}, 'recursion_limit': 40}
    interrupted, resumed, node_updates = False, False, 0
    error_type = None
    try:
        graph = factory(ports)
        if not isinstance(graph, CompiledStateGraph):
            raise ValueError('Expected a compiled StateGraph, not supplied events')
        updates = list(graph.stream({}, config, stream_mode='updates'))
        node_updates += sum('__interrupt__' not in u for u in updates)
        snapshot = graph.get_state(config)
        interrupted = (any('__interrupt__' in u for u in updates)
                       and any(task.interrupts for task in snapshot.tasks)
                       and bool(snapshot.next))
        if scenario == 'success':
            if not interrupted:
                violations.add('missing_business_interrupt')
            else:
                before_resume = len(ports.events)
                resumed_updates = list(graph.stream(Command(resume='accept'), config, stream_mode='updates'))
                node_updates += sum('__interrupt__' not in u for u in resumed_updates)
                resumed = not graph.get_state(config).next
                if len(ports.events) != before_resume:
                    violations.add('agent_or_runner_call_replayed_after_acceptance')
                if not resumed:
                    violations.add('did_not_finish_after_acceptance')
        elif interrupted or snapshot.next:
            violations.add('invalid_advance_after_failed_gate')
    except Exception as exc:
        # Do not publish source-bearing tracebacks from a graph under test.
        error_type = type(exc).__name__
        violations.add('graph_exception')
    expected = [('A', 'red'), ('B', 'green'), ('B', 'red'), ('A', 'green')]
    if scenario == 'red_already_green':
        expected = expected[:1]
    elif scenario == 'green_fails':
        expected = expected[:2]
    calls = [(e['actor'], e['phase']) for e in ports.events if e['kind'] == 'agent']
    if calls != expected:
        violations.add('actual_partner_sequence')
    if len(ports.events) != len(expected) * 2:
        violations.add('missing_or_extra_execution')
    for i, (actor, phase) in enumerate(expected):
        pair = ports.events[i*2:i*2+2]
        if len(pair) != 2 or pair[0]['kind'] != 'agent' or pair[1]['kind'] != 'runner':
            violations.add('agent_advanced_without_runner')
            continue
        if pair[1]['proposal'] != pair[0]['id']:
            violations.add('runner_proposal_binding')
        expected_code = 1 if phase == 'red' else 0
        if scenario == 'red_already_green' and i == 0:
            expected_code = 0
        if scenario == 'green_fails' and i == 1:
            expected_code = 1
        if pair[1]['returncode'] != expected_code:
            violations.add('unexpected_runner_result')
    # A correct-looking loop in one node is NOT a graph-controlled handoff.
    # These identities come from LangGraph's execution context, not graph state.
    tasks = [e.get('graph_task') for e in ports.events]
    if any(t is None for t in tasks) or any(
            left[1] >= right[1] for left, right in zip(tasks, tasks[1:])
            if left is not None and right is not None):
        violations.add('no_graph_handoff_boundary')
    return {'version': 1, 'scenario': scenario, 'passed': not violations,
            'status': 'passed' if not violations else 'failed',
            'evidence_kind': 'compiled_langgraph_probe', 'runtime_verified': False,
            'observed_calls': [f'{a}:{p}' for a, p in calls],
            'observed_runner_calls': sum(e['kind'] == 'runner' for e in ports.events),
            'observed_graph_tasks': tasks,
            'business_interrupt_observed': interrupted,
            'resume_finished': resumed, 'observed_node_updates': node_updates,
            'violations': sorted(violations), 'graph_error_type': error_type}
