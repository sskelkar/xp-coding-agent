import os
import pytest
from xp_agent.pair_evals.money import evaluate_money, load_candidate

GOOD = '''def make(value, currency="USD"):
    return {"amount": value, "currency": currency}
def amount_of(money): return money["amount"]
def currency_of(money): return money["currency"]
def multiply(money, factor): return make(amount_of(money) * factor, currency_of(money))
def add_money(left, right, rates):
    value = amount_of(right)
    if currency_of(left) != currency_of(right):
        key = currency_of(right) + "/" + currency_of(left)
        if key not in rates: raise ValueError("Missing rate")
        value = value // rates[key]
    return make(amount_of(left) + value, currency_of(left))
'''


def test_candidate_loader_refuses_symlinks_and_reserved_acceptance_file(tmp_path):
    (tmp_path/'money_api.py').symlink_to('/etc/passwd')
    with pytest.raises(ValueError, match='symlink'): load_candidate(tmp_path)
    (tmp_path/'money_api.py').unlink()
    (tmp_path/'test_pair_acceptance.py').write_text('pass')
    with pytest.raises(ValueError, match='reserved'): load_candidate(tmp_path)


def test_candidate_loader_requires_api_and_bounds_input(tmp_path):
    with pytest.raises(ValueError, match='money_api'): load_candidate(tmp_path)
    (tmp_path/'money_api.py').write_text('x' * 400_001)
    with pytest.raises(ValueError, match='400'): load_candidate(tmp_path)


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Real Docker acceptance checks')
@pytest.mark.parametrize('stage', ['multiplication', 'reusable', 'exchange'])
def test_correct_money_api_passes_independent_docker_acceptance(tmp_path, stage):
    (tmp_path/'money_api.py').write_text(GOOD)
    before = (tmp_path/'money_api.py').read_bytes()
    report = evaluate_money(tmp_path, stage=stage)
    assert report['passed'], report
    assert report['tests']['passed'] >= 25
    assert not report['runtime_verified']
    assert (tmp_path/'money_api.py').read_bytes() == before


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS') != '1', reason='Real Docker acceptance checks')
@pytest.mark.parametrize('source,stage', [
    (GOOD.replace('amount_of(money) * factor', '10'), 'multiplication'),
    (GOOD.replace('return make(amount_of(money) * factor, currency_of(money))',
                  'money["amount"] *= factor; return money'), 'reusable'),
    (GOOD.replace('value = value // rates', 'value = value * rates'), 'exchange'),
    ('# no public API', 'multiplication'),
])
def test_wrong_implementations_fail_without_host_execution(tmp_path, source, stage):
    (tmp_path/'money_api.py').write_text(source)
    report = evaluate_money(tmp_path, stage=stage)
    assert not report['passed']
    assert report['tests']['failed'] + report['tests']['errors'] > 0
