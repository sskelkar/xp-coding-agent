"""Local-data SDK experiments. Only synthetic IDs and bounded summaries are sent."""
import json
import os
from pathlib import Path
import sys
from ..evals import CASE_NAMES as CONTROLLER_CASES
from .evaluation import SCORE_NAMES,evaluate_pair
from . import BASE_URL

PAIR_CASES=['pair_valid','pair_self_implementation','pair_missing_swap','pair_stale_handoff']
CASE_NAMES=CONTROLLER_CASES+PAIR_CASES


def quality_gate(cases):
    """No averages: missing, duplicate, unknown or failed cases fail the suite."""
    return len(cases)==len(CASE_NAMES) and {c.get('name') for c in cases}==set(CASE_NAMES) and all(c.get('passed') is True for c in cases)


def safe_result(value):
    result={'name':value['name'],'passed':value['passed'] is True}
    if value.get('actual') in {'verified','blocked','rejected'}: result['actual']=value['actual']
    scores={k:v for k,v in value.get('scores',{}).items() if k in SCORE_NAMES and
            (v is None or type(v) is bool or isinstance(v,str) and v in {'complete','valid_partial','violation','insufficient_evidence','not_applicable'})}
    if type(value.get('independent_acceptance')) is bool: scores['independent_acceptance_passed']=value['independent_acceptance']
    result['scores']=scores
    return result


def pair_case(name):
    events=[dict(sequence=i,phase=phase,actor=actor,before=None if i==1 else str(i-1),artifact=str(i),accepted=True)
        for i,(phase,actor) in enumerate([('red','A'),('green','B'),('red','B'),('green','A')],1)]
    if name=='pair_self_implementation': events[1]['actor']='A'
    if name=='pair_missing_swap': events[2]['actor']='A'
    if name=='pair_stale_handoff': events[2]['before']='stale'
    scores=evaluate_pair(events)
    expected={'pair_ownership_valid':name not in {'pair_self_implementation','pair_missing_swap'},
              'handoff_state_valid':name!='pair_stale_handoff'}
    return {'name':name,'passed':scores==expected,'scores':scores}


def replay(client,provider,value):
    """Attach recorded controller spans below the SDK experiment task, preserving time."""
    from langfuse import LangfuseSpan,LangfuseAgent,LangfuseGeneration,LangfuseTool
    from opentelemetry import trace
    from .exporter import validate
    validate(value)
    tracer=provider.get_tracer('xp-agent')
    spans={}; pending=[]
    wrappers=dict(span=LangfuseSpan,agent=LangfuseAgent,generation=LangfuseGeneration,tool=LangfuseTool)
    for row in value['records']:
        context=trace.set_span_in_context(spans[row['parent']]) if row['parent'] else None
        span=tracer.start_span(row['name'],context=context,start_time=row['start_ns'])
        spans[row['id']]=span
        args=dict(otel_span=span,langfuse_client=client,metadata=row['attributes'],environment='local')
        if row['kind']=='generation': args.update(model=row['attributes'].get('model'),cost_details={'total':0.0},metadata={**row['attributes'],'billing':'unknown'})
        pending.append((wrappers[row['kind']](**args),row['end_ns']))
    for obs,end in reversed(pending): obs.end(end_time=end)


def execute_experiment(client,provider):
    """The same real REPL/Docker paths as ordinary evals; one case at a time."""
    from langfuse import Evaluation
    from ..evals import evaluate_case
    from . import capture
    outputs=[]
    def task(*,item,**kwargs):
        name=item['input']
        try:
            with capture('xp.evaluation') as recorder:
                result=pair_case(name) if name in PAIR_CASES else evaluate_case(name,trace=False)
        except Exception:
            # SDK task exception capture would publish traceback paths/diagnostics.
            result={'name':name,'passed':False,'actual':'blocked'}
        replay(client,provider,recorder.snapshot())
        result=safe_result(result)
        outputs.append(result)
        return result
    def evaluate(*,output,**kwargs):
        scores=[Evaluation(name='case_passed',value=int(output['passed']),data_type='BOOLEAN')]
        for name,value in output['scores'].items():
            if value is None: continue
            scores.append(Evaluation(name=name,value=int(value) if type(value) is bool else value,
                                     data_type='BOOLEAN' if type(value) is bool else 'CATEGORICAL'))
        return scores
    def gate(*,item_results,**kwargs):
        return Evaluation(name='suite_passed',value=int(quality_gate([item.output for item in item_results])),data_type='BOOLEAN')
    result=client.run_experiment(name='xp-scripted-v1',run_name='xp-scripted-v1',
        data=[{'input':name,'expected_output':{'case_passed':True},'metadata':{'fixture_version':'1'}} for name in CASE_NAMES],
        task=task,evaluators=[evaluate],run_evaluators=[gate],max_concurrency=1,
        metadata={'evaluator_version':'1','providers':'scripted','pairing':'synthetic-contract-only'})
    return {'passed':quality_gate(outputs) and len(result.item_results)==len(CASE_NAMES) and
                all(any(e.name=='case_passed' and e.value==1 for e in item.evaluations) for item in result.item_results) and
                any(e.name=='suite_passed' and e.value==1 for e in result.run_evaluations),
            'cases':outputs,'experiment_id':result.experiment_id,
            'url':result.experiment_url}


def run_experiment():
    """Run SDK/Docker work in a clean child; no hosted inference or ambient OTel."""
    import signal
    import subprocess
    keys={name:os.environ.get(name,'') for name in ('LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY')}
    if any(not v or len(v)>256 or not v.isascii() or any(c.isspace() for c in v) for v in keys.values()):
        raise ValueError('Configure local Langfuse project keys first; see docs/tracing.md')
    env={k:os.environ[k] for k in ('PATH','HOME','SYSTEMROOT','SSL_CERT_FILE','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG') if k in os.environ}
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
    # Keys travel on private stdin, not in argv, target containers or environment.
    child=subprocess.Popen([sys.executable,'-m','xp_agent.tracing.experiments'],
        env=env,cwd=str(Path(__file__).resolve().parents[2]),stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
    try:
        output,_=child.communicate(json.dumps(keys),timeout=900)
    except (KeyboardInterrupt,subprocess.TimeoutExpired) as exc:
        # Let the worker unwind DockerRunner.finally and SDK resources before a hard kill.
        if child.poll() is None:
            try: child.send_signal(signal.SIGINT)
            except ProcessLookupError: pass
        try: child.communicate(timeout=15)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            child.kill();child.communicate()
        if isinstance(exc,subprocess.TimeoutExpired): raise RuntimeError('Local experiment deadline exceeded') from None
        raise
    if child.returncode or len(output)>100_000:
        raise RuntimeError('Local experiment failed; check optional dependency, Docker, local service and keys')
    return json.loads(output)



def main():
    from contextlib import redirect_stdout,redirect_stderr
    try:
        keys=json.loads(sys.stdin.buffer.read(4096))
        with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
            from langfuse import Langfuse
            from opentelemetry.sdk.trace import TracerProvider
            from .exporter import local_exporter,local_httpx
            from opentelemetry.sdk.trace.export import SpanExporter,SpanExportResult
            delegate=local_exporter(keys)
            class Checked(SpanExporter):
                failed=False
                def export(self,spans):
                    status=delegate.export(spans)
                    self.failed |= status!=SpanExportResult.SUCCESS
                    return status
                def shutdown(self): delegate.shutdown()
            exporter=Checked()
            provider=TracerProvider(shutdown_on_exit=False)
            http=local_httpx()
            client=Langfuse(public_key=keys['LANGFUSE_PUBLIC_KEY'],secret_key=keys['LANGFUSE_SECRET_KEY'],
                base_url=BASE_URL,environment='local',tracer_provider=provider,span_exporter=exporter,
                httpx_client=http,timeout=3,sample_rate=1,should_export_span=lambda span:span.instrumentation_scope.name in {'xp-agent','langfuse-sdk'} and not span.events and not span.status.description)
            try:
                result=execute_experiment(client,provider)
                client.flush()
                if not provider.force_flush(timeout_millis=8000) or exporter.failed or http.failed: raise RuntimeError('Experiment not flushed')
            finally:
                provider.shutdown();http.close()
        print(json.dumps(result))
        return 0
    except Exception: return 1


if __name__=='__main__': sys.exit(main())
