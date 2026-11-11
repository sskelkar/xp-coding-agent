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
    assert report['demos']>=2
    assert not list(project.iterdir())
    state=json.loads((tmp_path/'run/pair-state.json').read_text())
    assert len(state['histories']['A'])>10
    assert any(m['actor']=='B' for m in state['histories']['A'])
    assert any(m['actor']=='user' and m['phase']=='feedback' for m in state['histories']['B'])
    assert (tmp_path/'run/checkpoints.sqlite').exists()
