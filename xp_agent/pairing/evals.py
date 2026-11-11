"""Deterministic Money integration participants, separate from hosted partners."""
from copy import deepcopy
from .session import Session
from ..pair_evals.money import evaluate_money

SCAFFOLD='''def make(value, currency="USD"):
    return {"amount":value,"currency":currency}
def amount_of(money): return money["amount"]
def currency_of(money): return money["currency"]
def multiply(money, factor): return make(0,currency_of(money))
'''
MUTABLE=SCAFFOLD.replace('return make(0,currency_of(money))','money["amount"] *= factor; return money')
IMMUTABLE=SCAFFOLD.replace('return make(0,currency_of(money))','return make(amount_of(money)*factor,currency_of(money))')
ADD_STUB='\ndef add_money(left,right,rates): return make(0,currency_of(left))\n'
ADD='''
def add_money(left,right,rates):
    value=amount_of(right)
    if currency_of(left)!=currency_of(right):
        key=currency_of(right)+"/"+currency_of(left)
        if key not in rates: raise ValueError("Missing rate")
        value=value//rates[key]
    return make(amount_of(left)+value,currency_of(left))
'''
TESTS=[
'''def test_multiplication():
    import money_api as api
    assert api.amount_of(api.multiply(api.make(5,"USD"),2))==10
''',
'''def test_reusable_original():
    import money_api as api
    original=api.make(5,"USD")
    twice=api.multiply(original,2)
    thrice=api.multiply(original,3)
    assert api.amount_of(original)==5
    assert api.amount_of(twice)==10
    assert api.amount_of(thrice)==15
''',
'''def test_addition():
    import money_api as api
    assert api.amount_of(api.add_money(api.make(5,"USD"),api.make(10,"CHF"),{"CHF/USD":2}))==10
''']
GOAL='''Implement a tiny Money API: make(value,currency), amount_of(money), currency_of(money), multiply(money,factor), and add_money(left,right,rates).
Amounts are nonnegative integers and multipliers positive integers. Multiplication preserves currency and leaves the original reusable. Addition returns the left currency and leaves both originals unchanged. A CHF/USD rate of 2 means two CHF per USD. Evaluate exact integer conversions only; missing rates raise ValueError. Start with multiplication, discover the design through small TDD cycles. No new dependencies.'''


def response(action='comment',message='Consider one next behavior.',edits=None,examples=None):
    return dict(action=action,message=message,edits=[{'path':p,'content':c} for p,c in (edits or {}).items()],examples=examples or [])


class ScriptedPartner:
    """Test double supplying code; not evidence of model coding quality."""
    def __init__(self,identity):self.identity=identity;self.calls=[]
    def reply(self,phase,state):
        self.calls.append((phase,deepcopy(state['histories'][self.identity])))
        cycle=state['cycle']
        if phase=='discuss':return response(action='demo' if cycle>3 else 'comment')
        if phase=='bootstrap':return response('edit',edits={'money_api.py':SCAFFOLD if cycle==1 else IMMUTABLE+ADD_STUB})
        if phase=='red':return response('edit',edits={'test_money.py':state['files'].get('test_money.py','')+'\n'+TESTS[cycle-1]})
        if phase=='green':return response('edit',edits={'money_api.py':MUTABLE if cycle==1 else IMMUTABLE if cycle==2 else IMMUTABLE+ADD})
        if phase=='refactor':return response(message='The small functions are clear; no cleanup needed.')
        if phase=='demo':return response('demo',message='Five dollars times two produces ten.',examples=[
            {'label':'Five dollars doubled','module':'money_api','expression':'api.amount_of(api.multiply(api.make(5,"USD"),2))','expected':10}])
        raise ValueError('Unexpected scripted phase')


def run_money(output,project,*,partners=None,provider='codex',model=None,auth='cli',budget=900):
    session=Session.create(output,project,GOAL,partners=partners,provider=provider,model=model,auth=auth,budget=budget,max_cycles=8)
    result=session.advance()
    if not result['interrupts'] or result['interrupts'][0]['kind']!='confirm_goal':raise RuntimeError('Outcome confirmation missing')
    result=session.advance('confirm',expected_interrupt=result['interrupt_token'])
    demos=0
    while result['interrupts']:
        event=result['interrupts'][0]
        if event['kind']=='progress_update':
            result=session.advance('continue',expected_interrupt=result['interrupt_token']);continue
        if event['kind']!='working_demo':break  # Do not invent business answers.
        demos+=1
        acceptance=evaluate_money(session.path/'workspace',stage='exchange')
        if acceptance['passed']:
            result=session.advance('accept',expected_interrupt=result['interrupt_token']);break
        if demos>=4:break
        result=session.advance('continue',expected_interrupt=result['interrupt_token'])
    final=evaluate_money(session.path/'workspace',stage='exchange') if result['status']=='accepted' else None
    state=__import__('json').loads((session.path/'pair-state.json').read_text())
    roles=[f"{e['actor']}:{e['phase']}" for e in state['records'] if e['kind']=='step' and e['phase'] in {'red','green'}]
    from ..pair_evals.contracts import grade_contract
    contract=grade_contract(__import__('json').loads((session.path/'pair-evidence.json').read_text()))
    return {'passed':result['status']=='accepted' and final is not None and final['passed'] and contract['passed'],
            'mode':'scripted_partners' if partners else 'live_partners','status':result['status'],
            'observed_roles':roles,'contract_grade':contract,'demos':demos,'money_acceptance':final,'session':str(session.path)}



def evaluate(output,*,live=False,provider='codex',model=None,auth='cli',trace=False):
    from pathlib import Path
    import tempfile,uuid
    from ..pair_evals.graph_probe import probe_graph
    from .graph import probe_factory
    probes=[probe_graph(probe_factory,scenario=s) for s in ('success','red_already_green','green_fails')]
    scratch=Path.cwd()/'.xp-runs';scratch.mkdir(exist_ok=True,mode=0o700)
    root=Path(output).parent/('pair-run-'+uuid.uuid4().hex[:12])
    from .. import tracing
    with tracing.operation('xp.evaluation',enabled=trace,directory=Path(output).parent/'pair-eval-traces',mode='pair') as active:
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            partners=None if live else {a:ScriptedPartner(a) for a in ('A','B')}
            report=run_money(root,tmp,partners=partners,provider=provider,model=model,auth=auth)
        checks=report['contract_grade'].get('checks',{})
        tracing.set_scores({'pair_ownership_valid':checks.get('ownership'),
            'handoff_state_valid':all(checks[k] for k in ('revision_chain','runner_binding','ordering')) if checks else None,
            'independent_acceptance_passed':bool(report['money_acceptance'] and report['money_acceptance']['passed']),
            'evidence_complete':report['contract_grade']['status']!='insufficient_evidence',
            'tdd_sequence':{'passed':'complete','failed':'violation','valid_partial':'valid_partial','insufficient_evidence':'insufficient_evidence'}[report['contract_grade']['status']]})
        report['trace_id']=active.trace_id if active else None
    report['production_graph_probes']=probes
    report['passed']=report['passed'] and all(p['passed'] for p in probes)
    report['verification']={'production_routing':all(p['passed'] for p in probes),
                            'real_docker_money':bool(report['money_acceptance'] and report['money_acceptance']['passed']),
                            'accepted_transition_records':report['contract_grade']['passed'],
                            'live_model_coding':live and report['passed'],'llm_judge_used':False}
    return report
