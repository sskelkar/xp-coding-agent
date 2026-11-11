"""Controller operations for the production graph: private state, code and tests."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import re
import time
from ..policy import PolicyError, safe_path, check_content, validate_edits, digest, discover
from ..project import write_files
from .. import tracing
from .partners import parse_reply


RESERVED={'pytest.py','conftest.py','sitecustomize.py','usercustomize.py','test_pair_demo.py','test_pair_acceptance.py'}


def is_test(path):return Path(path).name.startswith('test_') or Path(path).name.endswith('_test.py')
def green(report,required=()):
    return (report['returncode']==0 and bool(report['passed']) and not any(report[k] for k in ('failed','errors','skipped'))
            and set(required)<=set(report['passed']))


class Operations:
    confirmed=False
    refactoring=True
    def __init__(self,partners,runner,workspace,goal,files,*,budget=900,attempts=2,max_cycles=12,demo_every=2):
        if set(partners)!={'A','B'} or partners['A'] is partners['B']:raise ValueError('Two distinct partners required')
        for actor,partner in partners.items():
            if partner.identity!=actor:raise ValueError('Partner identity mismatch')
        self.partners,self.runner,self.workspace=partners,runner,Path(workspace)
        self.goal,self.files,self.budget=goal,files,budget
        self.attempts,self.max_cycles,self.demo_every=attempts,max_cycles,demo_every
        if min(budget,attempts,max_cycles,demo_every)<=0:raise ValueError('Positive resource limits required')

    def initialize(self,state):
        return dict(phase='red',cycle=1,files=self.files,pending={},status='running',reason='',
                    required=[],baseline=[],histories={'A':[],'B':[]},records=[],snapshots={},agreement=1,
                    goal=self.goal,feedback='',attempts=0,remaining=self.budget,active=0.,last_feedback_active=0.,
                    since_feedback=0,bootstrap_done=False,config={'max_cycles':self.max_cycles})

    def _message(self,s,actor,phase,text,reference=None):
        message={'id':f"message-{len(s['histories']['A'])}",'actor':actor,'phase':phase,'message':text,'reference':reference}
        for identity in ('A','B'):s['histories'][identity].append(deepcopy(message))

    def _record(self,s,kind,**fields):
        event={'kind':kind,'id':f"event-{len(s['records'])}",'active_seconds':s['active'],**fields}
        s['records'].append(event)
        return event

    def _call(self,actor,phase,state):
        s=deepcopy(state)
        if s['remaining']<=0 or (s['cycle']>self.max_cycles and phase!='demo'):
            return {**s,'status':'blocked','reason':'Pair execution budget exhausted'},None
        start=time.monotonic()
        try:
            backend=getattr(self.partners[actor],'backend',None)
            with tracing.observation('model.propose','generation',actor=actor,phase=phase,mode='pair',
                    model=getattr(backend,'model','scripted-fixture'),provider=getattr(backend,'provider',None),
                    auth=getattr(backend,'auth',None),usage_known=False):
                reply=parse_reply(self.partners[actor].reply(phase,s))
            if reply['action']!='edit' and reply['edits']:raise PolicyError('Only edit actions may contain edits')
            self._message(s,actor,phase,reply['message'])
            return s,reply
        except (ValueError,RuntimeError,OSError) as exc:
            s.update(status='blocked',reason=str(exc))
            return s,None
        finally:
            elapsed=time.monotonic()-start
            s['remaining']-=elapsed;s['active']+=elapsed

    def _run(self,s,files,phase):
        start=time.monotonic()
        if s['remaining']<=0:raise PolicyError('Execution time exhausted')
        with tracing.observation('run-tests','tool',phase=phase,mode='pair'):
            report=self.runner.test(files,min(s['remaining'],60))
        elapsed=time.monotonic()-start
        s['remaining']-=elapsed;s['active']+=elapsed
        return report

    def confirm(self,state):
        s=deepcopy(state)
        event=self._record(s,'agreement',actor='user',revision=1)
        self._message(s,'user','agreement','Confirmed outcome: '+s['goal'],event['id'])
        return s

    def baseline(self,state):
        s=deepcopy(state)
        if not any(is_test(p) for p in s['files']):return s  # Explicitly no baseline, not a passing zero-test claim.
        try:
            r=self._run(s,s['files'],'baseline')
            if not green(r):raise PolicyError('Existing baseline must pass before pairing')
            s['required']=r['passed'];s['baseline']=r['passed']
        except (ValueError,RuntimeError,OSError) as exc:s.update(status='blocked',reason=str(exc))
        return s

    def discuss(self,actor,state):
        s,reply=self._call(actor,'discuss',state)
        if reply:
            if reply['edits']:return {**s,'status':'blocked','reason':'Discussion cannot edit files'}
            if reply['action'] in {'question','demo'}:s.update(status=reply['action'],pending={'actor':actor,'reply':reply})
        return s

    def propose(self,actor,phase,state):
        s,reply=self._call(actor,phase,state)
        s['attempts']=state['attempts']+1
        if not reply:return s
        if reply['action'] in {'question','demo'}:
            return {**s,'status':reply['action'],'pending':{'actor':actor,'reply':reply}}
        try:
            if phase!='refactor' and reply['action']!='edit':raise PolicyError('This phase requires an edit')
            edits={e['path']:e['content'] for e in reply['edits']}
            if any(Path(p).name in RESERVED for p in edits):raise PolicyError('Reserved test infrastructure cannot be edited')
            if any(not p.endswith('.py') for p in edits):raise PolicyError('Only project Python paths may be edited')
            tests=[p for p in s['files'].keys()|edits.keys() if is_test(p)]
            sources=[p for p in s['files'].keys()|edits.keys() if not is_test(p)]
            candidate=validate_edits(phase,s['files'],edits,sources,tests)
            if sum(len(v.encode()) for v in candidate.values())>400_000:raise PolicyError('Snapshot exceeds 400 KB')
            s.update(status='running',pending={'actor':actor,'reply':reply,'files':candidate,
                                              'before':digest(s['files']),'started_active':state['active'],
                                              'history':deepcopy(s['histories'][actor][:-1])})
        except (ValueError,RuntimeError) as exc:return self.reject(s,str(exc))
        return s

    def test(self,state):
        s=deepcopy(state)
        try:
            s['report']=self._run(s,s['pending']['files'],s['phase'])
            r=s['report']
            if (s['phase']=='red' and r['errors'] and not s['bootstrap_done']
                    and any(name in r.get('output','') for name in ('ModuleNotFoundError','ImportError','AttributeError','NameError'))):
                s['status']='scaffold_needed'
        except (ValueError,RuntimeError,OSError) as exc:s.update(status='blocked',reason=str(exc))
        return s

    def bootstrap(self,state):
        actor='B' if state['cycle']%2 else 'A'
        pending=deepcopy(state['pending'])
        context={**state,'files':pending['files'],'feedback':state['report'].get('output','')[-4000:]}
        s,reply=self._call(actor,'bootstrap',context)
        # Accepted files are still the old snapshot; pending tests are not lost.
        s['files']=deepcopy(state['files']);s['pending']=pending
        if not reply:return s
        try:
            edits={e['path']:e['content'] for e in reply['edits']}
            if reply['action']!='edit' or not edits:raise PolicyError('Scaffolding requires source edits')
            for path,content in edits.items():
                safe_path(path)
                if Path(path).name in RESERVED:raise PolicyError('Reserved test infrastructure cannot be scaffolded')
                if is_test(path) or not path.endswith('.py'):raise PolicyError('Scaffolding cannot change tests')
                old=ast.parse(s['files'].get(path,'')).body;new=ast.parse(content).body
                if [ast.dump(n) for n in new[:len(old)]]!=[ast.dump(n) for n in old]:raise PolicyError('Scaffolding must preserve existing source')
            candidate={**pending['files'],**edits}
            if sum(len(v.encode()) for v in candidate.values())>400_000:raise PolicyError('Snapshot exceeds 400 KB')
            r=self._run(s,candidate,'red')
            if r['returncode']!=1 or not r['failed'] or r['errors'] or r['skipped'] or not set(s['required'])<=set(r['passed']):
                raise PolicyError('Scaffolding must leave a meaningful assertion failure')
            source_only={**s['files'],**edits}
            self._sync(s['files'],source_only)
            before_id,after_id,checked=digest(s['files']),digest(source_only),digest(candidate)
            s['snapshots'].update({before_id:deepcopy(s['files']),after_id:deepcopy(source_only),checked:deepcopy(candidate)})
            history=deepcopy(s['histories'][actor][:-1])
            event=self._record(s,'bootstrap',actor=actor,cycle=s['cycle'],phase='bootstrap',
                  before=before_id,after=after_id,checked=checked,agreement=s['agreement'],context='partner-'+actor,
                  history=[m['reference'] for m in history if m.get('reference')],
                  report={**{k:r[k] for k in ('returncode','passed','failed','errors','skipped')},
                          'revision':checked,'required':s['required']})
            self._message(s,'controller','bootstrap','Scaffolding validated; behavioral test still fails.',event['id'])
            s['files']=source_only
            s['pending']['files']=candidate;s['pending']['before']=digest(source_only)
            s['bootstrap_done']=True;s['status']='running'
        except (ValueError,RuntimeError,OSError,SyntaxError) as exc:s.update(status='blocked',reason=str(exc))
        return s

    def _sync(self,before,after):
        # Private snapshot only. Never overwrite unexplained human edits or symlinks.
        names=[]
        for path in self.workspace.rglob('*'):
            if '.git' in path.relative_to(self.workspace).parts:continue
            if path.is_symlink():raise PolicyError('Workspace contains a symlink')
            if path.is_file():names.append(path.relative_to(self.workspace).as_posix())
        current=discover(self.workspace,names) if names else {}
        if current not in (before,after):raise PolicyError('Workspace changed externally; reconcile before continuing')
        write_files(self.workspace,after)

    def accept(self,state):
        s=deepcopy(state);p=s['pending'];after=p['files']
        try:self._sync(s['files'],after)
        except (ValueError,OSError) as exc:return {**s,'status':'blocked','reason':str(exc)}
        before_id,after_id=digest(s['files']),digest(after)
        s['snapshots'][before_id]=deepcopy(s['files']);s['snapshots'][after_id]=deepcopy(after)
        event=self._record(s,'step',actor=p['actor'],cycle=s['cycle'],phase=s['phase'],before=before_id,after=after_id,
                     agreement=s['agreement'],context='partner-'+p['actor'],history=[m['reference'] for m in p['history'] if m.get('reference')],
                     dispatch_active=p['started_active'],
                     report={**{k:v for k,v in s['report'].items() if k!='output'},
                             'revision':after_id,'required':s['required']})
        self._message(s,'controller',s['phase'],f"Accepted {p['actor']} {s['phase']}; tests: "+json.dumps({k:len(s['report'][k]) for k in ('passed','failed','errors','skipped')}),event['id'])
        s.update(files=after,status='running',feedback='',bootstrap_done=False if s['phase']=='refactor' else s['bootstrap_done'])
        return s

    def reject(self,state,reason):
        s=deepcopy(state);s['feedback']=reason+'\n'+s.get('report',{}).get('output','')[-4000:]
        self._message(s,'controller',s['phase'],'Rejected candidate: '+reason)
        s['status']='blocked' if s['attempts']>=self.attempts or s['remaining']<=0 else 'retry'
        s['reason']=reason
        return s

    def checkin_due(self,state):return state['active']-state['last_feedback_active']>=300

    def demo_due(self,state):
        return state['since_feedback']>=self.demo_every or state['active']-state['last_feedback_active']>=300 or state['cycle']>self.max_cycles

    def prepare_demo(self,state):
        s=deepcopy(state)
        if s['status']=='question':
            event=self._record(s,'question',actor=s['pending']['actor'])
            self._message(s,'controller','question',s['pending']['reply']['message'],event['id'])
            return {**s,'demo':{'kind':'business_question','message':s['pending']['reply']['message'],
                               'working_increment':False,'revision':digest(s['files']),'event_id':event['id']}}
        if self.checkin_due(s) and s['phase']!='red':
            event=self._record(s,'question',actor='controller')
            self._message(s,'controller','question','Active-time progress check-in',event['id'])
            return {**s,'status':'question','demo':{'kind':'progress_update','working_increment':False,
                'message':'Active-time check-in: an incomplete TDD cycle remains. Continue or clarify the outcome.',
                'revision':digest(s['files']),'event_id':event['id']}}
        if s['phase']!='red' or not s['required']:
            return {**s,'status':'blocked','demo':{'kind':'blocked','message':'No completed green increment to demonstrate'}}
        s,reply=self._call('A','demo',s)
        if not reply or reply['edits'] or not reply['examples']:
            return {**s,'status':'blocked','demo':{'kind':'blocked','message':'Executable demonstration required'}}
        try:
            examples=[]
            for i,e in enumerate(reply['examples']):
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*',e['module']):raise PolicyError('Invalid demo module')
                if e['module'].replace('.','/')+'.py' not in s['files']:raise PolicyError('Demo module absent from project')
                e['expression']=ast.unparse(ast.parse(e['expression'],mode='eval').body)
                examples.append(f"def test_demo_{i}():\n    import {e['module']} as api\n    import json, sys\n    actual = {e['expression']}\n    assert actual == {e['expected']!r}\n    record = dict(label={e['label']!r},actual=actual,expected={e['expected']!r})\n    sys.__stdout__.write('XP_PAIR_DEMO=' + json.dumps(record) + '\\n')\n")
            report=self._run(s,{**s['files'],'test_pair_demo.py':'\n'.join(examples)},'final')
            if not green(report,s['required']):raise PolicyError('Demonstration failed its executable checks')
            actual=[]
            for line in re.findall(r'XP_PAIR_DEMO=([^\n]+)',report['output']):
                actual.append(json.loads(line))
            if len(actual)!=len(examples):raise PolicyError('Demo did not return expected observations')
            event=self._record(s,'demo',actor='controller',revision=digest(s['files']),
                               samples=[dict(input=x['label'],actual=x['actual'],expected=x['expected']) for x in actual])
            self._message(s,'controller','demo',reply['message'],event['id'])
            s.update(status='waiting',demo={'kind':'working_demo','message':reply['message'],
                       'revision':digest(s['files']),'event_id':event['id'],'examples':actual,'cycle':s['cycle']-1,
                       'prompt':'accept, continue, or clarify the outcome'})
        except (ValueError,RuntimeError,OSError,SyntaxError) as exc:s.update(status='blocked',reason=str(exc),demo={'kind':'blocked','message':str(exc)})
        return s

    def feedback(self,state,answer):
        s=deepcopy(state)
        if s['status']=='blocked':return s
        if answer=='accept' and s['demo']['kind']=='working_demo':s['status']='accepted'
        elif answer=='continue':s['status']='running'
        elif isinstance(answer,str) and answer.strip() and answer!='accept':
            s['agreement']+=1;s['goal']+='\nBusiness clarification: '+answer;s['status']='running'
        else:return {**s,'status':'blocked','reason':'Invalid business decision'}
        event=self._record(s,'feedback',actor='user',revision=s['agreement'],demo=s['demo']['event_id'],
                           decision=str(answer) if answer in ('accept','continue') else 'revise')
        self._message(s,'user','feedback',str(answer),event['id'])
        s.update(feedback=str(answer),since_feedback=0,last_feedback_active=s['active'])
        return s
