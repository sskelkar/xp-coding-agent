import json
import pytest
from xp_agent.backend import CodexBackend, BackendError, parse_reply


def test_backend_accepts_only_bounded_structured_edits():
    reply = {'edits': [{'path': 'calc.py', 'content': 'x=1'}], 'rationale': 'Simple', 'blocked': '', 'acceptance': [], 'tradeoffs': []}
    assert parse_reply(json.dumps(reply)) == reply
    with pytest.raises(BackendError):
        parse_reply('not json')
    with pytest.raises(BackendError):
        parse_reply(json.dumps({**reply, 'edits': [{'path': '../oops', 'content': 'x'}]}))


def test_codex_configuration_is_read_only_and_disables_execution_tools(tmp_path):
    argv = CodexBackend('example-model').command(tmp_path)
    assert argv[argv.index('--sandbox') + 1] == 'read-only'
    assert '--ignore-user-config' in argv and '--ignore-rules' in argv
    for feature in ('shell_tool', 'apps', 'plugins', 'hooks', 'view_image'):
        assert feature in argv
    assert '--dangerously-bypass-approvals-and-sandbox' not in argv
