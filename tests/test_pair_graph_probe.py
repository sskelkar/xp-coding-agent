"""Exercise the probe against actual compiled graphs, not prewritten traces."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from xp_agent.pair_evals.graph_probe import probe_graph


class State(TypedDict, total=False):
    pending: dict
    report: dict
    answer: str


def graph_factory(ports, *, wrong_actor=False, skip_tests=False, ignore_red=False,
                  no_interrupt=False, write_after_feedback=False):
    graph = StateGraph(State)
    turns = [('A','red'), ('A' if wrong_actor else 'B','green'), ('B','red'), ('A','green')]
    for i, (actor, phase) in enumerate(turns):
        def propose(state, actor=actor, phase=phase):
            return {'pending': ports.agent(actor, phase)}
        def test(state):
            return {'report': ports.run_tests(state['pending'])}
        graph.add_node(f'agent_{i}', propose)
        graph.add_node(f'test_{i}', test)
        graph.add_edge(f'agent_{i}', f'test_{i}' if not skip_tests else (f'agent_{i+1}' if i<3 else 'business'))
        def route(state, i=i, phase=phase):
            expected = 1 if phase == 'red' else 0
            return (f'agent_{i+1}' if i<3 else 'business') if ignore_red or state['report']['returncode']==expected else END
        graph.add_conditional_edges(f'test_{i}', route)
    def business(state):
        return {'answer': 'accept' if no_interrupt else interrupt({'kind':'demo'})}
    graph.add_node('business', business)
    graph.add_edge(START,'agent_0')
    if write_after_feedback:
        graph.add_node('extra', lambda state: {'pending':ports.agent('B','red')})
        graph.add_edge('business','extra');graph.add_edge('extra',END)
    else:graph.add_edge('business',END)
    return graph.compile(checkpointer=InMemorySaver())


def test_real_compiled_graph_rotates_roles_and_waits_for_business():
    result = probe_graph(graph_factory)
    assert result['passed'], result
    assert result['observed_calls'] == ['A:red','B:green','B:red','A:green']
    assert result['observed_runner_calls'] == 4
    assert result['business_interrupt_observed']
    assert result['evidence_kind'] == 'compiled_langgraph_probe'
    assert result['runtime_verified'] is False  # Reference graph, not shipped pair runtime.


def test_wrong_actor_and_skipped_runner_are_detected_from_actual_calls():
    for options in ({'wrong_actor':True},{'skip_tests':True}):
        result = probe_graph(lambda ports: graph_factory(ports, **options))
        assert not result['passed'], result


def test_graph_cannot_advance_on_premature_green_or_failed_implementation():
    for scenario in ('red_already_green','green_fails'):
        result = probe_graph(graph_factory, scenario=scenario)
        assert result['passed'], result
        broken = probe_graph(lambda p:graph_factory(p,ignore_red=True),scenario=scenario)
        assert not broken['passed'], broken


def test_plain_completion_does_not_substitute_for_a_langgraph_interrupt():
    result = probe_graph(lambda p:graph_factory(p,no_interrupt=True))
    assert not result['passed']
    assert not result['business_interrupt_observed']


def test_resume_does_not_repeat_agent_calls_or_code_after_acceptance():
    result = probe_graph(lambda p:graph_factory(p,write_after_feedback=True))
    assert not result['passed']
    assert 'A:red' in result['observed_calls']


def test_overlapping_agent_invocations_are_rejected():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    def work(actor):
        if actor == 'A':
            entered.set()
            if not release.wait(timeout=2): raise RuntimeError('Test synchronization failed')
    def factory(ports):
        graph=StateGraph(State)
        def parallel(state):
            with ThreadPoolExecutor(2) as pool:
                a=pool.submit(ports.agent,'A','red')
                assert entered.wait(timeout=2)
                try:ports.agent('B','green')
                finally:release.set()
                a.result()
            return {}
        graph.add_node('parallel',parallel);graph.add_edge(START,'parallel');graph.add_edge('parallel',END)
        return graph.compile(checkpointer=InMemorySaver())
    result=probe_graph(factory, agent_work=work)
    assert not result['passed']
    assert 'concurrent_agent_call' in result['violations']


def test_manual_ping_pong_loop_inside_one_node_is_not_graph_orchestration():
    def factory(ports):
        graph=StateGraph(State)
        def manual_loop(state):
            for actor,phase in [('A','red'),('B','green'),('B','red'),('A','green')]:
                ports.run_tests(ports.agent(actor,phase))
            return {}
        def business(state):return {'answer':interrupt({'kind':'demo'})}
        graph.add_node('manual_loop',manual_loop);graph.add_node('business',business)
        graph.add_edge(START,'manual_loop');graph.add_edge('manual_loop','business');graph.add_edge('business',END)
        return graph.compile(checkpointer=InMemorySaver())
    result=probe_graph(factory)
    assert not result['passed']
    assert 'no_graph_handoff_boundary' in result['violations']
