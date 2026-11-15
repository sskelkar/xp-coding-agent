"""Shared authentication rules and transport errors for both providers."""

import os


class BackendError(ValueError):
    pass


def validate_auth(provider, auth):
    allowed = {'cli', 'api-key', 'oauth-token'} if provider == 'claude' else {'cli', 'api-key'}
    if auth not in allowed:
        raise BackendError('Unsupported authentication mode for provider')


def provider_environment(provider, auth):
    validate_auth(provider, auth)
    home_key = 'CODEX_HOME' if provider == 'codex' else 'CLAUDE_CONFIG_DIR'
    # System egress/trust is infrastructure, not a provider/base-URL override.
    transport = ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy',
                 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE')
    env = {
        k: os.environ[k]
        for k in ('PATH', 'HOME', 'USER', 'TMPDIR', home_key, *transport) if k in os.environ
    }
    if auth != 'cli':
        key = ('CLAUDE_CODE_OAUTH_TOKEN' if auth == 'oauth-token' else
               'CODEX_API_KEY' if provider == 'codex' else 'ANTHROPIC_API_KEY')
        if not os.environ.get(key, '').strip():
            raise BackendError(
                f'{key} is required for {provider} {auth} authentication; set it locally, never in a plan'
            )
        env[key] = os.environ[key]
    return env
