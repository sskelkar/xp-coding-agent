"""Claude Code transport; the model proposes JSON without project tools."""
import json
from pathlib import Path
import tempfile
from .backend import BackendError, SCHEMA, parse_reply, proposal_prompt, provider_environment
from .process import run


class ClaudeBackend:
    provider = 'claude'

    def __init__(self, model='haiku', status=None, auth='cli'):
        self.model, self.status, self.auth = model, status, auth

    def environment(self):
        env = provider_environment(self.provider, self.auth)
        env.update(CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
                   CLAUDE_CODE_DISABLE_CLAUDE_MDS='1', CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')
        return env

    def command(self, schema=None):
        argv = ['claude', '--print', '--model', self.model, '--output-format', 'stream-json', '--verbose',
                '--json-schema', json.dumps(schema or SCHEMA), '--tools', '', '--permission-mode', 'dontAsk',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--setting-sources', '', '--settings', json.dumps({'disableAllHooks': True, 'enabledPlugins': {},
                                                                  'autoMemoryEnabled': False}),
                '--disable-slash-commands', '--no-chrome', '--no-session-persistence',
                '--system-prompt', 'You are a bounded coding proposal generator. Follow the supplied XP contract.']
        # Bare mode deliberately excludes saved OAuth/keychain credentials.
        if self.auth == 'api-key':
            argv.append('--bare')
        return argv

    def propose(self, phase, context, timeout):
        return parse_reply(self.request(proposal_prompt(phase, context), SCHEMA, timeout))

    def select(self, context, timeout):
        from .session import SELECTION_SCHEMA, SELECTION_PROMPT
        return json.loads(self.request(SELECTION_PROMPT + '\n' + json.dumps(context), SELECTION_SCHEMA, timeout))

    def request(self, prompt, schema, timeout):
        env = self.environment()
        with tempfile.TemporaryDirectory(prefix='xp-claude-') as tmp:
            result = run(self.command(schema), cwd=Path(tmp), env=env, stdin=prompt,
                         timeout=min(timeout, 180), tick=self.status)
        if result.returncode:
            raise BackendError('Claude invocation failed; check authentication, quota, model access and CLI compatibility. No provider fallback was attempted.')
        final = None
        try:
            for line in result.stdout.splitlines():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('Invalid event')
                if event.get('type') == 'assistant':
                    for block in event.get('message', {}).get('content', []):
                        # Claude implements schema output with this internal, non-executing tool.
                        if block.get('type') == 'tool_use' and block.get('name') != 'StructuredOutput':
                            raise BackendError('Backend attempted tool use; proposal rejected')
                if event.get('type') == 'result':
                    if final is not None:
                        raise ValueError('Duplicate result')
                    final = event
            if not final or final.get('is_error') is not False or final.get('subtype') != 'success':
                raise ValueError('No successful result')
            from .tracing import report_usage
            report_usage(final.get('usage'))
            return json.dumps(final['structured_output'])
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            # Do not echo error strings from provider output into durable state.
            raise BackendError('Claude returned an invalid, unsafe or unsuccessful structured proposal') from exc
