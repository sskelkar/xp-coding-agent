"""Codex CLI transport for bounded model requests."""
import json
from pathlib import Path
import tempfile

from ..process import run
from .common import BackendError, provider_environment


class CodexBackend:
    provider = 'codex'

    def __init__(self, model='gpt-6-luna', auth='cli'):
        self.model = model
        self.auth = auth

    def environment(self):
        return provider_environment(self.provider, self.auth)

    def command(self, directory):
        argv = [
            'codex', 'exec', '--model', self.model, '--sandbox', 'read-only',
            '--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check',
            '--json', '--color', 'never', '--cd',
            str(directory), '--output-schema',
            str(directory / 'schema.json'), '--output-last-message',
            str(directory / 'reply.json'), '-c', 'approval_policy="never"', '-c',
            'web_search="disabled"', '-c', 'model_reasoning_effort="low"', '--enable',
            'skip_host_skill_discovery'
        ]
        for feature in ('shell_tool', 'unified_exec', 'apps', 'plugins', 'hooks', 'view_image',
                        'browser_use', 'computer_use', 'image_generation', 'workspace_dependencies',
                        'skill_search', 'multi_agent', 'shell_snapshot'):
            argv += ['--disable', feature]
        return argv + ['-']

    def request(self, prompt, schema, timeout):
        with tempfile.TemporaryDirectory(prefix='xp-model-') as tmp:
            directory = Path(tmp)
            (directory / 'schema.json').write_text(json.dumps(schema))
            env = self.environment()
            result = run(self.command(directory),
                         cwd=directory,
                         env=env,
                         stdin=prompt,
                         timeout=min(timeout, 180))
            # Provider diagnostics can contain credentials or source; never persist them.
            if result.returncode:
                raise BackendError(
                    'Codex invocation failed; check authentication, quota, model access and CLI compatibility. No provider fallback was attempted.'
                )
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict) or not isinstance(event.get('item', {}), dict):
                    raise BackendError('Codex returned a malformed event')
                if event.get('type') == 'turn.completed':
                    from ..tracing import report_usage
                    report_usage(event.get('usage'))
                item_type = event.get('item', {}).get('type', '')
                if item_type in {'command_execution', 'file_change', 'mcp_tool_call', 'web_search'}:
                    raise BackendError('Backend attempted tool use; proposal rejected')
            path = directory / 'reply.json'
            if not path.is_file():
                raise BackendError('Codex did not return a structured proposal')
            return path.read_text()
