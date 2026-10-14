import json
import pytest
from xp_agent.project import create_plan, verify_approval, make_workspace, write_json
from xp_agent.policy import PolicyError

class Planner:
    model = 'fixture'
    def propose(self, phase, context, timeout):
        return {'edits': [], 'rationale': 'One small behavior', 'blocked': '',
                'acceptance': ['double(2) == 4'], 'tradeoffs': ['Keep existing API; defer generalization']}


def test_plan_binds_code_scope_model_and_acceptance(tmp_path):
    (tmp_path / 'calc.py').write_text('x = 1\n')
    (tmp_path / 'test_calc.py').write_text('def test_x():\n    assert True\n')
    (tmp_path / 'AGENTS.md').write_text('Use explicit names')
    plan = create_plan(tmp_path, 'Double', ['calc.py'], ['test_calc.py'], Planner())
    assert 'AGENTS.md' in plan['files']
    verify_approval(plan, plan['approval_id'])
    modified = json.loads(json.dumps(plan))
    modified['source_paths'].append('other.py')
    with pytest.raises(PolicyError):
        verify_approval(modified, plan['approval_id'])
    (tmp_path / 'calc.py').write_text('x = 2\n')
    with pytest.raises(PolicyError, match='changed'):
        verify_approval(plan, plan['approval_id'])


def test_workspace_is_separate_git_branch_and_original_is_untouched(tmp_path):
    original = tmp_path / 'original'
    original.mkdir()
    (original / 'calc.py').write_text('x = 1\n')
    files = {'calc.py': 'x = 1\n'}
    root = make_workspace(tmp_path / 'run', files)
    assert (root / '.git').is_dir()
    (root / 'calc.py').write_text('x = 2\n')
    assert (original / 'calc.py').read_text() == 'x = 1\n'


def test_atomic_records_are_private(tmp_path):
    path = tmp_path / 'record.json'
    write_json(path, {'status': 'running'})
    assert json.loads(path.read_text())['status'] == 'running'
    assert path.stat().st_mode & 0o077 == 0
