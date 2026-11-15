"""Build executable demo tests and read their observed values."""

import ast
import json
import re

from ..policy import PolicyError

DEMO_TEST_FILE = 'test_pair_demo.py'
OBSERVATION_MARKER = 'XP_PAIR_DEMO='
MODULE_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*')


def render_demo_tests(examples, files):
    tests = []
    for index, example in enumerate(examples):
        module = example['module']
        if not MODULE_NAME.fullmatch(module):
            raise PolicyError('Invalid demo module')
        if module.replace('.', '/') + '.py' not in files:
            raise PolicyError('Demo module absent from project')
        expression = ast.unparse(ast.parse(example['expression'], mode='eval').body)
        tests.append(f"""def test_demo_{index}():
    import {module} as api
    import json, sys
    actual = {expression}
    assert actual == {example['expected']!r}
    record = dict(label={example['label']!r},actual=actual,expected={example['expected']!r})
    sys.__stdout__.write({OBSERVATION_MARKER!r} + json.dumps(record) + '\\n')
""")
    return '\n'.join(tests)


def demo_observations(output, expected_count):
    observations = [
        json.loads(line) for line in re.findall(OBSERVATION_MARKER + r'([^\n]+)', output)
    ]
    if len(observations) != expected_count:
        raise PolicyError('Demo did not return expected observations')
    return observations
