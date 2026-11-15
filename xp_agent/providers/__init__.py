"""Select the model adapter for an explicitly configured provider."""
from ..policy import check_content
from .common import BackendError, validate_auth


def create_backend(provider='codex', model=None, auth='cli'):
    validate_auth(provider, auth)
    if model is not None:
        if not model.strip() or model.startswith('-'):
            raise BackendError('Invalid model name')
        check_content(model)
    if provider == 'codex':
        from .codex import CodexBackend
        return CodexBackend(model or 'gpt-6-luna', auth)
    if provider == 'claude':
        from .claude import ClaudeBackend
        return ClaudeBackend(model or 'haiku', auth)
    raise BackendError('Unsupported provider: choose codex or claude')
