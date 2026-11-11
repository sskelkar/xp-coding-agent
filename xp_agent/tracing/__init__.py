"""Bounded opt-in metadata tracing; no SDK/network/credential access while recording."""
import contextvars
from contextlib import contextmanager
import functools
import json
import math
import re
import time
import uuid
from pathlib import Path

BASE_URL = 'http://127.0.0.1:4000'
MAX_RECORDS = 2000
MAX_BYTES = 1_000_000
_current = contextvars.ContextVar('xp_trace', default=None)
_parent = contextvars.ContextVar('xp_observation', default=None)
NAMES = {'xp.plan','xp.execute','xp.batch','xp.evaluation','discover-project','plan-change',
         'prepare-workspace','execute-session','execute-increment','baseline','coding-phase','final',
         'model.select','model.propose','run-tests','controller-gate','write-report'}
ENUMS = {'phase':{'plan','discovery','baseline','red','green','refactor','final','discuss','bootstrap','demo'},
         'provider':{'codex','claude'},'auth':{'cli','api-key','oauth-token'},
         'status':{'running','ready','verified','blocked','cancelled','rejected'},
         'outcome':{'ok','error','cancelled'}, 'actor':{'solo','A','B'},
         'tdd_sequence':{'complete','valid_partial','violation','insufficient_evidence'},
         'visibility':{'cli-aggregate'},'mode':{'single','pair'}}
NUMBERS = {'sequence','attempt','increment','files','edits','passed','failed','errors','skipped','returncode',
           'remaining_seconds','input_tokens','output_tokens','cache_read_tokens','cache_creation_tokens',
           'rejected_proposals'}
BOOLS = {'accepted','usage_known','scope_valid','evidence_complete'}
HASHES = {'source_hash','test_hash','code_hash','before_hash','previous_trace_id'}


def attributes(values):
    out = {}
    for key,value in values.items():
        if key in ENUMS and isinstance(value,str) and value in ENUMS[key]: out[key]=value
        elif key in NUMBERS and type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**12: out[key]=value
        elif key in BOOLS and type(value) is bool: out[key]=value
        elif key in HASHES and isinstance(value,str) and re.fullmatch('[0-9a-f]{32}|[0-9a-f]{64}',value): out[key]=value
        elif key=='model' and isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.-]{1,100}',value): out[key]=value
    return out


class Observation:
    def __init__(self,row=None): self.row=row
    def update(self,**values):
        if self.row is not None: self.row['attributes'].update(attributes(values))


class Recorder:
    def __init__(self,session_id=None):
        self.trace_id=uuid.uuid4().hex
        self.session_id=session_id or uuid.uuid4().hex
        if not re.fullmatch('[0-9a-f]{32}',self.session_id): raise ValueError('Invalid trace session identity')
        self.records=[]
        self.dropped=0
        self.scores={}
    def snapshot(self):
        value={'version':1,'trace_id':self.trace_id,'session_id':self.session_id,
               'records':self.records,'dropped':self.dropped,'scores':self.scores}
        while len(json.dumps(value).encode())>MAX_BYTES and value['records']:
            value['records']=value['records'][:-1]
            value['dropped']+=1
        if value['dropped']:
            value['scores']={**value['scores'],'evidence_complete':False,'tdd_sequence':'insufficient_evidence'}
        return value


def current(): return _current.get()


def annotate(**values):
    recorder=current()
    if recorder:
        for row in reversed(recorder.records):
            if row['id']==_parent.get():
                Observation(row).update(**values); break


@contextmanager
def observation(name,kind='span',**values):
    recorder=current()
    if not recorder:
        yield Observation(); return
    if name not in NAMES or kind not in {'span','agent','generation','tool'}:
        raise ValueError('Unknown trace operation')
    if len(recorder.records)>=MAX_RECORDS or _parent.get()=='dropped':
        recorder.dropped+=1
        token=_parent.set('dropped')
        try: yield Observation()
        finally: _parent.reset(token)
        return
    row={'id':uuid.uuid4().hex[:16],'parent':_parent.get(),'name':name,'kind':kind,
         'start_ns':time.time_ns(),'end_ns':None,'attributes':attributes(values)}
    recorder.records.append(row)
    token=_parent.set(row['id'])
    try:
        yield Observation(row)
        row['attributes'].setdefault('outcome','ok')
    except BaseException as exc:
        row['attributes']['outcome']='cancelled' if isinstance(exc,KeyboardInterrupt) else 'error'
        raise
    finally:
        row['end_ns']=max(row['start_ns'],time.time_ns())
        _parent.reset(token)


def traced(name,kind='span'):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args,**kwargs):
            with observation(name,kind): return fn(*args,**kwargs)
        return wrapped
    return decorate


def export_trace(value):
    from .exporter import export
    return export(value)


def set_scores(scores):
    recorder=current()
    if recorder:
        from .evaluation import SCORE_NAMES
        recorder.scores.update({k:v for k,v in scores.items() if k in SCORE_NAMES and
                               (v is None or type(v) is bool or isinstance(v,str) and v in ENUMS['tdd_sequence']|{'not_applicable'})})


@contextmanager
def operation(name,*,enabled=False,directory=None,session_id=None,write=print,export=True,**values):
    if not enabled:
        yield None; return
    # A broken output consumer must not change the coding outcome.
    notify=write
    def write(message):
        try: notify(message)
        except Exception: pass
    recorder=Recorder(session_id)
    token,parent=_current.set(recorder),_parent.set(None)
    try:
        with observation(name,'agent',**values): yield recorder
    finally:
        _parent.reset(parent); _current.reset(token)
        try:
            from ..project import write_json
            root=Path(directory or Path.home()/'.local/state/xp-coding-agent/traces')
            payload=recorder.snapshot()
            path=root/('trace-'+recorder.trace_id+'.json')
            write_json(path,payload)
            if export:
                result=export_trace(payload)
                if not isinstance(result,dict) or not result.get('exported'): raise RuntimeError('Trace not exported')
                write('Trace: '+result['url']+' (id: '+recorder.trace_id+')')
                write_json(path.with_suffix('.export.json'),result)
            else:
                write('Trace recorded locally; export disabled.')
        except Exception:
            write('Warning: trace not exported; inspect local recording and local Langfuse setup. Coding outcome is unchanged.')


@contextmanager
def capture(name):
    """Record an experiment task without disk/network; replay with its SDK parent."""
    recorder=Recorder()
    token,parent=_current.set(recorder),_parent.set(None)
    try:
        with observation(name,'agent'): yield recorder
    finally:
        _parent.reset(parent); _current.reset(token)


def report_usage(usage):
    """Only CLI-reported integer counts; unknown is never estimated as zero."""
    if not isinstance(usage,dict): return
    values={}
    for source,target in {'input_tokens':'input_tokens','output_tokens':'output_tokens',
        'cached_input_tokens':'cache_read_tokens','cache_read_input_tokens':'cache_read_tokens',
        'cache_creation_input_tokens':'cache_creation_tokens'}.items():
        value=usage.get(source)
        if type(value) is int and 0<=value<=10**12: values[target]=value
    annotate(**values,usage_known='input_tokens' in values and 'output_tokens' in values)
