"""Bounded, explicit file disclosure and phase-specific candidate validation."""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re


class PolicyError(ValueError):
    pass


def safe_path(name: str) -> str:
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or str(p) != name or
        any(x in {'..', '.', '.git', '.venv', 'profiles', 'node_modules', '__pycache__'}
            or x.startswith('.') for x in p.parts) or '\\' in name or
        p.suffix in {'.pem', '.key'} or any(x in p.name.lower() for x in ('credential', 'secret', 'auth.json'))):
        raise PolicyError(f'Forbidden path: {name}')
    return name


def check_content(content: str):
    if len(content.encode()) > 100_000 or '\x00' in content:
        raise PolicyError('Binary or oversized input')
    if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}', content):
        raise PolicyError('Possible secret detected; input withheld')


def discover(root: Path, paths: list[str]) -> dict[str, str]:
    """Open each component relative to a directory fd; never follow symlinks."""
    result = {}
    for name in paths:
        safe_path(name)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in PurePosixPath(name).parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            file_fd = os.open(PurePosixPath(name).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file_fd, 'rb') as f:
                import stat
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                    raise PolicyError('Only regular files are supported')
                data = f.read(100_001).decode('utf-8')
            check_content(data)
            result[name] = data
        except (OSError, UnicodeError) as exc:
            raise PolicyError(f'Cannot safely read {name}') from exc
        finally:
            os.close(fd)
    if sum(len(v.encode()) for v in result.values()) > 400_000:
        raise PolicyError('Read scope exceeds 400KB; select fewer files')
    return result


def digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def validate_edits(phase, files, edits, source_paths, test_paths):
    allowed = set(test_paths if phase == 'red' else source_paths)
    if phase not in {'red', 'green', 'refactor'}:
        raise PolicyError('Unknown phase')
    if phase != 'refactor' and not edits:
        raise PolicyError('This phase requires a change')
    for name, content in edits.items():
        safe_path(name)
        if name not in allowed or not name.endswith('.py'):
            raise PolicyError(f'{phase} may not edit {name}')
        check_content(content)
        try:
            tree = ast.parse(content)
            if phase == 'red':
                old = ast.parse(files.get(name, '')).body
                if [ast.dump(n) for n in tree.body[:len(old)]] != [ast.dump(n) for n in old]:
                    raise PolicyError('Red must preserve existing tests and setup')
                added = tree.body[len(old):]
                if not added or not all(isinstance(n, ast.FunctionDef) and n.name.startswith('test_')
                                        and not n.decorator_list and any(isinstance(x, ast.Assert) for x in ast.walk(n))
                                        for n in added):
                    raise PolicyError('Red must append undecorated assertion-based tests')
                names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
                if len(names) != len(set(names)):
                    raise PolicyError('Duplicate test/function names')
        except SyntaxError as exc:
            raise PolicyError('Candidate has invalid Python syntax') from exc
    return {**files, **edits}
