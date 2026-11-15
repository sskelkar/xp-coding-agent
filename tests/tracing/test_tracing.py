import json
import pytest
from xp_agent import tracing


def test_trace_is_bounded_hierarchical_and_metadata_only(tmp_path):
    with tracing.operation('xp.execute', enabled=True, directory=tmp_path, export=False) as trace:
        with tracing.observation('model.propose',
                                 'generation',
                                 model='fixture-model',
                                 phase='red',
                                 task='private task',
                                 files={'secret.py': 'private source'},
                                 api_key='private key'):
            tracing.annotate(passed=1, reason='private exception')
    payload = json.loads(next(tmp_path.glob('trace-*.json')).read_text())
    text = json.dumps(payload)
    assert 'private' not in text and 'secret.py' not in text
    assert len(payload['records']) == 2
    assert payload['records'][1]['parent'] == payload['records'][0]['id']
    assert payload['records'][1]['attributes']['phase'] == 'red'
    assert payload['session_id'] == trace.session_id


def test_disabled_tracing_never_exports_or_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tracing, 'export_trace', lambda *a: pytest.fail('unexpected export'))
    with tracing.operation('xp.execute', enabled=False, directory=tmp_path):
        with tracing.observation('run-tests', 'tool'):
            pass
    assert not list(tmp_path.iterdir())


def test_export_failure_does_not_replace_domain_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(tracing, 'export_trace', lambda *a:
                        (_ for _ in ()).throw(RuntimeError('private diagnostic')))
    output = []
    with pytest.raises(ValueError, match='domain failure'):
        with tracing.operation('xp.execute', enabled=True, directory=tmp_path, write=output.append):
            raise ValueError('domain failure')
    assert any('not exported' in line for line in output)
    assert all('private diagnostic' not in line for line in output)
    assert next(tmp_path.glob('trace-*.json')).exists()


def test_export_rejects_raw_record_fields():
    from xp_agent.tracing.exporter import validate
    value = tracing.Recorder().snapshot()
    value['raw'] = 'private source'
    with pytest.raises(ValueError):
        validate(value)


def test_sdk_export_preserves_hierarchy_without_inputs_or_outputs(tmp_path):
    pytest.importorskip('langfuse')
    import httpx
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from xp_agent.tracing.exporter import send

    class Memory(SpanExporter):
        spans = []

        def export(self, spans):
            self.spans.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

    requests = []

    def respond(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200,
                                  json={
                                      'data': [{
                                          'id': 'fixture-project',
                                          'name': 'Fixture',
                                          'organization': {
                                              'id': 'fixture-org',
                                              'name': 'Fixture'
                                          },
                                          'metadata': {}
                                      }]
                                  })
        return httpx.Response(200, json={'successes': [], 'errors': []})

    with tracing.operation('xp.execute', enabled=True, directory=tmp_path,
                           export=False) as recording:
        with tracing.observation('model.propose',
                                 'generation',
                                 model='fixture-model',
                                 usage_known=False):
            pass
    memory = Memory()
    url = send(recording.snapshot(), {
        'LANGFUSE_PUBLIC_KEY': 'pk-lf-fixture-' + recording.trace_id,
        'LANGFUSE_SECRET_KEY': 'sk-lf-fixture'
    },
               exporter=memory,
               httpx_client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert url == tracing.BASE_URL + '/project/fixture-project/traces/' + recording.trace_id
    assert len(memory.spans) == 2
    root = next(s for s in memory.spans if s.name == 'xp.execute')
    child = next(s for s in memory.spans if s.name == 'model.propose')
    assert child.parent.span_id == root.context.span_id
    assert root.attributes['session.id'] == recording.session_id
    assert child.attributes['langfuse.observation.type'] == 'generation'
    assert all('langfuse.observation.input' not in s.attributes
               and 'langfuse.observation.output' not in s.attributes for s in memory.spans)
    assert root.start_time <= child.start_time <= child.end_time <= root.end_time


def test_trace_caps_records_and_marks_scores_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(tracing, 'MAX_RECORDS', 2)
    with tracing.operation('xp.execute', enabled=True, directory=tmp_path, export=False):
        with tracing.observation('model.propose', 'generation'):
            with tracing.observation('run-tests', 'tool'):
                pass
        tracing.set_scores({'tdd_sequence': 'complete'})
    value = json.loads(next(tmp_path.glob('trace-*.json')).read_text())
    assert len(value['records']) == 2 and value['dropped'] == 1
    assert value['scores']['evidence_complete'] is False
    assert value['scores']['tdd_sequence'] == 'insufficient_evidence'


def test_export_child_receives_no_ambient_credentials_or_proxies(monkeypatch):
    from xp_agent.tracing import exporter
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'pk-lf-fixture')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', 'sk-lf-fixture')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private')
    monkeypatch.setenv('HTTPS_PROXY', 'https://private.invalid')
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'https://private.invalid')

    def launch(args, **kwargs):
        assert not any(
            k.startswith(('LANGFUSE', 'ANTHROPIC', 'OTEL')) or 'PROXY' in k for k in kwargs['env'])
        assert 'private' not in json.dumps(args)
        assert kwargs['timeout'] == 20
        assert json.loads(kwargs['input'])['keys']['LANGFUSE_PUBLIC_KEY'] == 'pk-lf-fixture'

        class Child:
            returncode = 0
            stdout = '{"exported":true}'

        return Child()

    monkeypatch.setattr(exporter.subprocess, 'run', launch)
    assert exporter.export(tracing.Recorder().snapshot())['exported'] is True


def test_local_http_transport_refuses_cloud_and_redirect_destinations():
    pytest.importorskip('langfuse')
    import httpx
    from xp_agent.tracing.exporter import local_httpx
    client = local_httpx()
    try:
        with pytest.raises(ValueError, match='destination'):
            client.get('https://cloud.langfuse.com/api/public/projects')
        with pytest.raises(ValueError, match='destination'):
            client.get(tracing.BASE_URL + '/unapproved')
    finally:
        client.close()


def test_reported_usage_is_validated_and_missing_usage_stays_unknown(tmp_path):
    with tracing.operation('xp.execute', enabled=True, directory=tmp_path,
                           export=False) as recorder:
        with tracing.observation('model.propose', 'generation', usage_known=False):
            tracing.report_usage({
                'input_tokens': 12,
                'output_tokens': 4,
                'cached_input_tokens': 3,
                'secret': 'PRIVATE'
            })
        with tracing.observation('model.propose', 'generation', usage_known=False):
            tracing.report_usage({'input_tokens': 'PRIVATE', 'output_tokens': -1})
    first, second = recorder.records[1:]
    assert first['attributes']['usage_known'] is True
    assert first['attributes']['cache_read_tokens'] == 3
    assert second['attributes']['usage_known'] is False


def test_sdk_score_upload_failure_is_not_reported_as_success(tmp_path):
    pytest.importorskip('langfuse')
    import httpx
    import uuid
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from xp_agent.tracing.exporter import send, local_httpx

    class Memory(SpanExporter):

        def export(self, spans):
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

    with tracing.operation('xp.execute', enabled=True, directory=tmp_path,
                           export=False) as recorder:
        tracing.set_scores({'tdd_sequence': 'complete'})
    client = local_httpx(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={})))
    with pytest.raises(RuntimeError, match='score'):
        send(recorder.snapshot(), {
            'LANGFUSE_PUBLIC_KEY': 'pk-lf-fixture-' + uuid.uuid4().hex,
            'LANGFUSE_SECRET_KEY': 'sk-lf-fixture'
        },
             exporter=Memory(),
             httpx_client=client)


def test_exporter_strips_sdk_scope_credentials_before_transport():
    pytest.importorskip('langfuse')
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
    from xp_agent.tracing.exporter import strip_scope_attributes

    class Memory(SpanExporter):

        def __init__(self):
            self.spans = []

        def export(self, spans):
            self.spans.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

    memory = Memory()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(strip_scope_attributes(memory)))
    try:
        tracer = provider.get_tracer('langfuse-sdk',
                                     'fixture',
                                     attributes={
                                         'public_key': 'pk-lf-PRIVATE',
                                         'other': 'PRIVATE'
                                     })
        with tracer.start_as_current_span('experiment-item-task') as span:
            span.set_attribute('safe', 'fixture')
        provider.force_flush()
        actual = memory.spans[0]
        assert not actual.instrumentation_scope.attributes
        assert actual.instrumentation_scope.name == 'langfuse-sdk'
        assert actual.attributes['safe'] == 'fixture'
    finally:
        provider.shutdown()
