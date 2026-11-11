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
    after_business: str
    bootstrap_done: bool
    config: dict


def build_graph(ops, checkpointer):
    """One graph for live sessions, scripted integration and instrumented probes.

    Operations supply actors, policy and execution; all phase/ownership edges
    below are production routing. Test doubles replace dependencies, not edges.
    """
    graph = StateGraph(PairState)
    def initialize(state): return ops.initialize(state)
    def confirm(state):
        if not ops.confirmed:
            answer = interrupt({'kind':'confirm_goal','goal':state['goal'],
                                'message':'Confirm this outcome, or supply a clarification.'})
            if answer != 'confirm':
                return {'status':'rejected','reason':'Outcome not confirmed'}
        return ops.confirm(state)
    def baseline(state):return ops.baseline(state)
    def discussion_a(state):return ops.discuss('A',state)
    def discussion_b(state):return ops.discuss('B',state)
    def propose(state):
        author = 'A' if state['cycle'] % 2 else 'B'
        actor = author if state['phase']=='red' else ('B' if author=='A' else 'A')
        return ops.propose(actor,state['phase'],state)
    def test(state):return ops.test(state)
    def bootstrap(state):return ops.bootstrap(state)
    def accept(state):
        phase = state['phase']
        report = state['report']
        clean = not report.get('errors') and not report.get('skipped')
        passed, failed = set(report['passed']), set(report['failed'])
        required = set(state.get('required',[]))
        if phase=='red':
            valid = (clean and report['returncode']==1 and bool(failed)
                     and required <= passed and not required & failed)
        else:
            valid = (clean and report['returncode']==0 and bool(passed) and not failed and required <= passed)
        if not valid:return ops.reject(state,'Phase test requirement failed')
        accepted = {**state, **ops.accept(state)}
        if accepted['status']=='blocked':return accepted
        if phase=='red':
            return {**accepted,'phase':'green','required':sorted(passed|failed),'attempts':0}
        if phase=='green' and ops.refactoring:
            return {**accepted,'phase':'refactor','required':sorted(passed),'attempts':0}
        return {**accepted,'phase':'red','cycle':state['cycle']+1,'required':sorted(passed),
                'attempts':0,'since_feedback':state.get('since_feedback',0)+1}
    def prepare_demo(state):return ops.prepare_demo(state)
    def business(state):
        answer=interrupt(state['demo'])
        return ops.feedback(state,answer)
    graph.add_node('initialize',initialize)
    graph.add_node('confirm',confirm)
    graph.add_node('baseline',baseline)
    graph.add_node('discuss_a',discussion_a)
    graph.add_node('discuss_b',discussion_b)
    graph.add_node('propose',propose)
    graph.add_node('run_tests',test)
    graph.add_node('bootstrap',bootstrap)
    graph.add_node('accept',accept)
    graph.add_node('prepare_demo',prepare_demo)
    graph.add_node('business',business)
    graph.add_edge(START,'initialize')
    graph.add_edge('initialize','confirm')
    graph.add_conditional_edges('confirm',lambda s:END if s['status']=='rejected' else 'baseline')
    graph.add_conditional_edges('baseline',lambda s:END if s['status']=='blocked' else 'discuss_a')
    def after_discussion(state, next_node):
        if state['status']=='blocked':return END
        return 'prepare_demo' if state['status'] in {'question','demo'} else next_node
    graph.add_conditional_edges('discuss_a',lambda s:after_discussion(s,'discuss_b'))
    graph.add_conditional_edges('discuss_b',lambda s:after_discussion(s,'propose'))
    graph.add_conditional_edges('propose',lambda s:'propose' if s['status']=='retry' else after_discussion(s,'run_tests'))
    graph.add_conditional_edges('run_tests',lambda s:END if s['status']=='blocked' else 'bootstrap' if s['status']=='scaffold_needed' else 'accept')
    graph.add_conditional_edges('bootstrap',lambda s:END if s['status']=='blocked' else 'run_tests')
    def advance(state):
        if state['status']=='blocked':return END
        if state['status']=='retry':return 'propose'
        if ops.checkin_due(state):return 'prepare_demo'
        if state['phase']!='red':return 'propose'
        if ops.demo_due(state):return 'prepare_demo'
        return 'discuss_a'
    graph.add_conditional_edges('accept',advance)
    graph.add_conditional_edges('prepare_demo',lambda s:END if s['status']=='blocked' else 'business')
    graph.add_conditional_edges('business',lambda s:END if s['status'] in {'accepted','blocked','rejected'} else 'discuss_a')
    return graph.compile(checkpointer=checkpointer)


class ProbeOperations:
    """Dependency adapter for the production routing, not a reference graph."""
    confirmed, refactoring = True, False
    def __init__(self,ports):self.ports=ports
    def initialize(self,state):return {'phase':'red','cycle':1,'status':'running','goal':'Two probe cycles','required':[],'since_feedback':0}
    def confirm(self,state):return {}
    def baseline(self,state):return {}
    def discuss(self,actor,state):return {}
    def propose(self,actor,phase,state):return {'pending':self.ports.agent(actor,phase)}
    def test(self,state):return {'report':self.ports.run_tests(state['pending'])}
    def accept(self,state):return {'status':'running'}
    def reject(self,state,reason):return {'status':'blocked','reason':reason}
    def bootstrap(self,state):return {'status':'blocked'}
    def checkin_due(self,state):return False
    def demo_due(self,state):return state['cycle']>2
    def prepare_demo(self,state):return {'demo':{'kind':'demo','message':'Probe complete'}}
    def feedback(self,state,answer):return {'status':'accepted' if answer=='accept' else 'blocked'}


def probe_factory(ports):
    from langgraph.checkpoint.memory import InMemorySaver
    return build_graph(ProbeOperations(ports),InMemorySaver())
