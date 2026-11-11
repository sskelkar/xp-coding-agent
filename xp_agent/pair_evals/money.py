"""Independent, requirement-aligned Money acceptance executed only in Docker.

The public adapter contract is intentionally explicit; evaluator code must not
be given to the coding partners as an implementation recipe. Trusted toy code
only: candidate Python and pytest share a process inside the restricted runner.
"""
import hashlib
import json
import os
from pathlib import Path
from ..sandbox import DockerRunner
from ..policy import safe_path, check_content

STAGES = ('multiplication', 'reusable', 'exchange')
RESERVED = 'test_pair_acceptance.py'
MULTIPLICATION = '''import pytest
import money_api as api

@pytest.mark.parametrize("amount", [0, 1, 5, 19, 1001])
@pytest.mark.parametrize("factor", [1, 2, 3, 7, 11])
def test_multiplication(amount, factor):
    original = api.make(amount, "USD")
    result = api.multiply(original, factor)
    assert type(api.amount_of(result)) is int
    assert api.amount_of(result) == amount * factor
    assert api.currency_of(result) == "USD"
'''
REUSABLE = '''
@pytest.mark.parametrize("amount", [1, 5, 19])
def test_original_is_reusable(amount):
    original = api.make(amount, "USD")
    twice = api.multiply(original, 2)
    thrice = api.multiply(original, 3)
    assert api.amount_of(original) == amount
    assert api.amount_of(twice) == amount * 2
    assert api.amount_of(thrice) == amount * 3
    assert api.currency_of(original) == "USD"
'''
EXCHANGE = '''
@pytest.mark.parametrize("usd,chf,rate", [(5,10,2),(7,12,3),(0,20,4)])
def test_exchange(usd, chf, rate):
    left, right = api.make(usd, "USD"), api.make(chf, "CHF")
    result = api.add_money(left, right, {"CHF/USD": rate})
    assert api.amount_of(result) == usd + chf // rate
    assert api.currency_of(result) == "USD"
    assert api.amount_of(left) == usd
    assert api.amount_of(right) == chf

def test_same_currency_addition():
    result = api.add_money(api.make(5,"USD"), api.make(7,"USD"), {})
    assert api.amount_of(result) == 12
    assert api.currency_of(result) == "USD"

def test_missing_exchange_rate_is_explicit():
    with pytest.raises(ValueError):
        api.add_money(api.make(5,"USD"), api.make(10,"CHF"), {})
'''


def load_candidate(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Candidate root must not be a symlink')
    if not root.is_dir():
        raise ValueError('Candidate must be a directory')
    files, total = {}, 0
    for base, directories, names in os.walk(root, followlinks=False):
        directories[:] = [d for d in directories if not d.startswith('.') and d != '__pycache__']
        for name in directories + names:
            if (Path(base) / name).is_symlink():
                raise ValueError('Candidate contains a symlink')
        for name in sorted(names):
            if not name.endswith('.py'):
                continue
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            if name == RESERVED or name == 'conftest.py':
                raise ValueError('Candidate uses a reserved evaluator/pytest configuration path')
            safe_path(relative)
            total += path.stat().st_size
            if total > 400_000:
                raise ValueError('Candidate exceeds 400 KB')
            content = path.read_text()
            check_content(content)
            files[relative] = content
    if 'money_api.py' not in files:
        raise ValueError('Candidate requires money_api.py; see the public adapter contract')
    return files


def evaluate_money(root, *, stage='multiplication', runner=None):
    if stage not in STAGES:
        raise ValueError('Unknown Money stage')
    files = load_candidate(root)
    candidate_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    oracle = MULTIPLICATION
    if stage in ('reusable', 'exchange'):
        oracle += REUSABLE
    if stage == 'exchange':
        oracle += EXCHANGE
    report = (runner or DockerRunner()).test({**files, RESERVED: oracle}, 60)
    expected_count = {'multiplication': 25, 'reusable': 28, 'exchange': 33}[stage]
    # Count only independent evaluator tests, never candidate-owned tests.
    ids = {key: [t for t in report[key] if t.startswith(RESERVED + '::')]
           for key in ('passed', 'failed', 'errors', 'skipped')}
    passed = (report['returncode'] == 0 and len(set(ids['passed'])) == expected_count
              and not any(report[k] for k in ('failed', 'errors', 'skipped')))
    return {'version': 1, 'stage': stage, 'passed': passed,
            'status': 'passed' if passed else 'failed',
            'candidate_hash': candidate_hash, 'runtime_verified': False,
            'evidence_kind': 'independent_docker_acceptance',
            'expected_tests': expected_count,
            'tests': {k: len(v) for k, v in ids.items()},
            'runner_returncode': report['returncode']}
