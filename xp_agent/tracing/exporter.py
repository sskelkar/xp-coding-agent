"""Short-lived, local-only exporter. SDK imports and keys stay out of recording."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from . import BASE_URL, MAX_BYTES, MAX_RECORDS, NAMES, attributes, ENUMS
from .evaluation import SCORE_NAMES


def validate(value):
    if set(value)!={'version','trace_id','session_id','records','dropped','scores'} or value['version']!=1:
        raise ValueError('Invalid trace schema')
    if len(json.dumps(value).encode())>MAX_BYTES or len(value['records'])>MAX_RECORDS:
        raise ValueError('Trace too large')
    for key in ('trace_id','session_id'):
        if not isinstance(value[key],str) or not re.fullmatch('[0-9a-f]{32}',value[key]): raise ValueError('Invalid identity')
    if type(value['dropped']) is not int or value['dropped']<0: raise ValueError('Invalid dropped count')
    seen={}
    for row in value['records']:
        if set(row)!={'id','parent','name','kind','start_ns','end_ns','attributes'}: raise ValueError('Invalid observation schema')
        if not re.fullmatch('[0-9a-f]{16}',row['id']) or row['id'] in seen: raise ValueError('Invalid observation identity')
        if row['parent'] is not None and row['parent'] not in seen: raise ValueError('Missing parent')
        if row['name'] not in NAMES or row['kind'] not in {'span','agent','generation','tool'}: raise ValueError('Invalid operation')
        if any(type(row[k]) is not int for k in ('start_ns','end_ns')) or not 0<row['start_ns']<=row['end_ns']: raise ValueError('Invalid timing')
        if row['parent']:
            parent=seen[row['parent']]
            if not parent['start_ns']<=row['start_ns']<=row['end_ns']<=parent['end_ns']: raise ValueError('Invalid hierarchy timing')
        if row['attributes']!=attributes(row['attributes']): raise ValueError('Unapproved metadata')
        seen[row['id']]=row
    if value['records'] and sum(r['parent'] is None for r in value['records'])!=1: raise ValueError('Multiple roots')
    for key,item in value['scores'].items():
        if key not in SCORE_NAMES or not (item is None or type(item) is bool or isinstance(item,str) and item in ENUMS['tdd_sequence']|{'not_applicable'}):
            raise ValueError('Invalid score')


def export(value):
    validate(value)
    keys={name:os.environ.get(name,'') for name in ('LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY')}
    if any(not v or len(v)>256 or not v.isascii() or any(c.isspace() for c in v) for v in keys.values()):
        raise RuntimeError('Configure local project keys')
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','SSL_CERT_FILE') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
    result=subprocess.run([sys.executable,'-m','xp_agent.tracing.exporter'],
        input=json.dumps({'trace':value,'keys':keys}),text=True,env=env,
        cwd=str(Path(__file__).resolve().parents[2]),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        timeout=20)
    if result.returncode: raise RuntimeError('Local export failed')
    response=json.loads(result.stdout)
    if response.get('exported') is not True or set(response)-{'exported','url'}: raise RuntimeError('Invalid export response')
    url=response.get('url')
    if url is not None and not re.fullmatch(re.escape(BASE_URL)+r'/project/[A-Za-z0-9_-]+/traces/'+value['trace_id'],url):
        raise RuntimeError('Invalid local trace URL')
    return {'exported':True,'trace_id':value['trace_id'],'url':url or BASE_URL}


def send(value,keys,*,exporter=None,httpx_client=None):
    """Preserve recorded parent IDs/timestamps with public OTel and SDK wrappers."""
    from langfuse import Langfuse, LangfuseSpan, LangfuseAgent, LangfuseGeneration, LangfuseTool
    from opentelemetry.context import Context
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, set_span_in_context
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.id_generator import IdGenerator
    from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter
    validate(value)
    trace_id=int(value['trace_id'],16)
    class Ids(IdGenerator):
        id_=1
        def generate_trace_id(self): return trace_id
        def generate_span_id(self): return self.id_
    exporter=exporter or local_exporter(keys)
    httpx_client=httpx_client or local_httpx()
    class Checked(SpanExporter):
        failed=False
        def export(self,spans):
            result=exporter.export(spans)
            self.failed |= result!=SpanExportResult.SUCCESS
            return result
        def shutdown(self): exporter.shutdown()
    checked,ids=Checked(),Ids()
    provider=TracerProvider(id_generator=ids,shutdown_on_exit=False)
    client=Langfuse(public_key=keys['LANGFUSE_PUBLIC_KEY'],secret_key=keys['LANGFUSE_SECRET_KEY'],
        base_url=BASE_URL,tracing_enabled=True,environment='local',release='xp-agent-0.1.0',timeout=3,
        sample_rate=1,tracer_provider=provider,span_exporter=checked,httpx_client=httpx_client,
        should_export_span=lambda span:span.instrumentation_scope.name=='xp-agent')
    tracer=provider.get_tracer('xp-agent')
    wrappers=dict(span=LangfuseSpan,agent=LangfuseAgent,generation=LangfuseGeneration,tool=LangfuseTool)
    try:
        pending=[]
        for row in value['records']:
            ids.id_=int(row['id'],16)
            ctx=Context()
            if row['parent']:
                parent=SpanContext(trace_id,int(row['parent'],16),is_remote=False,trace_flags=TraceFlags(1))
                ctx=set_span_in_context(NonRecordingSpan(parent),ctx)
            span=tracer.start_span(row['name'],context=ctx,start_time=row['start_ns'])
            args=dict(otel_span=span,langfuse_client=client,metadata=row['attributes'],environment='local',
                      level='ERROR' if row['attributes'].get('outcome')=='error' else 'DEFAULT')
            if row['kind']=='generation':
                args.update(model=row['attributes'].get('model'),cost_details={'total':0.0},
                            usage_details={k:row['attributes'][v] for k,v in {'input':'input_tokens','output':'output_tokens'}.items() if v in row['attributes']})
                args['metadata']={**args['metadata'],'billing':'unknown'}
            obs=wrappers[row['kind']](**args)
            if row['parent'] is None:
                span.set_attribute('langfuse.trace.name',row['name'])
                span.set_attribute('session.id',value['session_id'])
                obs.update(metadata={**row['attributes'],'dropped_observations':value['dropped'],'evaluator_version':'1'})
            pending.append((obs,row['end_ns']))
        for obs,end in reversed(pending): obs.end(end_time=end)
        if not provider.force_flush(timeout_millis=8000) or checked.failed: raise RuntimeError('Trace export failed')
        for name,item in value['scores'].items():
            if item is None: continue
            client.create_score(trace_id=value['trace_id'],score_id=value['trace_id']+'-'+name,
                name=name,value=int(item) if type(item) is bool else item,
                data_type='BOOLEAN' if type(item) is bool else 'CATEGORICAL',metadata={'evaluator_version':'1'})
        client.flush()
        if getattr(httpx_client,'failed',False): raise RuntimeError('Local score export failed')
        return client.get_trace_url(trace_id=value['trace_id'])
    finally:
        provider.shutdown()
        httpx_client.close()



def local_exporter(keys):
    import base64
    import requests
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    class LocalSession(requests.Session):
        def request(self,method,url,**kwargs):
            if url!=BASE_URL+'/api/public/otel/v1/traces': raise ValueError('Nonlocal destination refused')
            kwargs['allow_redirects']=False
            return super().request(method,url,**kwargs)
    session=LocalSession(); session.trust_env=False
    auth=base64.b64encode((keys['LANGFUSE_PUBLIC_KEY']+':'+keys['LANGFUSE_SECRET_KEY']).encode()).decode()
    exporter=OTLPSpanExporter(endpoint=BASE_URL+'/api/public/otel/v1/traces',
        headers={'Authorization':'Basic '+auth,'x-langfuse-ingestion-version':'4'},timeout=3,session=session)
    return strip_scope_attributes(exporter)


def local_httpx(*,transport=None):
    import httpx
    class LocalClient(httpx.Client):
        failed=False
        def send(self,request,**kwargs):
            if (request.method,str(request.url)) not in {('POST',BASE_URL+'/api/public/scores'),('GET',BASE_URL+'/api/public/projects')}:
                self.failed=True
                raise ValueError('Unapproved SDK destination')
            kwargs['follow_redirects']=False
            try:
                response=super().send(request,**kwargs)
                response.read()
                self.failed |= not response.is_success
                if request.url.path.endswith('/scores') and response.is_success:
                    self.failed |= bool(response.json().get('errors'))
                return response
            except Exception:
                self.failed=True
                raise
    httpx_client=LocalClient(trust_env=False,follow_redirects=False,timeout=3,transport=transport)
    return httpx_client



def strip_scope_attributes(exporter):
    """Langfuse's SDK scope carries its public key; transport must not export it."""
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.sdk.util.instrumentation import InstrumentationScope
    class Filtered(SpanExporter):
        def export(self,spans):
            cleaned=[]
            for span in spans:
                scope=span.instrumentation_scope
                cleaned.append(ReadableSpan(name=span.name,context=span.context,parent=span.parent,
                    resource=span.resource,attributes=span.attributes,events=span.events,links=span.links,
                    kind=span.kind,status=span.status,start_time=span.start_time,end_time=span.end_time,
                    instrumentation_scope=InstrumentationScope(scope.name,scope.version,scope.schema_url) if scope else None))
            return exporter.export(cleaned)
        def shutdown(self): exporter.shutdown()
        def force_flush(self,timeout_millis=30000): return exporter.force_flush(timeout_millis)
    return Filtered()


def main():
    try:
        payload=json.loads(sys.stdin.buffer.read(MAX_BYTES+4096))
        url=send(payload['trace'],payload['keys'])
        print(json.dumps({'exported':True,'url':url}))
        return 0
    except Exception: return 1


if __name__=='__main__': sys.exit(main())
