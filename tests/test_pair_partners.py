import json
import pytest
from xp_agent.pairing.partners import Partner,parse_reply


def response():return dict(action='comment',message='Use the prior business decision.',edits=[],examples=[])


def test_partner_replays_its_own_continuing_history_without_legacy_plan_prompt():
    captured=[]
    class Backend:
        def request(self,prompt,schema,timeout):captured.append(prompt);return json.dumps(response())
    state=dict(goal='Money',agreement=2,files={},histories={'A':[{'message':'No mutation'}],'B':[{'message':'Other history'}]},remaining=60)
    Partner('A',backend=Backend()).reply('discuss',state)
    assert 'No mutation' in captured[0] and 'Other history' not in captured[0]
    assert 'PLAN: return no edits' not in captured[0]


def test_pair_reply_refuses_tool_like_extra_fields_and_duplicate_paths():
    with pytest.raises(ValueError):parse_reply({**response(),'command':'run something'})
    value=response();value['edits']=[{'path':'x.py','content':'pass'}]*2
    with pytest.raises(ValueError,match='Duplicate'):parse_reply(value)


def test_pair_trace_keeps_static_discussion_bootstrap_and_demo_phase_labels():
    from xp_agent import tracing
    for phase in ('discuss','bootstrap','demo'):
        assert tracing.attributes({'actor':'B','phase':phase,'message':'private business text'})=={'actor':'B','phase':phase}
