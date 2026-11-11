from xp_agent.pair_evals.graph_probe import probe_graph
from xp_agent.pairing.graph import probe_factory


def test_production_graph_is_used_by_the_handoff_probe():
    for scenario in ('success','red_already_green','green_fails'):
        result=probe_graph(probe_factory,scenario=scenario)
        assert result['passed'], result
