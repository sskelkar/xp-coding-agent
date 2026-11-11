from copy import deepcopy
import pytest


def trace():
    # Controller evidence fixture, not a real two-agent runtime.
    events = [dict(kind='agreement', id='agreement-1', actor='user', revision=1)]
    snapshots = {'v0': {'money.py': 'pass\n', 'test_money.py': 'pass\n'}}
    current = 'v0'
    for cycle, author, implementer in [(1, 'A', 'B'), (2, 'B', 'A')]:
        for phase, actor in [('red', author), ('green', implementer), ('refactor', implementer)]:
            next_revision = f'v{len(snapshots)}'
            files = dict(snapshots[current])
            files['test_money.py' if phase == 'red' else 'money.py'] += f'# {cycle}-{phase}\n'
            snapshots[next_revision] = files
            events.append(dict(kind='step', id=f'{cycle}-{phase}', actor=actor, cycle=cycle,
                               phase=phase, before=current, after=next_revision, agreement=1,
                               context=f'context-{actor}', history=[e['id'] for e in events],
                               report=dict(returncode=1 if phase == 'red' else 0,
                                           passed=['old'], failed=[f'new-{cycle}'] if phase == 'red' else [],
                                           errors=[], skipped=[], revision=next_revision,
                                           required=['old'] if phase == 'red' else ['old', f'new-{cycle}'])))
            if phase != 'red': events[-1]['report']['passed'].append(f'new-{cycle}')
            if cycle == 2: events[-1]['report']['passed'].append('new-1')
            current = next_revision
    events += [dict(kind='demo', id='demo-1', actor='controller', revision=current,
                    samples=[dict(input='5 times 2', expected='10', actual='10')]),
               dict(kind='feedback', id='feedback-1', actor='user', demo='demo-1',
                    decision='accept', revision=1)]
    return dict(version=1, events=events, snapshots=snapshots, status='completed')


def grade(value):
    from xp_agent.pair_evals.contracts import grade_contract
    return grade_contract(value)


def test_valid_two_cycle_evidence_and_empty_evidence_have_different_outcomes():
    assert grade(trace())['status'] == 'passed'
    assert grade({})['status'] == 'insufficient_evidence'


@pytest.mark.parametrize('mutate,gate', [
    (lambda x: x['events'][2].update(actor='A'), 'ownership'),
    (lambda x: x['events'][4].update(actor='A'), 'ownership'),
    (lambda x: x['events'][1].update(before='missing'), 'revision_chain'),
    (lambda x: x['events'][1]['report'].update(returncode=0, failed=[]), 'tdd'),
    (lambda x: x['events'][2]['report'].update(errors=['broken']), 'tdd'),
    (lambda x: x['events'][2]['report'].update(passed=['new-1']), 'tdd'),
    (lambda x: x['events'][2]['report'].update(revision='v0'), 'runner_binding'),
    (lambda x: x['events'][4].update(context='reset-B'), 'memory_delivery'),
    (lambda x: x['events'][4].update(history=[]), 'memory_delivery'),
    (lambda x: x['events'][1].update(agreement=2), 'business'),
    (lambda x: x['events'][-1].update(actor='A'), 'business'),
    (lambda x: x['events'][-2]['samples'][0].update(actual='5'), 'demo'),
    (lambda x: x['events'].pop(), 'business'),
    (lambda x: x['events'][2].update(id=x['events'][1]['id']), 'recovery'),
    (lambda x: x['snapshots']['v1'].update(**{'money.py': 'changed during red'}), 'edit_scope'),
    (lambda x: x['snapshots']['v2'].update(**{'test_money.py': 'assert True'}), 'edit_scope'),
])
def test_corrupted_controller_evidence_is_not_accepted(mutate, gate):
    evidence = trace()
    mutate(evidence)
    result = grade(evidence)
    assert result['status'] == 'failed', result
    assert gate in result['violations'], result


def test_business_wait_blocks_coding_until_response_even_if_revision_is_green():
    value = trace()
    value['events'].insert(4, dict(kind='question', id='question-1', actor='B', agreement=1))
    assert 'business' in grade(value)['violations']


def test_feedback_revision_is_used_by_subsequent_work():
    value = trace()
    value['events'][4:4] = [dict(kind='demo', id='demo-mid', actor='controller', revision='v3',
                                 samples=[dict(input='5 times 2', expected='10', actual='10')]),
                            dict(kind='feedback', id='clarify', actor='user', demo='demo-mid',
                                 decision='revise', revision=2)]
    for event in value['events'][6:]:
        if event['kind'] == 'step':
            event['agreement'] = 2
            event['history'] = [e['id'] for e in value['events'][:value['events'].index(event)]]
    value['events'][-1]['revision'] = 2
    assert grade(value)['status'] == 'passed'


def test_missing_phase_and_zero_test_green_fail():
    value = trace()
    value['events'][2]['report']['passed'] = []
    assert 'tdd' in grade(value)['violations']
    value = trace()
    value['events'].pop(3)
    assert 'ordering' in grade(value)['violations']


def test_partial_red_is_not_completed_and_late_business_reply_cannot_create_success():
    value = trace()
    value['events'] = value['events'][:2]
    value['status'] = 'blocked'
    result = grade(value)
    assert result['status'] == 'valid_partial'
    assert not result['passed']


def test_malformed_evidence_fails_closed_instead_of_crashing():
    for evidence in (None, [], {'version': 1, 'events': [None]}, {'version': 1, 'events': [], 'snapshots': {}}):
        assert grade(evidence)['status'] == 'insufficient_evidence'


def test_history_order_and_missing_demo_are_not_hidden_by_matching_identifiers():
    value = trace()
    value['events'][4]['history'].reverse()
    assert 'memory_delivery' in grade(value)['violations']
    value = trace()
    value['events'][-2] = dict(kind='question', id='demo-1', actor='B', agreement=1)
    assert 'demo' in grade(value)['violations']


def test_cadence_rejects_work_after_deadline_or_cycle_limit():
    value = trace()
    for i, e in enumerate(value['events']): e['active_seconds'] = i * 100
    assert 'cadence' in grade(value)['violations']
    from xp_agent.pair_evals.contracts import grade_contract
    assert 'cadence' in grade_contract(trace(), max_cycles=1)['violations']


def test_first_red_cannot_drop_declared_baseline_and_demo_requires_samples():
    value = trace()
    value['events'][1]['report']['passed'] = []
    assert 'tdd' in grade(value)['violations']
    value = trace();value['events'][-2]['samples'] = []
    assert grade(value)['status'] == 'insufficient_evidence'


def test_duplicate_feedback_and_wrong_refactor_writer_fail():
    value = trace();value['events'].append(deepcopy(value['events'][-1]))
    assert {'business','recovery'} <= set(grade(value)['violations'])
    value = trace();value['events'][3]['actor'] = 'A'
    assert 'ownership' in grade(value)['violations']


def test_current_schema_explicitly_refuses_test_evolution_and_bootstrap():
    value = trace();value['events'][1]['kind'] = 'bootstrap'
    assert grade(value)['status'] == 'insufficient_evidence'
    value = trace();value['events'][3]['phase'] = 'adapt_tests'
    assert 'ordering' in grade(value)['violations']
