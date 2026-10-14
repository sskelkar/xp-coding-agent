from pathlib import Path
import pytest
from xp_agent.policy import PolicyError, discover, validate_edits


def test_discovery_includes_guidance_but_not_secrets_or_symlinks(tmp_path):
    (tmp_path / 'README.md').write_text('Run pytest')
    (tmp_path / 'AGENTS.md').write_text('Use clear names')
    (tmp_path / '.env').write_text('SYNTHETIC_SECRET=example')
    (tmp_path / 'link.py').symlink_to('/etc/passwd')
    files = discover(tmp_path, ['README.md', 'AGENTS.md'])
    assert set(files) == {'README.md', 'AGENTS.md'}
    with pytest.raises(PolicyError):
        discover(tmp_path, ['link.py'])
    with pytest.raises(PolicyError):
        discover(tmp_path, ['.env'])


def test_red_cannot_change_production_and_green_cannot_change_tests():
    files = {'calc.py': 'x = 1\n', 'test_calc.py': 'def test_old():\n    assert True\n'}
    with pytest.raises(PolicyError):
        validate_edits('red', files, {'calc.py': 'x = 2\n'}, ['calc.py'], ['test_calc.py'])
    with pytest.raises(PolicyError):
        validate_edits('green', files, {'test_calc.py': 'def test_old():\n    pass\n'}, ['calc.py'], ['test_calc.py'])


def test_red_preserves_existing_test_ast_and_requires_new_assertion():
    old = 'def test_old():\n    assert 1 == 1\n'
    valid = old + '\ndef test_new():\n    assert 2 == 3\n'
    assert validate_edits('red', {'test_calc.py': old}, {'test_calc.py': valid}, [], ['test_calc.py'])
    with pytest.raises(PolicyError):
        validate_edits('red', {'test_calc.py': old}, {'test_calc.py': 'def test_old():\n    assert True\n'}, [], ['test_calc.py'])


@pytest.mark.parametrize('path', ['../escape.py', '/tmp/x.py', '.git/config', '.env', 'profiles/private.json'])
def test_forbidden_edit_paths(path):
    with pytest.raises(PolicyError):
        validate_edits('green', {}, {path: 'x'}, [path], [])


def test_known_secret_is_blocked_before_model_submission(tmp_path):
    (tmp_path / 'app.py').write_text('api_key = "sk-" + "x" * 40')
    # This is executable construction, not a literal secret: scanners cannot infer it.
    (tmp_path / 'config.txt').write_text('-----BEGIN PRIVATE KEY-----\nFAKE')
    with pytest.raises(PolicyError):
        discover(tmp_path, ['config.txt'])
