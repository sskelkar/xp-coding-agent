import json
from xp_agent.cli import main


def test_cli_help_lists_plan_run_and_evals(capsys):
    import pytest
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert all(name in output for name in ('plan', 'run', 'eval'))


def test_cli_rejects_unapproved_run_before_backend_or_workspace(tmp_path, capsys):
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps({'approval_id': 'not-approved'}))
    code = main(['run', str(path), '--approve', 'wrong', '--output', str(tmp_path / 'result')])
    assert code == 2
    assert not (tmp_path / 'result').exists()
