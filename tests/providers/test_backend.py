import json
import pytest
from xp_agent.providers.codex import CodexBackend
from xp_agent.providers.common import BackendError
from xp_agent.pairing.partners import SCHEMA, parse_reply


def test_codex_configuration_is_read_only_and_disables_execution_tools(tmp_path):
    argv = CodexBackend('example-model').command(tmp_path)
    assert argv[argv.index('--sandbox') + 1] == 'read-only'
    assert '--ignore-user-config' in argv and '--ignore-rules' in argv
    for feature in ('shell_tool', 'apps', 'plugins', 'hooks', 'view_image'):
        assert feature in argv
    assert '--dangerously-bypass-approvals-and-sandbox' not in argv


def test_factory_selects_provider_defaults_and_rejects_unknown_provider():
    from xp_agent.providers import create_backend
    assert create_backend().model == 'gpt-6-luna'
    claude = create_backend('claude')
    assert (claude.provider, claude.model, claude.auth) == ('claude', 'haiku', 'cli')
    assert create_backend('claude', 'sonnet', 'api-key').model == 'sonnet'
    with pytest.raises(BackendError):
        create_backend('unknown')


def test_auth_environment_is_explicit_and_provider_specific(monkeypatch):
    from xp_agent.providers import create_backend
    monkeypatch.setenv('CODEX_API_KEY', 'synthetic-codex-value')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-anthropic-value')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://unapproved.invalid')
    for provider, key in [('codex', 'CODEX_API_KEY'), ('claude', 'ANTHROPIC_API_KEY')]:
        login_env = create_backend(provider).environment()
        assert not {'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL'} & login_env.keys()
        env = create_backend(provider, auth='api-key').environment()
        assert env[key].startswith('synthetic-')
        assert len({'CODEX_API_KEY', 'ANTHROPIC_API_KEY'} & env.keys()) == 1
        monkeypatch.delenv(key)
        with pytest.raises(BackendError, match=key):
            create_backend(provider, auth='api-key').environment()


def test_claude_request_uses_schema_and_disables_project_tools(monkeypatch):
    from xp_agent.providers import create_backend
    from xp_agent.providers import claude as claude_backend
    from xp_agent.process import Result
    reply = {'action': 'comment', 'message': 'No cleanup needed', 'edits': [], 'examples': []}

    def fake_run(argv, **kwargs):
        assert argv[argv.index('--tools') + 1] == ''
        assert '--strict-mcp-config' in argv
        assert '--no-session-persistence' in argv
        assert argv[argv.index('--setting-sources') + 1] == ''
        assert '--disable-slash-commands' in argv
        assert '--dangerously-skip-permissions' not in argv
        assert '--bare' not in argv  # saved login must remain usable
        assert json.loads(argv[argv.index('--json-schema') + 1]) == SCHEMA
        assert kwargs['stdin'] == 'proposal'
        assert kwargs['timeout'] == 180
        return Result(
            0,
            json.dumps({
                'type': 'result',
                'subtype': 'success',
                'is_error': False,
                'structured_output': reply
            }))

    monkeypatch.setattr(claude_backend, 'run', fake_run)
    assert parse_reply(create_backend('claude').request('proposal', SCHEMA, 600)) == reply


@pytest.mark.parametrize('output', [
    {
        'type': 'result',
        'subtype': 'error_max_turns',
        'is_error': True
    },
    {
        'type': 'result',
        'subtype': 'success',
        'is_error': False,
        'structured_output': {
            'bad': 'schema'
        }
    },
    {
        'type': 'assistant',
        'message': {
            'content': [{
                'type': 'tool_use',
                'name': 'Bash'
            }]
        }
    },
])
def test_claude_rejects_failure_malformed_output_and_tool_use(output, monkeypatch):
    from xp_agent.providers import create_backend
    from xp_agent.providers import claude as claude_backend
    from xp_agent.process import Result
    monkeypatch.setattr(claude_backend, 'run', lambda *a, **k: Result(0, json.dumps(output)))
    with pytest.raises(ValueError):
        parse_reply(create_backend('claude').request('proposal', SCHEMA, 30))


def test_provider_failures_do_not_leak_raw_credentials(monkeypatch):
    from xp_agent.providers import create_backend
    from xp_agent.providers import codex as backend, claude as claude_backend
    from xp_agent.process import Result
    diagnostic = 'synthetic-private-value-from-provider'
    for module, provider in [(backend, 'codex'), (claude_backend, 'claude')]:
        monkeypatch.setattr(module, 'run', lambda *a, **k: Result(1, diagnostic))
        with pytest.raises(BackendError) as error:
            create_backend(provider).request('proposal', SCHEMA, 30)
        assert diagnostic not in str(error.value)


def test_claude_oauth_token_is_an_explicit_auth_choice(monkeypatch):
    from xp_agent.providers import create_backend
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'synthetic-oauth-token')
    assert 'CLAUDE_CODE_OAUTH_TOKEN' not in create_backend('claude').environment()
    adapter = create_backend('claude', auth='oauth-token')
    assert adapter.environment()['CLAUDE_CODE_OAUTH_TOKEN'] == 'synthetic-oauth-token'
    assert '--bare' not in adapter.command(SCHEMA)
    with pytest.raises(BackendError):
        create_backend('codex', auth='oauth-token')


@pytest.mark.parametrize('tool_name, accepted', [('StructuredOutput', True), ('Bash', False),
                                                 ('Read', False)])
def test_claude_tool_events_cannot_be_hidden_by_successful_final_result(
        tool_name, accepted, monkeypatch):
    from xp_agent.providers import create_backend
    from xp_agent.providers import claude as claude_backend
    from xp_agent.process import Result
    reply = {
        'action': 'comment',
        'message': 'Consider the next behavior',
        'edits': [],
        'examples': []
    }
    events = [{
        'type': 'assistant',
        'message': {
            'content': [{
                'type': 'tool_use',
                'name': tool_name
            }]
        }
    }, {
        'type': 'result',
        'subtype': 'success',
        'is_error': False,
        'structured_output': reply
    }]
    monkeypatch.setattr(claude_backend, 'run',
                        lambda *a, **k: Result(0, '\n'.join(map(json.dumps, events))))
    if accepted:
        assert parse_reply(create_backend('claude').request('proposal', SCHEMA, 30)) == reply
    else:
        with pytest.raises(BackendError):
            create_backend('claude').request('proposal', SCHEMA, 30)


@pytest.mark.parametrize('event', [[], {'item': []}, {'item': None}])
def test_codex_malformed_events_fail_as_backend_errors(event, tmp_path, monkeypatch):
    from xp_agent.providers import codex as backend
    from xp_agent.process import Result
    monkeypatch.setattr(backend, 'run', lambda *a, **k: Result(0, json.dumps(event)))
    with pytest.raises(BackendError):
        CodexBackend().request('proposal', SCHEMA, 30)


def test_transport_preserves_system_proxy_and_ca_without_inheriting_provider_overrides(monkeypatch):
    from xp_agent.providers import create_backend
    monkeypatch.setenv('HTTPS_PROXY', 'http://system-proxy.invalid:8080')
    monkeypatch.setenv('SSL_CERT_FILE', '/tmp/system-ca.pem')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://unapproved.invalid')
    env = create_backend().environment()
    assert env['HTTPS_PROXY'] == 'http://system-proxy.invalid:8080'
    assert env['SSL_CERT_FILE'] == '/tmp/system-ca.pem'
    assert 'ANTHROPIC_BASE_URL' not in env
