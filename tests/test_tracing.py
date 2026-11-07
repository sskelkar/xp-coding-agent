import json
import os
from pathlib import Path
import pytest
from xp_agent import tracing


def test_trace_is_bounded_hierarchical_and_metadata_only(tmp_path):
    with tracing.operation('xp.execute', enabled=True, directory=tmp_path, export=False) as trace:
        with tracing.observation('model.propose', 'generation', model='fixture-model', phase='red',
                                 task='private task', files={'secret.py':'private source'}, api_key='private key'):
            tracing.annotate(passed=1, reason='private exception')
    payload=json.loads(next(tmp_path.glob('trace-*.json')).read_text())
    text=json.dumps(payload)
    assert 'private' not in text and 'secret.py' not in text
    assert len(payload['records'])==2
    assert payload['records'][1]['parent']==payload['records'][0]['id']
    assert payload['records'][1]['attributes']['phase']=='red'
    assert payload['session_id']==trace.session_id


def test_disabled_tracing_never_exports_or_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tracing,'export_trace',lambda *a:pytest.fail('unexpected export'))
    with tracing.operation('xp.execute',enabled=False,directory=tmp_path):
        with tracing.observation('run-tests','tool'): pass
    assert not list(tmp_path.iterdir())


def test_export_failure_does_not_replace_domain_exception(tmp_path,monkeypatch):
    monkeypatch.setattr(tracing,'export_trace',lambda *a:(_ for _ in ()).throw(RuntimeError('private diagnostic')))
    output=[]
    with pytest.raises(ValueError,match='domain failure'):
        with tracing.operation('xp.execute',enabled=True,directory=tmp_path,write=output.append):
            raise ValueError('domain failure')
    assert any('not exported' in line for line in output)
    assert all('private diagnostic' not in line for line in output)
    assert next(tmp_path.glob('trace-*.json')).exists()


def test_controller_trace_contains_execution_evidence(tmp_path):
    from test_workflow import spec, Backend, Runner, result, change, TEST
    from xp_agent.workflow import execute
    green = result(passed=('test_calc.py::test_zero','test_calc.py::test_two'))
    with tracing.operation('xp.execute',enabled=True,directory=tmp_path,export=False):
        state=execute(spec(),Backend([change('test_calc.py',TEST),change('calc.py','def double(x):\n    return x * 2\n'),change()]),
                      Runner([result(),result(failed=('test_calc.py::test_two',)),green,green,green]))
    payload=json.loads(next(tmp_path.glob('trace-*.json')).read_text())
    assert state['status']=='verified'
    assert payload['scores']['tdd_sequence']=='complete'
    assert payload['scores']['red_execution_valid'] is True
    assert len([r for r in payload['records'] if r['name']=='run-tests'])==5
    assert len([r for r in payload['records'] if r['kind']=='generation'])==3
    assert all(e.get('version')==1 and e.get('before_hash') for e in state['evidence'])


def test_export_rejects_raw_record_fields():
    from xp_agent.tracing.exporter import validate
    value=tracing.Recorder().snapshot()
    value['raw']='private source'
    with pytest.raises(ValueError): validate(value)


def test_repl_trace_toggle_records_rejection_without_execution(tmp_path,monkeypatch):
    from xp_agent.repl import shell
    from test_session import project,Planner
    root=project(tmp_path)
    exported=[]
    monkeypatch.setattr(tracing,'export_trace',lambda value:exported.append(value) or {'exported':True,'url':'local'})
    replies=iter(['/trace on','Double inputs','reject','/quit'])
    shell(root,backend=Planner(),image='fixture',output_root=tmp_path/'runs',
          read=lambda p:next(replies),write=lambda m:None,
          runner_factory=lambda *a,**k:pytest.fail('Unapproved execution'))
    assert len(exported)==1
    assert exported[0]['records'][0]['attributes']['status']=='rejected'
    assert any(r['kind']=='generation' for r in exported[0]['records'])
    assert json.loads((tmp_path/'settings.json').read_text())['trace'] is True


def test_score_validator_detects_mutated_accepted_evidence():
    import copy
    from test_workflow import spec,Backend,Runner,result,change,TEST
    from xp_agent.workflow import execute
    from xp_agent.tracing.evaluation import evaluate_state
    green=result(passed=('test_calc.py::test_zero','test_calc.py::test_two'))
    state=execute(spec(),Backend([change('test_calc.py',TEST),change('calc.py','def double(x):\n    return x*2\n'),change()]),
                  Runner([result(),result(failed=('test_calc.py::test_two',)),green,green,green]))
    for mutate in [lambda r:r[1].update(source_hash='f'*64),
                   lambda r:r[2].update(test_hash='f'*64),
                   lambda r:r[1].update(failed=[]),
                   lambda r:r[2].update(passed=[]),
                   lambda r:r.reverse()]:
        broken=copy.deepcopy(state); mutate(broken['evidence'])
        assert evaluate_state(broken)['tdd_sequence'] in {'violation','insufficient_evidence'}
    partial=copy.deepcopy(state); partial['evidence']=partial['evidence'][:2];partial['status']='cancelled'
    assert evaluate_state(partial)['tdd_sequence']=='valid_partial'
    del partial['evidence'][0]['before_hash']
    assert evaluate_state(partial)['tdd_sequence']=='insufficient_evidence'


def test_pair_contract_requires_swaps_and_fresh_handoffs():
    from xp_agent.tracing.evaluation import evaluate_pair
    events=[dict(sequence=i,phase=phase,actor=actor,before=None if i==1 else str(i-1),artifact=str(i),accepted=True)
            for i,(phase,actor) in enumerate([('red','A'),('green','B'),('red','B'),('green','A')],1)]
    assert all(evaluate_pair(events).values())
    events[2]['actor']='A'
    assert evaluate_pair(events)['pair_ownership_valid'] is False
    events[2]['before']='stale'
    assert evaluate_pair(events)['handoff_state_valid'] is False


def test_sdk_export_preserves_hierarchy_without_inputs_or_outputs(tmp_path):
    pytest.importorskip('langfuse')
    import httpx
    from opentelemetry.sdk.trace.export import SpanExporter,SpanExportResult
    from xp_agent.tracing.exporter import send
    class Memory(SpanExporter):
        spans=[]
        def export(self,spans): self.spans.extend(spans); return SpanExportResult.SUCCESS
        def shutdown(self): pass
    requests=[]
    def respond(request):
        requests.append(request)
        if request.method=='GET': return httpx.Response(200,json={'data':[{'id':'fixture-project','name':'Fixture','organization':{'id':'fixture-org','name':'Fixture'},'metadata':{}}]})
        return httpx.Response(200,json={'successes':[],'errors':[]})
    with tracing.operation('xp.execute',enabled=True,directory=tmp_path,export=False) as recording:
        with tracing.observation('model.propose','generation',model='fixture-model',usage_known=False): pass
    memory=Memory()
    url=send(recording.snapshot(),{'LANGFUSE_PUBLIC_KEY':'pk-lf-fixture-'+recording.trace_id,'LANGFUSE_SECRET_KEY':'sk-lf-fixture'},
         exporter=memory,httpx_client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert url==tracing.BASE_URL+'/project/fixture-project/traces/'+recording.trace_id
    assert len(memory.spans)==2
    root=next(s for s in memory.spans if s.name=='xp.execute')
    child=next(s for s in memory.spans if s.name=='model.propose')
    assert child.parent.span_id==root.context.span_id
    assert root.attributes['session.id']==recording.session_id
    assert child.attributes['langfuse.observation.type']=='generation'
    assert all('langfuse.observation.input' not in s.attributes and 'langfuse.observation.output' not in s.attributes for s in memory.spans)
    assert root.start_time<=child.start_time<=child.end_time<=root.end_time


def test_experiment_suite_gate_requires_every_expected_case():
    from xp_agent.tracing.experiments import quality_gate,CASE_NAMES
    good=[{'name':name,'passed':True} for name in CASE_NAMES]
    assert quality_gate(good)
    assert not quality_gate(good[:-1])
    assert not quality_gate(good+[good[0]])
    assert not quality_gate([{**c,'passed':False} if i==0 else c for i,c in enumerate(good)])


def test_sdk_experiment_uses_safe_items_outputs_and_scores(monkeypatch):
    pytest.importorskip('langfuse')
    import httpx
    import uuid
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter,SpanExportResult
    from xp_agent import evals
    from xp_agent.tracing.experiments import execute_experiment,CASE_NAMES
    class Memory(SpanExporter):
        def __init__(self): self.spans=[]
        def export(self,spans): self.spans.extend(spans);return SpanExportResult.SUCCESS
        def shutdown(self): pass
    requests=[]
    def respond(request):
        requests.append(request)
        if request.method=='GET': return httpx.Response(200,json={'data':[{'id':'fixture-project','name':'Fixture','organization':{'id':'fixture-org','name':'Fixture'},'metadata':{}}]})
        return httpx.Response(200,json={'successes':[],'errors':[]})
    def fixture(name,**kwargs):
        with tracing.observation('model.propose','generation',phase='red',task='PRIVATE TASK'): pass
        return {'name':name,'passed':True,'actual':'verified','reason':'PRIVATE REASON','scores':{'tdd_sequence':'complete'},'increments':['PRIVATE SOURCE']}
    monkeypatch.setattr(evals,'evaluate_case',fixture)
    memory=Memory();provider=TracerProvider(shutdown_on_exit=False)
    client=Langfuse(public_key='pk-lf-fixture-'+uuid.uuid4().hex,secret_key='sk-lf-fixture',base_url=tracing.BASE_URL,
                    tracer_provider=provider,span_exporter=memory,
                    httpx_client=httpx.Client(transport=httpx.MockTransport(respond)),environment='local',
                    should_export_span=lambda span:span.instrumentation_scope.name in {'xp-agent','langfuse-sdk'})
    try:
        result=execute_experiment(client,provider)
        client.flush();provider.force_flush()
        assert result['passed'] is True
        assert len(result['cases'])==len(CASE_NAMES)
        assert len([s for s in memory.spans if s.name=='model.propose'])==9
        assert all(s.parent is not None for s in memory.spans if s.name=='xp.evaluation')
        assert 'PRIVATE' not in json.dumps([dict(s.attributes) for s in memory.spans])
        assert any('/scores' in str(r.url) for r in requests)
    finally: provider.shutdown()


def test_trace_caps_records_and_marks_scores_incomplete(tmp_path,monkeypatch):
    monkeypatch.setattr(tracing,'MAX_RECORDS',2)
    with tracing.operation('xp.execute',enabled=True,directory=tmp_path,export=False):
        with tracing.observation('coding-phase'):
            with tracing.observation('run-tests','tool'): pass
        tracing.set_scores({'tdd_sequence':'complete'})
    value=json.loads(next(tmp_path.glob('trace-*.json')).read_text())
    assert len(value['records'])==2 and value['dropped']==1
    assert value['scores']['evidence_complete'] is False
    assert value['scores']['tdd_sequence']=='insufficient_evidence'


def test_export_child_receives_no_ambient_credentials_or_proxies(monkeypatch):
    from xp_agent.tracing import exporter
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY','pk-lf-fixture')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY','sk-lf-fixture')
    monkeypatch.setenv('ANTHROPIC_API_KEY','private')
    monkeypatch.setenv('HTTPS_PROXY','https://private.invalid')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT','https://private.invalid')
    def launch(args,**kwargs):
        assert not any(k.startswith(('LANGFUSE','ANTHROPIC','OTEL')) or 'PROXY' in k for k in kwargs['env'])
        assert 'private' not in json.dumps(args)
        assert kwargs['timeout']==20
        assert json.loads(kwargs['input'])['keys']['LANGFUSE_PUBLIC_KEY']=='pk-lf-fixture'
        class Child: returncode=0;stdout='{"exported":true}'
        return Child()
    monkeypatch.setattr(exporter.subprocess,'run',launch)
    assert exporter.export(tracing.Recorder().snapshot())['exported'] is True


def test_local_http_transport_refuses_cloud_and_redirect_destinations():
    pytest.importorskip('langfuse')
    import httpx
    from xp_agent.tracing.exporter import local_httpx
    client=local_httpx()
    try:
        with pytest.raises(ValueError,match='destination'): client.get('https://cloud.langfuse.com/api/public/projects')
        with pytest.raises(ValueError,match='destination'): client.get(tracing.BASE_URL+'/unapproved')
    finally: client.close()


def test_reported_usage_is_validated_and_missing_usage_stays_unknown(tmp_path):
    with tracing.operation('xp.execute',enabled=True,directory=tmp_path,export=False) as recorder:
        with tracing.observation('model.propose','generation',usage_known=False):
            tracing.report_usage({'input_tokens':12,'output_tokens':4,'cached_input_tokens':3,'secret':'PRIVATE'})
        with tracing.observation('model.propose','generation',usage_known=False):
            tracing.report_usage({'input_tokens':'PRIVATE','output_tokens':-1})
    first,second=recorder.records[1:]
    assert first['attributes']['usage_known'] is True
    assert first['attributes']['cache_read_tokens']==3
    assert second['attributes']['usage_known'] is False


def test_sdk_score_upload_failure_is_not_reported_as_success(tmp_path):
    pytest.importorskip('langfuse')
    import httpx
    import uuid
    from opentelemetry.sdk.trace.export import SpanExporter,SpanExportResult
    from xp_agent.tracing.exporter import send,local_httpx
    class Memory(SpanExporter):
        def export(self,spans): return SpanExportResult.SUCCESS
        def shutdown(self): pass
    with tracing.operation('xp.execute',enabled=True,directory=tmp_path,export=False) as recorder:
        tracing.set_scores({'tdd_sequence':'complete'})
    client=local_httpx(transport=httpx.MockTransport(lambda r:httpx.Response(400,json={})))
    with pytest.raises(RuntimeError,match='score'):
        send(recorder.snapshot(),{'LANGFUSE_PUBLIC_KEY':'pk-lf-fixture-'+uuid.uuid4().hex,'LANGFUSE_SECRET_KEY':'sk-lf-fixture'},
             exporter=Memory(),httpx_client=client)


def test_primary_repl_traces_resume_with_preserved_identity_and_budget(tmp_path,monkeypatch):
    from xp_agent.repl import shell
    from xp_agent.session import load_session
    from test_session import project,Planner
    from test_workflow import Runner,result,change
    root=project(tmp_path);exports=[]
    class Partner(Planner):
        interrupted=False
        def propose(self,phase,context,timeout):
            if phase=='plan': return super().propose(phase,context,timeout)
            if phase=='red': return change('test_calc.py',context['files']['test_calc.py']+'\ndef test_two():\n    assert double(2)==4\n')
            if phase=='green':
                if not self.interrupted:
                    self.interrupted=True
                    raise KeyboardInterrupt
                return change('calc.py','def double(x):\n    return x*2\n')
            return change()
    def export(value):
        exports.append(value)
        # Even unavailable tracing must not obstruct cancellation or continuation.
        raise RuntimeError('PRIVATE SERVER ERROR')
    monkeypatch.setattr(tracing,'export_trace',export)
    green=result(passed=('test_calc.py::test_zero','test_calc.py::test_two'))
    runners=iter([Runner([result(),result(failed=('test_calc.py::test_two',))]),Runner([green,green,green])])
    answers=iter(['Double inputs','approve','/resume','/quit']);messages=[]
    shell(root,backend=Partner(),image='fixture',trace=True,output_root=tmp_path/'runs',
          read=lambda p:next(answers),write=messages.append,runner_factory=lambda *a,**k:next(runners))
    record=load_session(next((tmp_path/'runs').iterdir()))
    assert record['status']=='verified' and record['states'][0]['attempts']['green']==2
    assert len(exports)==3 and len({e['session_id'] for e in exports})==1
    assert exports[1]['scores']['tdd_sequence']=='valid_partial'
    assert exports[2]['scores']['tdd_sequence']=='complete'
    assert exports[2]['records'][0]['attributes']['previous_trace_id']==exports[1]['trace_id']
    assert any(r['name']=='prepare-workspace' for r in exports[1]['records'])
    assert not any(r['name']=='prepare-workspace' for r in exports[2]['records'])
    assert not any('PRIVATE SERVER ERROR' in m for m in messages)


@pytest.mark.skipif(os.getenv('XP_DOCKER_TESTS')!='1',reason='Requires Docker')
def test_sdk_experiment_runs_real_repl_and_docker_fixtures():
    pytest.importorskip('langfuse')
    import httpx
    import uuid
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter,SpanExportResult
    from xp_agent.tracing.experiments import execute_experiment,CASE_NAMES
    class Memory(SpanExporter):
        def __init__(self): self.spans=[]
        def export(self,spans): self.spans.extend(spans); return SpanExportResult.SUCCESS
        def shutdown(self): pass
    def respond(request):
        if request.method=='GET':
            return httpx.Response(200,json={'data':[{'id':'fixture-project','name':'Fixture',
                'organization':{'id':'fixture-org','name':'Fixture'},'metadata':{}}]})
        return httpx.Response(200,json={'successes':[],'errors':[]})
    memory=Memory();provider=TracerProvider(shutdown_on_exit=False)
    client=Langfuse(public_key='pk-lf-fixture-'+uuid.uuid4().hex,secret_key='sk-lf-fixture',base_url=tracing.BASE_URL,
        tracer_provider=provider,span_exporter=memory,httpx_client=httpx.Client(transport=httpx.MockTransport(respond)),
        environment='local',should_export_span=lambda span:span.instrumentation_scope.name in {'xp-agent','langfuse-sdk'})
    try:
        report=execute_experiment(client,provider)
        client.flush();provider.force_flush()
        assert report['passed'] and len(report['cases'])==len(CASE_NAMES)
        cases={case['name']:case for case in report['cases']}
        assert cases['repl_success']['scores']['tdd_sequence']=='complete'
        assert cases['repl_success']['scores']['independent_acceptance_passed'] is True
        assert cases['repl_reject']['actual']=='rejected'
        assert cases['pair_self_implementation']['scores']['pair_ownership_valid'] is False
        assert any(s.name=='run-tests' for s in memory.spans)
        data=json.dumps([dict(s.attributes) for s in memory.spans])
        assert 'def double' not in data and 'test_calc.py' not in data
        assert str(Path.cwd()) not in data
    finally: provider.shutdown()


def test_experiment_cancellation_gives_worker_a_cleanup_window(monkeypatch):
    import signal
    import subprocess
    from xp_agent.tracing.experiments import run_experiment
    from xp_agent import process
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY','pk-lf-fixture')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY','sk-lf-fixture')
    monkeypatch.setattr(process,'run',lambda *a,**k:(_ for _ in ()).throw(KeyboardInterrupt()))
    signals=[]
    class Child:
        calls=0
        def communicate(self,*a,**k):
            self.calls+=1
            if self.calls==1: raise KeyboardInterrupt
            return ('','')
        def poll(self): return None
        def send_signal(self,value): signals.append(value)
        def kill(self): pytest.fail('Worker should have a cleanup window')
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:Child())
    with pytest.raises(KeyboardInterrupt): run_experiment()
    assert signals==[signal.SIGINT]


def test_exporter_strips_sdk_scope_credentials_before_transport():
    pytest.importorskip('langfuse')
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor,SpanExporter,SpanExportResult
    from xp_agent.tracing.exporter import strip_scope_attributes
    class Memory(SpanExporter):
        def __init__(self): self.spans=[]
        def export(self,spans): self.spans.extend(spans);return SpanExportResult.SUCCESS
        def shutdown(self): pass
    memory=Memory();provider=TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(strip_scope_attributes(memory)))
    try:
        tracer=provider.get_tracer('langfuse-sdk','fixture',attributes={'public_key':'pk-lf-PRIVATE','other':'PRIVATE'})
        with tracer.start_as_current_span('experiment-item-task') as span: span.set_attribute('safe','fixture')
        provider.force_flush()
        actual=memory.spans[0]
        assert not actual.instrumentation_scope.attributes
        assert actual.instrumentation_scope.name=='langfuse-sdk'
        assert actual.attributes['safe']=='fixture'
    finally:provider.shutdown()
