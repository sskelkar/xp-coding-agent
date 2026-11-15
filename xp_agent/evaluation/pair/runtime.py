"""Run the pair graph, Money acceptance, and evidence grading."""
import json
from pathlib import Path
import tempfile
import uuid

from ... import tracing
from ...pairing.session import PairSession
from .contracts import grade_contract
from .graph_probe import probe_factory, probe_graph
from .money import evaluate_money
from .money_fixture import GOAL, ScriptedPartner


def run_money(output,
              project,
              *,
              partners=None,
              provider='codex',
              model=None,
              auth='cli',
              budget=900):
    session = PairSession.create(output,
                                 project,
                                 GOAL,
                                 partners=partners,
                                 provider=provider,
                                 model=model,
                                 auth=auth,
                                 budget=budget,
                                 max_cycles=8)
    result = session.advance()
    if not result['interrupts'] or result['interrupts'][0]['kind'] != 'confirm_goal':
        raise RuntimeError('Outcome confirmation missing')
    result = session.advance('confirm', expected_interrupt=result['interrupt_token'])
    demos = 0
    while result['interrupts']:
        event = result['interrupts'][0]
        if event['kind'] == 'progress_update':
            result = session.advance('continue', expected_interrupt=result['interrupt_token'])
            continue
        if event['kind'] != 'working_demo':
            break  # Do not invent business answers.
        demos += 1
        acceptance = evaluate_money(session.path / 'workspace', stage='exchange')
        if acceptance['passed']:
            result = session.advance('accept', expected_interrupt=result['interrupt_token'])
            break
        if demos >= 4:
            break
        result = session.advance('continue', expected_interrupt=result['interrupt_token'])
    final = evaluate_money(session.path / 'workspace',
                           stage='exchange') if result['status'] == 'accepted' else None
    state = json.loads((session.path / 'pair-state.json').read_text())
    roles = [
        f"{e['actor']}:{e['phase']}" for e in state['records']
        if e['kind'] == 'step' and e['phase'] in {'red', 'green'}
    ]
    contract = grade_contract(json.loads((session.path / 'pair-evidence.json').read_text()))
    return {
        'passed':
        result['status'] == 'accepted' and final is not None and final['passed']
        and contract['passed'],
        'mode':
        'scripted_partners' if partners else 'live_partners',
        'status':
        result['status'],
        'observed_roles':
        roles,
        'contract_grade':
        contract,
        'demos':
        demos,
        'money_acceptance':
        final,
        'session':
        str(session.path)
    }


def evaluate(output, *, live=False, provider='codex', model=None, auth='cli', trace=False):
    probes = [
        probe_graph(probe_factory, scenario=s)
        for s in ('success', 'red_already_green', 'green_fails')
    ]
    scratch = Path.cwd() / '.xp-runs'
    scratch.mkdir(exist_ok=True, mode=0o700)
    root = Path(output).parent / ('pair-run-' + uuid.uuid4().hex[:12])
    with tracing.operation('xp.evaluation',
                           enabled=trace,
                           directory=Path(output).parent / 'pair-eval-traces',
                           mode='pair') as active:
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            partners = None if live else {a: ScriptedPartner(a) for a in ('A', 'B')}
            report = run_money(root,
                               tmp,
                               partners=partners,
                               provider=provider,
                               model=model,
                               auth=auth)
        checks = report['contract_grade'].get('checks', {})
        tracing.set_scores({
            'pair_ownership_valid':
            checks.get('ownership'),
            'handoff_state_valid':
            all(checks[k]
                for k in ('revision_chain', 'runner_binding', 'ordering')) if checks else None,
            'independent_acceptance_passed':
            report['money_acceptance']['passed']
            if report['money_acceptance'] is not None else None,
            'evidence_complete':
            report['contract_grade']['status'] != 'insufficient_evidence',
            'tdd_sequence': {
                'passed': 'complete',
                'failed': 'violation',
                'valid_partial': 'valid_partial',
                'insufficient_evidence': 'insufficient_evidence'
            }[report['contract_grade']['status']]
        })
        report['trace_id'] = active.trace_id if active else None
    report['production_graph_probes'] = probes
    report['passed'] = report['passed'] and all(p['passed'] for p in probes)
    report['verification'] = {
        'production_routing': all(p['passed'] for p in probes),
        'real_docker_money': bool(report['money_acceptance']
                                  and report['money_acceptance']['passed']),
        'accepted_transition_records': report['contract_grade']['passed'],
        'live_model_coding': live and report['passed'],
        'llm_judge_used': False
    }
    return report
