import pytest

from xp_agent.cli import main


def test_cli_help_shows_pairing_and_evaluation(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(['--help'])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert 'pair' in output and 'eval' in output
    assert '{pair,eval}' in output


@pytest.mark.parametrize('command', ('plan', 'run', 'repl'))
def test_removed_commands_do_not_start_a_session(command, monkeypatch, capsys):
    from xp_agent.pairing import cli as pair_cli

    monkeypatch.setattr(pair_cli, 'main', lambda *_: pytest.fail('Unexpected pairing session'))
    assert main([command]) == 2
    assert 'Pairing is the only coding workflow' in capsys.readouterr().err


def test_default_entry_point_starts_pairing(monkeypatch):
    from xp_agent.pairing import cli as pair_cli

    monkeypatch.setattr(pair_cli, 'main', lambda args: args)
    assert main(['--goal', 'Money']) == ['--goal', 'Money']
    assert main(['pair', '--goal', 'Money']) == ['--goal', 'Money']
