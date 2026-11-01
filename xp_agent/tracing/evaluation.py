"""Pure deterministic evidence checks. No LLM, SDK, network or source export."""
import re

VERSION = '1'
SCORE_NAMES = {'red_execution_valid','green_execution_valid','edit_scope_preserved',
               'pair_ownership_valid','handoff_state_valid','independent_acceptance_passed',
               'evidence_complete','tdd_sequence'}
ORDER = ['baseline','red','green','refactor','final']


def evaluate_state(state):
    rows=state.get('evidence',[])
    scores={name:None for name in SCORE_NAMES}
    scores.update(pair_ownership_valid='not_applicable',handoff_state_valid='not_applicable')
    required={'version','sequence','phase','accepted','before_hash','code_hash','before_source_hash',
              'source_hash','before_test_hash','test_hash','scope_valid','returncode','passed','failed','errors','skipped'}
    complete=bool(rows) and all(required<=r.keys() and r['version']==1 and r['sequence']==i and
        all(isinstance(r[k],list) and all(isinstance(t,str) for t in r[k]) for k in ('passed','failed','errors','skipped')) and
        all(isinstance(r[k],str) and re.fullmatch('[a-f0-9]{64}',r[k]) for k in
            ('before_hash','code_hash','before_source_hash','source_hash','before_test_hash','test_hash')) and
        type(r['accepted']) is bool and type(r['scope_valid']) is bool for i,r in enumerate(rows,1))
    scores['evidence_complete']=complete
    if not complete:
        scores['tdd_sequence']='insufficient_evidence'
        return scores
    accepted=[r for r in rows if r['accepted']]
    phases=[r['phase'] for r in accepted]
    valid=phases==ORDER[:len(phases)] and len(phases)<=len(ORDER)
    previous=None
    baseline=set()
    required_tests=set()
    red_checks=[]; green_checks=[]; scope_checks=[]
    for r in accepted:
        phase=r['phase']
        scope=r['scope_valid']
        if previous:
            scope &= all(r['before_'+k]==previous[k] for k in ('source_hash','test_hash'))
            scope &= r['before_hash']==previous['code_hash']
        if phase=='red':
            scope &= r['source_hash']==r['before_source_hash']
            red_checks.append(r['returncode']==1 and bool(r['failed']) and not r['errors'] and not r['skipped'] and
                              baseline<=set(r['passed']) and not baseline.intersection(r['failed']) and
                              r['test_hash']!=r['before_test_hash'])
            required_tests=set(r['passed']+r['failed'])
        else:
            if phase in {'green','refactor'}: scope &= r['test_hash']==r['before_test_hash']
            ok=r['returncode']==0 and bool(r['passed']) and not any(r[k] for k in ('failed','errors','skipped'))
            ok &= required_tests<=set(r['passed'])
            if phase in {'green','refactor','final'}: green_checks.append(ok)
            else:
                valid &= ok
                baseline=set(r['passed'])
        if phase in {'baseline','final'}: scope &= r['before_hash']==r['code_hash']
        scope_checks.append(scope)
        previous=r
    scores.update(red_execution_valid=all(red_checks) if red_checks else None,
                  green_execution_valid=all(green_checks) if green_checks else None,
                  edit_scope_preserved=all(scope_checks) if scope_checks else None)
    valid &= all(red_checks+green_checks+scope_checks)
    if state.get('status')=='verified' and phases!=ORDER: valid=False
    scores['tdd_sequence']='violation' if not valid else 'complete' if phases==ORDER and state.get('status')=='verified' else 'valid_partial'
    return scores


def evaluate_pair(events):
    """Synthetic future contract only: A-red/B-green then B-red/A-green.

    IDs stand for separate contexts managed by a future pairing controller.
    This validator does not create partners or establish context isolation.
    """
    owner='A'; expected='red'; last=None; ownership=True; handoff=True
    for i,event in enumerate(events,1):
        if event.get('sequence')!=i or event.get('phase')!=expected or event.get('actor') != (owner if expected=='red' else {'A':'B','B':'A'}[owner]): ownership=False
        if not event.get('accepted') or not event.get('artifact') or event.get('before')!=last: handoff=False
        last=event.get('artifact')
        if expected=='green': owner={'A':'B','B':'A'}[owner]
        expected='green' if expected=='red' else 'red'
    return {'pair_ownership_valid':ownership if events else None,'handoff_state_valid':handoff if events else None}


def combine_scores(items,status):
    if not items: return evaluate_state({})
    result={}
    for name in SCORE_NAMES-{'tdd_sequence'}:
        values=[item[name] for item in items]
        result[name]=False if False in values else None if None in values else values[0]
    categories=[item['tdd_sequence'] for item in items]
    result['tdd_sequence']=('insufficient_evidence' if 'insufficient_evidence' in categories else
        'violation' if 'violation' in categories else
        'complete' if status=='verified' and all(c=='complete' for c in categories) else 'valid_partial')
    return result
