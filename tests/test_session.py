import json
import pytest
from xp_agent import session
from xp_agent.project import git
from xp_agent.policy import PolicyError


def project(tmp_path):
    root = tmp_path / 'app'
    root.mkdir()
    (root / 'calc.py').write_text('def double(x):\n    return x\n')
    (root / 'test_calc.py').write_text('from calc import double\ndef test_zero():\n    assert double(0) == 0\n')
    (root / 'helper.py').write_text('VALUE = 1\n')
    (root / '.env').write_text('private')
    git(root, 'init', '--template=', '-b', 'main')
    git(root, 'add', 'calc.py', 'test_calc.py', 'helper.py')
    git(root, 'commit', '-m', 'fixture')
    return root


class Planner:
    provider, model, auth = 'codex', 'fixture', 'cli'
    def select(self, context, timeout):
        if 'calc.py' not in context['files']:
            return {'read_paths': ['calc.py', 'test_calc.py'], 'source_paths': [], 'test_paths': [], 'increments': [], 'blocked': ''}
        return {'read_paths': [], 'source_paths': ['calc.py'], 'test_paths': ['test_calc.py'],
                'increments': [{'task': 'Double two', 'acceptance': ['double(2) == 4']}], 'blocked': ''}
    def propose(self, *args):
        return {'edits': [], 'rationale': 'Simple', 'blocked': '', 'acceptance': ['double(2) == 4'], 'tradeoffs': ['Keep API']}


def test_discovery_infers_scope_and_includes_runtime_dependencies(tmp_path):
    root = project(tmp_path)
    plan = session.prepare(root, 'Double inputs', Planner(), image='fixture')
    assert plan['source_paths'] == ['calc.py']
    assert 'helper.py' in plan['files']
    assert '.env' not in plan['files']
    assert plan['increments'][0]['task'] == 'Double two'
    assert plan['workspace_kind'] == 'worktree'


def test_worktree_branch_belongs_to_original_repository_and_preserves_main(tmp_path):
    root = project(tmp_path)
    plan = session.prepare(root, 'Double inputs', Planner(), image='fixture')
    workspace = session.create_workspace(plan, tmp_path / 'run')
    assert git(workspace, 'rev-parse', '--git-common-dir').strip() != '.git'
    assert git(workspace, 'branch', '--show-current').strip().startswith('xp/')
    assert git(root, 'branch', '--show-current').strip() == 'main'
    assert (root / 'calc.py').read_text() == plan['files']['calc.py']


def test_dirty_project_is_not_stashed_or_reset(tmp_path):
    root = project(tmp_path)
    (root / 'calc.py').write_text('# human work\n')
    with pytest.raises(PolicyError, match='uncommitted'):
        session.prepare(root, 'Double inputs', Planner(), image='fixture')
    assert (root / 'calc.py').read_text() == '# human work\n'


def test_resume_refuses_a_switched_worktree_branch(tmp_path):
    root=project(tmp_path)
    plan=session.prepare(root,'Double inputs',Planner(),image='fixture',progress=lambda m:None)
    saved=session.start(plan,tmp_path/'run')
    git(saved/'workspace','switch','-c','unapproved-branch')
    with pytest.raises(PolicyError,match='branch changed'):
        session.load_session(saved)


def test_resume_refuses_out_of_scope_staged_file(tmp_path):
    root=project(tmp_path)
    # Excluded from safe runtime capture, but still present in a linked checkout.
    git(root,'add','-f','.env'); git(root,'commit','-m','Synthetic excluded fixture')
    plan=session.prepare(root,'Double inputs',Planner(),image='fixture',progress=lambda m:None)
    saved=session.start(plan,tmp_path/'run')
    (saved/'workspace'/'.env').write_text('different synthetic private content')
    git(saved/'workspace','add','-f','.env')
    with pytest.raises(PolicyError,match='scope'):
        session.load_session(saved)


def test_verified_session_refuses_a_changed_revision(tmp_path):
    root=project(tmp_path)
    plan=session.prepare(root,'Double inputs',Planner(),image='fixture',progress=lambda m:None)
    saved=session.start(plan,tmp_path/'run')
    record=session.load_session(saved)
    record['status']='verified'
    session.save_session(saved,record)
    git(saved/'workspace','commit','--allow-empty','-m','External history change')
    with pytest.raises(PolicyError,match='revision changed'):
        session.load_session(saved)


def test_private_git_attributes_cannot_bypass_checkout_filter_gate(tmp_path):
    root=project(tmp_path)
    (root/'.git'/'info').mkdir(exist_ok=True)
    (root/'.git'/'info'/'attributes').write_text('*.py filter=external\n')
    with pytest.raises(PolicyError,match='attributes'):
        session.prepare(root,'Double inputs',Planner(),image='fixture',progress=lambda m:None)
