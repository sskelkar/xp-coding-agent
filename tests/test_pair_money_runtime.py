import os
import json
import pytest
from xp_agent.pairing.evals import run_money,ScriptedPartner


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS')!='1',reason='Real pair runtime with Docker')
def test_actual_pair_graph_builds_money_from_empty_project_and_passes_oracle(tmp_path):
    project=tmp_path/'project';project.mkdir()
    a,b=ScriptedPartner('A'),ScriptedPartner('B')
    report=run_money(tmp_path/'run',project,partners={'A':a,'B':b})
    assert report['passed'],report
    assert report['observed_roles']==['A:red','B:green','B:red','A:green','A:red','B:green']
    assert report['money_acceptance']['tests']['passed']==33
    grade=json.loads((tmp_path/'run/pair-contract-grade.json').read_text())
    assert grade['passed'],grade
    assert report['demos']>=2
    assert not list(project.iterdir())
    state=json.loads((tmp_path/'run/pair-state.json').read_text())
    assert len(state['histories']['A'])>10
    assert any(m['actor']=='B' for m in state['histories']['A'])
    assert any(m['actor']=='user' and m['phase']=='feedback' for m in state['histories']['B'])
    assert (tmp_path/'run/checkpoints.sqlite').exists()


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS')!='1',reason='SQLite restart plus real Docker')
def test_reopen_session_preserves_histories_turns_budgets_and_final_patch(tmp_path):
    from xp_agent.pairing.session import Session
    from xp_agent.pairing.evals import GOAL
    from xp_agent.pair_evals.money import evaluate_money
    project=tmp_path/'project';project.mkdir()
    path=tmp_path/'run'
    first=Session.create(path,project,GOAL,partners={a:ScriptedPartner(a) for a in ('A','B')})
    first.advance()
    second=Session(path,partners={a:ScriptedPartner(a) for a in ('A','B')})
    result=second.advance('confirm')
    assert result['interrupts'][0]['kind']=='working_demo'
    remaining=result['remaining_seconds']
    fresh={a:ScriptedPartner(a) for a in ('A','B')}
    third=Session(path,partners=fresh)
    third.advance()  # Reading a waiting session must not call a partner again.
    assert not fresh['A'].calls and not fresh['B'].calls
    third.advance('continue')
    result=third.advance('accept')
    assert result['status']=='accepted' and result['remaining_seconds']<=remaining
    assert result['contract_grade']=='passed'
    assert all(any(m['actor']=='user' and m['phase']=='feedback' for m in p.calls[0][1]) for p in fresh.values())
    patch=(path/'changes.patch').read_text()
    assert patch
    third.advance()
    assert (path/'changes.patch').read_text()==patch
    assert evaluate_money(path/'workspace',stage='exchange')['passed']
