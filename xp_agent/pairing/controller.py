"""Controller operations for the production graph: private state, code and tests."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import time
from ..policy import PolicyError, safe_path, check_content, validate_edits, digest
from ..workspace import reconcile_workspace
from .. import tracing
from .demos import DEMO_TEST_FILE, demo_observations, render_demo_tests
from .partners import parse_reply

RESERVED = {
    'pytest.py', 'conftest.py', 'sitecustomize.py', 'usercustomize.py', DEMO_TEST_FILE,
    'test_pair_acceptance.py'
}


def is_test(path):
    return Path(path).name.startswith('test_') or Path(path).name.endswith('_test.py')


def tests_pass(report, required=()):
    return (report['returncode'] == 0 and bool(report['passed'])
            and not any(report[k] for k in ('failed', 'errors', 'skipped'))
            and set(required) <= set(report['passed']))


class PairController:
    confirmed = False
    refactoring = True

    def __init__(self,
                 partners,
                 runner,
                 workspace,
                 goal,
                 files,
                 *,
                 budget=900,
                 attempts=2,
                 max_cycles=12,
                 demo_every=2):
        if set(partners) != {'A', 'B'} or partners['A'] is partners['B']:
            raise ValueError('Two distinct partners required')
        for actor, partner in partners.items():
            if partner.identity != actor:
                raise ValueError('Partner identity mismatch')
        self.partners, self.runner, self.workspace = partners, runner, Path(workspace)
        self.goal, self.files, self.budget = goal, files, budget
        self.attempts, self.max_cycles, self.demo_every = attempts, max_cycles, demo_every
        if min(budget, attempts, max_cycles, demo_every) <= 0:
            raise ValueError('Positive resource limits required')

    def initialize(self, state):
        return dict(phase='red',
                    cycle=1,
                    files=self.files,
                    pending={},
                    status='running',
                    reason='',
                    required=[],
                    baseline=[],
                    histories={
                        'A': [],
                        'B': []
                    },
                    records=[],
                    snapshots={},
                    agreement=1,
                    goal=self.goal,
                    feedback='',
                    attempts=0,
                    remaining=self.budget,
                    active=0.,
                    last_feedback_active=0.,
                    since_feedback=0,
                    bootstrap_done=False,
                    config={'max_cycles': self.max_cycles})

    def _message(self, updated, actor, phase, text, reference=None):
        message = {
            'id': f"message-{len(updated['histories']['A'])}",
            'actor': actor,
            'phase': phase,
            'message': text,
            'reference': reference
        }
        for identity in ('A', 'B'):
            updated['histories'][identity].append(deepcopy(message))

    def _record(self, updated, kind, **fields):
        event = {
            'kind': kind,
            'id': f"event-{len(updated['records'])}",
            'active_seconds': updated['active'],
            **fields
        }
        updated['records'].append(event)
        return event

    def _call(self, actor, phase, state):
        updated = deepcopy(state)
        if updated['remaining'] <= 0 or (updated['cycle'] > self.max_cycles and phase != 'demo'):
            return {
                **updated, 'status': 'blocked',
                'reason': 'Pair execution budget exhausted'
            }, None
        start = time.monotonic()
        try:
            backend = getattr(self.partners[actor], 'backend', None)
            with tracing.observation('model.propose',
                                     'generation',
                                     actor=actor,
                                     phase=phase,
                                     mode='pair',
                                     model=getattr(backend, 'model', 'scripted-fixture'),
                                     provider=getattr(backend, 'provider', None),
                                     auth=getattr(backend, 'auth', None),
                                     usage_known=False):
                reply = parse_reply(self.partners[actor].reply(phase, updated))
            if reply['action'] != 'edit' and reply['edits']:
                raise PolicyError('Only edit actions may contain edits')
            self._message(updated, actor, phase, reply['message'])
            return updated, reply
        except (ValueError, RuntimeError, OSError) as exc:
            updated.update(status='blocked', reason=str(exc))
            return updated, None
        finally:
            elapsed = time.monotonic() - start
            updated['remaining'] -= elapsed
            updated['active'] += elapsed

    def _run(self, updated, files, phase):
        start = time.monotonic()
        if updated['remaining'] <= 0:
            raise PolicyError('Execution time exhausted')
        with tracing.observation('run-tests', 'tool', phase=phase, mode='pair'):
            report = self.runner.test(files, min(updated['remaining'], 60))
        elapsed = time.monotonic() - start
        updated['remaining'] -= elapsed
        updated['active'] += elapsed
        return report

    def confirm(self, state):
        updated = deepcopy(state)
        event = self._record(updated, 'agreement', actor='user', revision=1)
        self._message(updated, 'user', 'agreement', 'Confirmed outcome: ' + updated['goal'],
                      event['id'])
        return updated

    def baseline(self, state):
        updated = deepcopy(state)
        if not any(is_test(p) for p in updated['files']):
            return updated  # Explicitly no baseline, not a passing zero-test claim.
        try:
            report = self._run(updated, updated['files'], 'baseline')
            if not tests_pass(report):
                raise PolicyError('Existing baseline must pass before pairing')
            updated['required'] = report['passed']
            updated['baseline'] = report['passed']
        except (ValueError, RuntimeError, OSError) as exc:
            updated.update(status='blocked', reason=str(exc))
        return updated

    def discuss(self, actor, state):
        updated, reply = self._call(actor, 'discuss', state)
        if reply:
            if reply['edits']:
                return {**updated, 'status': 'blocked', 'reason': 'Discussion cannot edit files'}
            if reply['action'] in {'question', 'demo'}:
                updated.update(status=reply['action'], pending={'actor': actor, 'reply': reply})
        return updated

    def propose(self, actor, phase, state):
        updated, reply = self._call(actor, phase, state)
        updated['attempts'] = state['attempts'] + 1
        if not reply:
            return updated
        if reply['action'] in {'question', 'demo'}:
            return {
                **updated, 'status': reply['action'],
                'pending': {
                    'actor': actor,
                    'reply': reply
                }
            }
        if phase != 'refactor' and reply['action'] != 'edit':
            return self.reject(
                updated, 'Submit action="edit" for this coding phase, or use action="question" '
                'to ask the user for a business decision. Comments do not pause the session.')
        try:
            edits = {e['path']: e['content'] for e in reply['edits']}
            if any(Path(p).name in RESERVED for p in edits):
                raise PolicyError('Reserved test infrastructure cannot be edited')
            if any(not p.endswith('.py') for p in edits):
                raise PolicyError('Only project Python paths may be edited')
            tests = [p for p in updated['files'].keys() | edits.keys() if is_test(p)]
            sources = [p for p in updated['files'].keys() | edits.keys() if not is_test(p)]
            candidate = validate_edits(phase, updated['files'], edits, sources, tests)
            if sum(len(v.encode()) for v in candidate.values()) > 400_000:
                raise PolicyError('Snapshot exceeds 400 KB')
            updated.update(status='running',
                           pending={
                               'actor': actor,
                               'reply': reply,
                               'files': candidate,
                               'before': digest(updated['files']),
                               'started_active': state['active'],
                               'history': deepcopy(updated['histories'][actor][:-1])
                           })
        except (ValueError, RuntimeError) as exc:
            return self.reject(updated, str(exc))
        return updated

    def test(self, state):
        updated = deepcopy(state)
        try:
            updated['report'] = self._run(updated, updated['pending']['files'], updated['phase'])
            report = updated['report']
            if (updated['phase'] == 'red' and report['errors'] and not updated['bootstrap_done']
                    and any(name in report.get('output', '')
                            for name in ('ModuleNotFoundError', 'ImportError', 'AttributeError',
                                         'NameError'))):
                updated['status'] = 'scaffold_needed'
        except (ValueError, RuntimeError, OSError) as exc:
            updated.update(status='blocked', reason=str(exc))
        return updated

    def bootstrap(self, state):
        actor = 'B' if state['cycle'] % 2 else 'A'
        pending = deepcopy(state['pending'])
        attempts = pending.get('bootstrap_attempts', 0) + 1
        feedback = state['feedback'] if attempts > 1 else state['report'].get('output', '')[-4000:]
        context = {**state, 'files': pending['files'], 'feedback': feedback}
        updated, reply = self._call(actor, 'bootstrap', context)
        # Accepted files are still the old snapshot; pending tests are not lost.
        updated['files'] = deepcopy(state['files'])
        updated['pending'] = pending
        if not reply:
            return updated
        try:
            edits = {e['path']: e['content'] for e in reply['edits']}
            if reply['action'] != 'edit' or not edits:
                raise PolicyError('Scaffolding requires source edits')
            for path, content in edits.items():
                safe_path(path)
                if Path(path).name in RESERVED:
                    raise PolicyError('Reserved test infrastructure cannot be scaffolded')
                if is_test(path) or not path.endswith('.py'):
                    raise PolicyError('Scaffolding cannot change tests')
                old = ast.parse(updated['files'].get(path, '')).body
                new = ast.parse(content).body
                if [ast.dump(n) for n in new[:len(old)]] != [ast.dump(n) for n in old]:
                    raise PolicyError('Scaffolding must preserve existing source')
            candidate = {**pending['files'], **edits}
            if sum(len(v.encode()) for v in candidate.values()) > 400_000:
                raise PolicyError('Snapshot exceeds 400 KB')
            report = self._run(updated, candidate, 'red')
            if report['returncode'] != 1 or not report['failed'] or report['errors'] or report[
                    'skipped'] or not set(updated['required']) <= set(report['passed']):
                reason = (
                    'Scaffolding must leave a meaningful assertion failure '
                    f"({len(report['passed'])} passed, {len(report['failed'])} assertion failures, "
                    f"{len(report['errors'])} errors, {len(report['skipped'])} skipped)")
                pending['bootstrap_attempts'] = attempts
                self._message(updated, 'controller', 'bootstrap', 'Rejected scaffold: ' + reason)
                updated.update(status='scaffold_needed' if attempts < self.attempts
                               and updated['remaining'] > 0 else 'blocked',
                               reason=reason,
                               report=report,
                               feedback=reason + '\n' + report.get('output', '')[-4000:])
                return updated
            source_only = {**updated['files'], **edits}
            reconcile_workspace(self.workspace, updated['files'], source_only)
            before_id, after_id, checked = digest(
                updated['files']), digest(source_only), digest(candidate)
            updated['snapshots'].update({
                before_id: deepcopy(updated['files']),
                after_id: deepcopy(source_only),
                checked: deepcopy(candidate)
            })
            history = deepcopy(updated['histories'][actor][:-1])
            event = self._record(
                updated,
                'bootstrap',
                actor=actor,
                cycle=updated['cycle'],
                phase='bootstrap',
                before=before_id,
                after=after_id,
                checked=checked,
                agreement=updated['agreement'],
                context='partner-' + actor,
                history=[m['reference'] for m in history if m.get('reference')],
                report={
                    **{
                        k: report[k]
                        for k in ('returncode', 'passed', 'failed', 'errors', 'skipped')
                    }, 'revision': checked,
                    'required': updated['required']
                })
            self._message(updated, 'controller', 'bootstrap',
                          'Scaffolding validated; behavioral test still fails.', event['id'])
            updated['files'] = source_only
            updated['pending']['files'] = candidate
            updated['pending']['before'] = digest(source_only)
            updated['bootstrap_done'] = True
            updated['status'] = 'running'
            updated['reason'] = ''
        except (ValueError, RuntimeError, OSError, SyntaxError) as exc:
            updated.update(status='blocked', reason=str(exc))
        return updated

    def accept(self, state):
        updated = deepcopy(state)
        proposal = updated['pending']
        after = proposal['files']
        try:
            reconcile_workspace(self.workspace, updated['files'], after)
        except (ValueError, OSError) as exc:
            return {**updated, 'status': 'blocked', 'reason': str(exc)}
        before_id, after_id = digest(updated['files']), digest(after)
        updated['snapshots'][before_id] = deepcopy(updated['files'])
        updated['snapshots'][after_id] = deepcopy(after)
        event = self._record(
            updated,
            'step',
            actor=proposal['actor'],
            cycle=updated['cycle'],
            phase=updated['phase'],
            before=before_id,
            after=after_id,
            agreement=updated['agreement'],
            context='partner-' + proposal['actor'],
            history=[m['reference'] for m in proposal['history'] if m.get('reference')],
            dispatch_active=proposal['started_active'],
            report={
                **{
                    k: v
                    for k, v in updated['report'].items() if k != 'output'
                }, 'revision': after_id,
                'required': updated['required']
            })
        self._message(
            updated, 'controller', updated['phase'],
            f"Accepted {proposal['actor']} {updated['phase']}; tests: " + json.dumps(
                {k: len(updated['report'][k])
                 for k in ('passed', 'failed', 'errors', 'skipped')}), event['id'])
        updated.update(
            files=after,
            status='running',
            feedback='',
            bootstrap_done=False if updated['phase'] == 'refactor' else updated['bootstrap_done'])
        return updated

    def reject(self, state, reason):
        updated = deepcopy(state)
        updated['feedback'] = reason + '\n' + updated.get('report', {}).get('output', '')[-4000:]
        self._message(updated, 'controller', updated['phase'], 'Rejected candidate: ' + reason)
        updated['status'] = 'blocked' if updated['attempts'] >= self.attempts or updated[
            'remaining'] <= 0 else 'retry'
        updated['reason'] = reason
        return updated

    def checkin_due(self, state):
        return state['active'] - state['last_feedback_active'] >= 300

    def demo_due(self, state):
        return state['since_feedback'] >= self.demo_every or state['active'] - state[
            'last_feedback_active'] >= 300 or state['cycle'] > self.max_cycles

    def prepare_demo(self, state):
        updated = deepcopy(state)
        if updated['status'] == 'question':
            event = self._record(updated, 'question', actor=updated['pending']['actor'])
            self._message(updated, 'controller', 'question', updated['pending']['reply']['message'],
                          event['id'])
            return {
                **updated, 'demo': {
                    'kind': 'business_question',
                    'message': updated['pending']['reply']['message'],
                    'working_increment': False,
                    'revision': digest(updated['files']),
                    'event_id': event['id']
                }
            }
        if self.checkin_due(updated) and updated['phase'] != 'red':
            event = self._record(updated, 'question', actor='controller')
            self._message(updated, 'controller', 'question', 'Active-time progress check-in',
                          event['id'])
            return {
                **updated, 'status': 'question',
                'demo': {
                    'kind': 'progress_update',
                    'working_increment': False,
                    'message':
                    'Active-time check-in: an incomplete TDD cycle remains. Continue or clarify the outcome.',
                    'revision': digest(updated['files']),
                    'event_id': event['id']
                }
            }
        if updated['phase'] != 'red' or not updated['required']:
            return {
                **updated, 'status': 'blocked',
                'demo': {
                    'kind': 'blocked',
                    'message': 'No completed green increment to demonstrate'
                }
            }
        updated, reply = self._call('A', 'demo', updated)
        if not reply or reply['edits'] or not reply['examples']:
            return {
                **updated, 'status': 'blocked',
                'demo': {
                    'kind': 'blocked',
                    'message': 'Executable demonstration required'
                }
            }
        try:
            examples = reply['examples']
            demo_tests = render_demo_tests(examples, updated['files'])
            report = self._run(updated, {**updated['files'], DEMO_TEST_FILE: demo_tests}, 'final')
            if not tests_pass(report, updated['required']):
                raise PolicyError('Demonstration failed its executable checks')
            actual = demo_observations(report['output'], len(examples))
            event = self._record(updated,
                                 'demo',
                                 actor='controller',
                                 revision=digest(updated['files']),
                                 samples=[
                                     dict(input=x['label'],
                                          actual=x['actual'],
                                          expected=x['expected']) for x in actual
                                 ])
            self._message(updated, 'controller', 'demo', reply['message'], event['id'])
            updated.update(status='waiting',
                           demo={
                               'kind': 'working_demo',
                               'message': reply['message'],
                               'revision': digest(updated['files']),
                               'event_id': event['id'],
                               'examples': actual,
                               'cycle': updated['cycle'] - 1,
                               'prompt': 'accept, continue, or clarify the outcome'
                           })
        except (ValueError, RuntimeError, OSError, SyntaxError) as exc:
            updated.update(status='blocked',
                           reason=str(exc),
                           demo={
                               'kind': 'blocked',
                               'message': str(exc)
                           })
        return updated

    def feedback(self, state, answer):
        updated = deepcopy(state)
        if updated['status'] == 'blocked':
            return updated
        if answer == 'accept' and updated['demo']['kind'] == 'working_demo':
            updated['status'] = 'accepted'
        elif answer == 'continue':
            updated['status'] = 'running'
        elif isinstance(answer, str) and answer.strip() and answer != 'accept':
            updated['agreement'] += 1
            updated['goal'] += '\nBusiness clarification: ' + answer
            updated['status'] = 'running'
        else:
            return {**updated, 'status': 'blocked', 'reason': 'Invalid business decision'}
        event = self._record(updated,
                             'feedback',
                             actor='user',
                             revision=updated['agreement'],
                             demo=updated['demo']['event_id'],
                             decision=str(answer) if answer in ('accept', 'continue') else 'revise')
        self._message(updated, 'user', 'feedback', str(answer), event['id'])
        updated.update(feedback=str(answer),
                       since_feedback=0,
                       last_feedback_active=updated['active'])
        return updated
