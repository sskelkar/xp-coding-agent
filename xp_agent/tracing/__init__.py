"""Bounded opt-in metadata tracing; no SDK/network/credential access while recording."""
import contextvars
from contextlib import contextmanager
import json
import re
import time
import uuid
from pathlib import Path

from .metadata import BASE_URL as BASE_URL
from .metadata import NAMES, attributes, valid_score

MAX_RECORDS = 2000
MAX_BYTES = 1_000_000
_current = contextvars.ContextVar('xp_trace', default=None)
_parent = contextvars.ContextVar('xp_observation', default=None)


class Observation:

    def __init__(self, row=None):
        self.row = row

    def update(self, **values):
        if self.row is not None:
            self.row['attributes'].update(attributes(values))


class Recorder:

    def __init__(self, session_id=None):
        self.trace_id = uuid.uuid4().hex
        self.session_id = session_id or uuid.uuid4().hex
        if not re.fullmatch('[0-9a-f]{32}', self.session_id):
            raise ValueError('Invalid trace session identity')
        self.records = []
        self.dropped = 0
        self.scores = {}

    def snapshot(self):
        value = {
            'version': 1,
            'trace_id': self.trace_id,
            'session_id': self.session_id,
            'records': self.records,
            'dropped': self.dropped,
            'scores': self.scores
        }
        while len(json.dumps(value).encode()) > MAX_BYTES and value['records']:
            value['records'] = value['records'][:-1]
            value['dropped'] += 1
        if value['dropped']:
            value['scores'] = {
                **value['scores'], 'evidence_complete': False,
                'tdd_sequence': 'insufficient_evidence'
            }
        return value


def current():
    return _current.get()


def annotate(**values):
    recorder = current()
    if recorder:
        for row in reversed(recorder.records):
            if row['id'] == _parent.get():
                Observation(row).update(**values)
                break


@contextmanager
def observation(name, kind='span', **values):
    recorder = current()
    if not recorder:
        yield Observation()
        return
    if name not in NAMES or kind not in {'span', 'agent', 'generation', 'tool'}:
        raise ValueError('Unknown trace operation')
    if len(recorder.records) >= MAX_RECORDS or _parent.get() == 'dropped':
        recorder.dropped += 1
        token = _parent.set('dropped')
        try:
            yield Observation()
        finally:
            _parent.reset(token)
        return
    row = {
        'id': uuid.uuid4().hex[:16],
        'parent': _parent.get(),
        'name': name,
        'kind': kind,
        'start_ns': time.time_ns(),
        'end_ns': None,
        'attributes': attributes(values)
    }
    recorder.records.append(row)
    token = _parent.set(row['id'])
    try:
        yield Observation(row)
        row['attributes'].setdefault('outcome', 'ok')
    except BaseException as exc:
        row['attributes']['outcome'] = 'cancelled' if isinstance(exc,
                                                                 KeyboardInterrupt) else 'error'
        raise
    finally:
        row['end_ns'] = max(row['start_ns'], time.time_ns())
        _parent.reset(token)


def export_trace(value):
    from .exporter import export
    return export(value)


def set_scores(scores):
    recorder = current()
    if recorder:
        recorder.scores.update({
            key: value
            for key, value in scores.items() if valid_score(key, value)
        })


@contextmanager
def operation(name,
              *,
              enabled=False,
              directory=None,
              session_id=None,
              write=print,
              export=True,
              **values):
    if not enabled:
        yield None
        return
    # A broken output consumer must not change the coding outcome.
    notify = write

    def write(message):
        try:
            notify(message)
        except Exception:
            pass

    recorder = Recorder(session_id)
    token, parent = _current.set(recorder), _parent.set(None)
    try:
        with observation(name, 'agent', **values):
            yield recorder
    finally:
        _parent.reset(parent)
        _current.reset(token)
        try:
            from ..workspace import write_json
            root = Path(directory or Path.home() / '.local/state/xp-coding-agent/traces')
            payload = recorder.snapshot()
            path = root / ('trace-' + recorder.trace_id + '.json')
            write_json(path, payload)
            if export:
                result = export_trace(payload)
                if not isinstance(result, dict) or not result.get('exported'):
                    raise RuntimeError('Trace not exported')
                write('Trace: ' + result['url'] + ' (id: ' + recorder.trace_id + ')')
                write_json(path.with_suffix('.export.json'), result)
            else:
                write('Trace recorded locally; export disabled.')
        except Exception:
            write(
                'Warning: trace not exported; inspect local recording and local Langfuse setup. Coding outcome is unchanged.'
            )


def report_usage(usage):
    """Only CLI-reported integer counts; unknown is never estimated as zero."""
    if not isinstance(usage, dict):
        return
    values = {}
    for source, target in {
            'input_tokens': 'input_tokens',
            'output_tokens': 'output_tokens',
            'cached_input_tokens': 'cache_read_tokens',
            'cache_read_input_tokens': 'cache_read_tokens',
            'cache_creation_input_tokens': 'cache_creation_tokens'
    }.items():
        value = usage.get(source)
        if type(value) is int and 0 <= value <= 10**12:
            values[target] = value
    annotate(**values, usage_known='input_tokens' in values and 'output_tokens' in values)
