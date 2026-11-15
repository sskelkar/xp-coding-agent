import os
import json
import pytest
from xp_agent.evaluation.pair.money_fixture import GOAL, ScriptedPartner, response
from xp_agent.evaluation.pair.runtime import run_money


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Real pair runtime with Docker')
@pytest.mark.parametrize('recover', [True, False])
def test_actual_pair_graph_retries_scaffolding_before_money_acceptance(tmp_path, recover):

    class ScaffoldPartner(ScriptedPartner):

        def reply(self, phase, state):
            if phase == 'bootstrap' and state['cycle'] == 1:
                retry = any(call[0] == 'bootstrap' for call in self.calls)
                if retry:
                    assert 'NotImplementedError' in state['feedback']
                if not retry or not recover:
                    self.calls.append((phase, state['histories'][self.identity]))
                    scaffold = (
                        'def make(value, currency): raise NotImplementedError("missing behavior")\n'
                        'def multiply(money, factor): pass\n'
                        'def amount_of(money): pass\n')
                    return response('edit', edits={'money_api.py': scaffold})
            return super().reply(phase, state)

    project = tmp_path / 'project'
    project.mkdir()
    a, b = ScriptedPartner('A'), ScaffoldPartner('B')
    report = run_money(tmp_path / 'run', project, partners={'A': a, 'B': b})
    if not recover:
        assert report['status'] == 'blocked'
        assert report['observed_roles'] == []
        assert sum(call[0] == 'bootstrap' for call in b.calls) == 2
        assert not (tmp_path / 'run' / 'workspace' / 'money_api.py').exists()
        return
    assert report['passed'], report
    assert report['observed_roles'] == ['A:red', 'B:green', 'B:red', 'A:green', 'A:red', 'B:green']
    assert report['money_acceptance']['tests']['passed'] == 33
    grade = json.loads((tmp_path / 'run/pair-contract-grade.json').read_text())
    assert grade['passed'], grade
    assert report['demos'] >= 2
    assert sum(call[0] == 'bootstrap' for call in b.calls) == 3
    assert not list(project.iterdir())
    state = json.loads((tmp_path / 'run/pair-state.json').read_text())
    assert len(state['histories']['A']) > 10
    assert any(m['actor'] == 'B' for m in state['histories']['A'])
    assert any(m['actor'] == 'user' and m['phase'] == 'feedback' for m in state['histories']['B'])
    assert (tmp_path / 'run/checkpoints.sqlite').exists()


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='SQLite restart plus real Docker')
def test_reopen_session_preserves_histories_turns_budgets_and_final_patch(tmp_path):
    from xp_agent.pairing.session import PairSession
    from xp_agent.evaluation.pair.money import evaluate_money
    project = tmp_path / 'project'
    project.mkdir()
    path = tmp_path / 'run'
    first = PairSession.create(path,
                               project,
                               GOAL,
                               partners={a: ScriptedPartner(a)
                                         for a in ('A', 'B')})
    first.advance()
    second = PairSession(path, partners={a: ScriptedPartner(a) for a in ('A', 'B')})
    result = second.advance('confirm')
    assert result['interrupts'][0]['kind'] == 'working_demo'
    remaining = result['remaining_seconds']
    fresh = {a: ScriptedPartner(a) for a in ('A', 'B')}
    third = PairSession(path, partners=fresh)
    third.advance()  # Reading a waiting session must not call a partner again.
    assert not fresh['A'].calls and not fresh['B'].calls
    third.advance('continue')
    result = third.advance('accept')
    assert result['status'] == 'accepted' and result['remaining_seconds'] <= remaining
    assert result['contract_grade'] == 'passed'
    assert all(
        any(m['actor'] == 'user' and m['phase'] == 'feedback' for m in p.calls[0][1])
        for p in fresh.values())
    patch = (path / 'changes.patch').read_text()
    assert patch
    third.advance()
    assert (path / 'changes.patch').read_text() == patch
    assert evaluate_money(path / 'workspace', stage='exchange')['passed']
