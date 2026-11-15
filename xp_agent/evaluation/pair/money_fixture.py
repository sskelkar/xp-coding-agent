"""Deterministic partners for the Money evaluation scenario."""

from copy import deepcopy

SCAFFOLD = '''def make(value, currency="USD"):
    return {"amount":value,"currency":currency}
def amount_of(money): return money["amount"]
def currency_of(money): return money["currency"]
def multiply(money, factor): return make(0,currency_of(money))
'''
MUTABLE = SCAFFOLD.replace('return make(0,currency_of(money))',
                           'money["amount"] *= factor; return money')
IMMUTABLE = SCAFFOLD.replace('return make(0,currency_of(money))',
                             'return make(amount_of(money)*factor,currency_of(money))')
ADD_STUB = '\ndef add_money(left,right,rates): return make(0,currency_of(left))\n'
ADD = '''
def add_money(left,right,rates):
    value=amount_of(right)
    if currency_of(left)!=currency_of(right):
        key=currency_of(right)+"/"+currency_of(left)
        if key not in rates: raise ValueError("Missing rate")
        value=value//rates[key]
    return make(amount_of(left)+value,currency_of(left))
'''
TESTS = [
    '''def test_multiplication():
    import money_api as api
    assert api.amount_of(api.multiply(api.make(5,"USD"),2))==10
''', '''def test_reusable_original():
    import money_api as api
    original=api.make(5,"USD")
    twice=api.multiply(original,2)
    thrice=api.multiply(original,3)
    assert api.amount_of(original)==5
    assert api.amount_of(twice)==10
    assert api.amount_of(thrice)==15
''', '''def test_addition():
    import money_api as api
    assert api.amount_of(api.add_money(api.make(5,"USD"),api.make(10,"CHF"),{"CHF/USD":2}))==10
'''
]
GOAL = '''Implement a tiny Money API: make(value,currency), amount_of(money), currency_of(money), multiply(money,factor), and add_money(left,right,rates).
Amounts are nonnegative integers and multipliers positive integers. Multiplication preserves currency and leaves the original reusable. Addition returns the left currency and leaves both originals unchanged. A CHF/USD rate of 2 means two CHF per USD. Evaluate exact integer conversions only; missing rates raise ValueError. Start with multiplication, discover the design through small TDD cycles. No new dependencies.'''


def response(action='comment', message='Consider one next behavior.', edits=None, examples=None):
    return dict(action=action,
                message=message,
                edits=[{
                    'path': p,
                    'content': c
                } for p, c in (edits or {}).items()],
                examples=examples or [])


class ScriptedPartner:
    """Test double supplying code; not evidence of model coding quality."""

    def __init__(self, identity):
        self.identity = identity
        self.calls = []

    def reply(self, phase, state):
        self.calls.append((phase, deepcopy(state['histories'][self.identity])))
        cycle = state['cycle']
        if phase == 'discuss':
            return response(action='demo' if cycle > 3 else 'comment')
        if phase == 'bootstrap':
            return response(
                'edit', edits={'money_api.py': SCAFFOLD if cycle == 1 else IMMUTABLE + ADD_STUB})
        if phase == 'red':
            return response('edit',
                            edits={
                                'test_money.py':
                                state['files'].get('test_money.py', '') + '\n' + TESTS[cycle - 1]
                            })
        if phase == 'green':
            return response('edit',
                            edits={
                                'money_api.py':
                                MUTABLE if cycle == 1 else IMMUTABLE if cycle == 2 else IMMUTABLE +
                                ADD
                            })
        if phase == 'refactor':
            return response(message='The small functions are clear; no cleanup needed.')
        if phase == 'demo':
            return response('demo',
                            message='Five dollars times two produces ten.',
                            examples=[{
                                'label': 'Five dollars doubled',
                                'module': 'money_api',
                                'expression': 'api.amount_of(api.multiply(api.make(5,"USD"),2))',
                                'expected': 10
                            }])
        raise ValueError('Unexpected scripted phase')
