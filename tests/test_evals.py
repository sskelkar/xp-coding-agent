import os
import pytest
from xp_agent.evals import evaluate

@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Requires real Docker execution')
def test_adversarial_fixture_evals_pass():
    report = evaluate()
    assert report['passed'], report
    names = {case['name'] for case in report['cases']}
    assert {'success', 'premature_green', 'scope_escape', 'weaken_tests', 'ambiguous_task', 'refactor_regression'} <= names
