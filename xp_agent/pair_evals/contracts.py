"""Pure checks over supplied controller records, not proof of record authenticity.

The caller must capture these records from controller actions and bind runner
reports to actual artifacts. This module neither executes nor orchestrates agents.
"""
import math
import ast

STEP_FIELDS = {'actor', 'cycle', 'phase', 'before', 'after', 'agreement', 'context', 'history', 'report'}
GATES = ('ownership', 'ordering', 'revision_chain', 'runner_binding', 'tdd',
         'edit_scope', 'memory_delivery', 'business', 'demo', 'recovery', 'cadence')


def _validate(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value.get('version') not in (1,2):
        raise ValueError('Expected evidence version 1 or 2')
    events, snapshots = value['events'], value['snapshots']
    if not isinstance(events, list) or not events or not isinstance(snapshots, dict) or not snapshots:
        raise ValueError('Nonempty events and snapshots required')
    if value['status'] not in {'completed', 'blocked', 'cancelled', 'waiting'}:
        raise ValueError('Unknown run status')
    for revision, files in snapshots.items():
        if not isinstance(revision, str) or not isinstance(files, dict) or (not files and value['version']==1):
            raise ValueError('Invalid snapshot')
        if not all(isinstance(p, str) and isinstance(c, str) for p, c in files.items()):
            raise ValueError('Snapshots must contain text file mappings')
    for e in events:
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e[k] for k in ('id', 'kind', 'actor')):
            raise ValueError('Invalid event identity')
        if e['kind'] not in ({'agreement', 'step', 'question', 'demo', 'feedback'} | ({'bootstrap'} if value['version']==2 else set())):
            raise ValueError('Unknown event kind')
        if 'active_seconds' in e and (type(e['active_seconds']) not in (int, float)
                or not math.isfinite(e['active_seconds']) or e['active_seconds'] < 0):
            raise ValueError('Invalid active time')
        if e['kind'] == 'agreement' and type(e.get('revision')) is not int:
            raise ValueError('Agreement revision required')
        if e['kind']=='bootstrap' and not isinstance(e.get('checked'),str):
            raise ValueError('Bootstrap validation snapshot required')
        if e['kind'] in {'step','bootstrap'}:
            if not STEP_FIELDS <= e.keys() or type(e['cycle']) is not int or type(e['agreement']) is not int:
                raise ValueError('Missing step evidence')
            if not all(isinstance(e[k], str) and e[k] for k in ('phase', 'before', 'after', 'context')):
                raise ValueError('Invalid step fields')
            if not isinstance(e['history'], list) or not all(isinstance(x, str) for x in e['history']):
                raise ValueError('History identifiers required')
            r = e['report']
            if not isinstance(r, dict) or type(r.get('returncode')) is not int or not isinstance(r.get('revision'), str):
                raise ValueError('Invalid runner report')
            for k in ('passed', 'failed', 'errors', 'skipped', 'required'):
                if not isinstance(r.get(k), list) or not all(isinstance(t, str) and t for t in r[k]):
                    raise ValueError('Missing runner test identities')
                if len(set(r[k])) != len(r[k]):
                    raise ValueError('Duplicate test identity')
        if e['kind'] == 'demo':
            if not isinstance(e.get('revision'), str) or not isinstance(e.get('samples'), list) or not e['samples']:
                raise ValueError('Demo execution samples required')
            if not all(isinstance(x, dict) and {'input', 'expected', 'actual'} <= x.keys() for x in e['samples']):
                raise ValueError('Invalid demo samples')
        if e['kind'] == 'feedback' and (not isinstance(e.get('demo'), str) or type(e.get('revision')) is not int
                                      or e.get('decision') not in {'continue', 'revise', 'accept', 'reject'}):
            raise ValueError('Invalid business response')
    return events, snapshots


def grade_contract(evidence, *, max_cycles=3, max_active_seconds=300):
    """Check accepted steps, histories and business boundaries in offline evidence.

    Test changes after red are deliberately refused: guarded adaptation is not
    implemented. Version 2 adds controlled bootstrap. Rejected attempts and full
    crash-recovery ledgers remain outside this accepted-transition view.
    """
    result = {'passed': False, 'status': 'insufficient_evidence', 'violations': [],
              'evidence_kind': 'offline_controller_records', 'runtime_verified': False,
              'limitations': ['Caller-supplied records; no execution or authenticity verification.',
                              'History delivery is not proof that a model used its memory.',
                              'Demo samples are declared evidence, not independently executed here.',
                              'Version 2 supports controlled bootstrap; rejected attempts, guarded test adaptation and crash recovery remain unqualified.']}
    try:
        events, snapshots = _validate(evidence)
    except (KeyError, TypeError, ValueError) as exc:
        return {**result, 'reason': str(exc)}
    if type(max_cycles) is not int or max_cycles < 1 or max_active_seconds <= 0:
        raise ValueError('Positive cadence limits required')
    violations = set()
    seen, contexts = set(), {}
    history_order, demo_ids = [], set()
    pending_bootstrap = []
    current, phase, cycle, author = None, 'red', 1, 'A'
    agreement, waiting, accepted_business = None, None, False
    green = False
    previous_tests, red_tests = set(), set()
    cycles_since_feedback, last_time, feedback_time = 0, 0, 0
    for e in events:
        if e['id'] in seen:
            violations.add('recovery')
        active_time = e.get('active_seconds', last_time)
        if active_time < last_time:
            violations.add('cadence')
        last_time = active_time
        kind = e['kind']
        if kind == 'agreement':
            if agreement is not None or e['actor'] != 'user' or e['revision'] < 1 or seen:
                violations.add('business')
            agreement = e['revision']
        elif kind == 'bootstrap':
            if agreement is None or e['agreement']!=agreement or waiting or phase!='red' or pending_bootstrap:
                violations.add('business')
            if e['cycle']!=cycle or e['phase']!='bootstrap':violations.add('ordering')
            if e['actor']!=('B' if author=='A' else 'A'):violations.add('ownership')
            before, after = snapshots.get(e['before']),snapshots.get(e['after'])
            checked = snapshots.get(e.get('checked'))
            if before is None or after is None or checked is None or (current is not None and current!=e['before']):
                violations.add('revision_chain')
            else:
                changed={p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)}
                if not changed or any(_is_test(p) or not p.endswith('.py') for p in changed):violations.add('edit_scope')
                try:
                    for p in changed:
                        old=ast.parse(before.get(p,'')).body; new=ast.parse(after.get(p,'')).body
                        if [ast.dump(n) for n in new[:len(old)]]!=[ast.dump(n) for n in old]:violations.add('edit_scope')
                except (SyntaxError,TypeError):violations.add('edit_scope')
                if any(after.get(p)!=checked.get(p) for p in after.keys()|checked.keys() if not _is_test(p)):
                    violations.add('edit_scope')
            report=e['report']
            if report['revision']!=e.get('checked'):violations.add('runner_binding')
            if (report['returncode']!=1 or not report['failed'] or report['errors'] or report['skipped']
                    or not (previous_tests|set(report['required']))<=set(report['passed'])):violations.add('tdd')
            if e['history']!=history_order:violations.add('memory_delivery')
            if e['actor'] in contexts and contexts[e['actor']]!=e['context']:violations.add('memory_delivery')
            contexts[e['actor']]=e['context']
            current=e['after'];pending_bootstrap=[e['id']]
        elif kind == 'step':
            if agreement is None or e['agreement'] != agreement or waiting or accepted_business:
                violations.add('business')
            dispatch=e.get('dispatch_active',active_time)
            if type(dispatch) not in (int,float) or not math.isfinite(dispatch) or not 0<=dispatch<=active_time:
                violations.add('cadence')
                dispatch=active_time
            if cycles_since_feedback >= max_cycles or dispatch - feedback_time >= max_active_seconds:
                violations.add('cadence')
            expected_actor = author if phase == 'red' else {'A': 'B', 'B': 'A'}[author]
            if e['actor'] != expected_actor:
                violations.add('ownership')
            if e['cycle'] != cycle or e['phase'] != phase:
                violations.add('ordering')
            if current is not None and e['before'] != current:
                violations.add('revision_chain')
            before, after = snapshots.get(e['before']), snapshots.get(e['after'])
            if before is None or after is None:
                violations.add('revision_chain')
            elif phase == 'red':
                changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
                if not changed or any(not _is_test(p) for p in changed):
                    violations.add('edit_scope')
            elif any(before.get(p) != after.get(p) for p in before.keys() | after.keys() if _is_test(p)):
                violations.add('edit_scope')
            if e['actor'] not in {'A', 'B'}:
                violations.add('ownership')
            else:
                other = 'B' if e['actor'] == 'A' else 'A'
                if (e['actor'] in contexts and contexts[e['actor']] != e['context']) or contexts.get(other) == e['context']:
                    violations.add('memory_delivery')
                contexts[e['actor']] = e['context']
            expected_history=[x for x in history_order if x not in pending_bootstrap] if phase=='red' else history_order
            if e['history'] != expected_history:
                violations.add('memory_delivery')
            pending_bootstrap=[]
            r = e['report']
            if r['revision'] != e['after']:
                violations.add('runner_binding')
            passed, failed = set(r['passed']), set(r['failed'])
            if passed & failed or r['errors'] or r['skipped']:
                violations.add('tdd')
            if phase == 'red':
                if r['returncode'] != 1 or not failed or not (previous_tests | set(r['required'])) <= passed or (previous_tests | set(r['required'])) & failed:
                    violations.add('tdd')
                red_tests = passed | failed
                green = False
                phase = 'green'
            else:
                if r['returncode'] != 0 or not passed or failed or not (red_tests | previous_tests | set(r['required'])) <= passed:
                    violations.add('tdd')
                previous_tests = passed
                green = True
                if phase == 'green':
                    phase = 'refactor'
                else:
                    phase, author, cycle = 'red', ('B' if author == 'A' else 'A'), cycle + 1
                    cycles_since_feedback += 1
            current = e['after']
        elif kind == 'question':
            if agreement is None or waiting or accepted_business:
                violations.add('business')
            waiting = e['id']
        elif kind == 'demo':
            if e['actor'] != 'controller' or e['revision'] != current or not green or phase != 'red':
                violations.add('demo')
            if any(x['actual'] != x['expected'] for x in e['samples']):
                violations.add('demo')
            if waiting:
                violations.add('business')
            waiting = e['id']
            demo_ids.add(e['id'])
        elif kind == 'feedback':
            if e['actor'] != 'user' or e['demo'] != waiting or waiting is None:
                violations.add('business')
            if e['decision'] == 'revise':
                if agreement is None or e['revision'] != agreement + 1:
                    violations.add('business')
                agreement = e['revision']
            elif e['revision'] != agreement:
                violations.add('business')
            if e['decision'] == 'accept':
                if e['demo'] not in demo_ids:
                    violations.add('demo')
                if not green or phase != 'red':
                    violations.add('business')
                accepted_business = True
            waiting = None if e['decision'] != 'reject' else e['id']
            cycles_since_feedback, feedback_time = 0, active_time
        seen.add(e['id'])
        history_order.append(e['id'])
    if evidence['status'] == 'completed' and (not accepted_business or waiting or not green or phase != 'red' or cycle < 2):
        violations.add('business')
    result.update(violations=sorted(violations), completed_cycles=cycle - 1,
                  checks={g: g not in violations for g in GATES},
                  active_time_evidence=all('active_seconds' in e for e in events))
    result['status'] = 'failed' if violations else 'passed' if evidence['status'] == 'completed' else 'valid_partial'
    result['passed'] = result['status'] == 'passed'
    return result


def _is_test(path):
    return path.endswith('.py') and (path.split('/')[-1].startswith('test_') or path.split('/')[-1].endswith('_test.py'))
