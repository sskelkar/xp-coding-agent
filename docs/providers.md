# Codex and Claude Code providers

XP Coding Agent ships with **two selectable adapters**, one for OpenAI Codex and one for Anthropic Claude Code. Both A and B use the same provider, model, and auth mode for a given session. A and B are roles within XP Coding Agent and have their own continuing histories. You can run different providers in separate sessions.

## Use either provider

Run one of these from the XP Coding Agent checkout. The path is the Python project the pair will work on.

**Codex**

```sh
command -v codex
codex login status
uv run --frozen xp-agent pair /path/to/project --provider codex --auth cli
```

Run `codex login` if there is no saved sign-in. Codex is the XP default and its default model ID is `gpt-6-luna`.

**Claude Code**

```sh
command -v claude
claude auth status
uv run --frozen xp-agent pair /path/to/project --provider claude --auth cli
```

Run `claude auth login` if there is no saved sign-in. The Claude default is `haiku`. In either command, use `--model` to pass an ID or alias the selected account can access, such as `--model sonnet` for Claude.

## Authentication modes

| Provider | `--auth` | Credential used |
| --- | --- | --- |
| Codex or Claude Code | `cli` | The selected CLI's saved credentials. This is the default. Billing and organization depend on that login. |
| Codex | `api-key` | `CODEX_API_KEY` in the launching shell. |
| Claude Code | `api-key` | `ANTHROPIC_API_KEY` in the launching shell. |
| Claude Code | `oauth-token` | `CLAUDE_CODE_OAUTH_TOKEN` in the launching shell. |

Set secrets through your shell or secret manager. Pass only the mode to XP Coding Agent. The manifest stores provider, model, and mode. On resume, XP reconstructs the same adapter and uses the credentials available in the current environment for that mode. Start a new session to switch provider, model, or auth mode. The controller stops on provider failure and retains the recorded session.

For a managed account, verify which organization the provider CLI is using before sending project context. The adapter preserves system proxy and certificate trust settings and, when set, forwards `CODEX_HOME` or `CLAUDE_CONFIG_DIR` to its corresponding CLI. Provider endpoint overrides and unrelated credential variables are excluded. [Security boundaries](security.md)

## How the adapters fit the pair

`Partner.reply()` sends a prompt, a JSON Schema, and a deadline to its selected adapter. The installed provider CLI runs in a temporary directory and returns a structured proposal. The partner validates it and the controller enforces phase policy, runs tests, and writes accepted files.

| Adapter | Request and response | Tool controls |
| --- | --- | --- |
| [Codex](../xp_agent/providers/codex.py) | `codex exec` with a schema file and a dedicated final-response file. | Requests the read-only sandbox, skips ordinary user config and rules, disables execution features, and rejects unexpected tool events. |
| [Claude Code](../xp_agent/providers/claude.py) | `claude --print` with a JSON schema and a structured result from stream JSON. | Supplies an empty tool list, disables hooks and ordinary settings sources, and requests strict empty MCP configuration. Claude's internal `StructuredOutput` event supplies the JSON response. API-key mode uses `--bare`. |

Both adapters start a fresh process per request. XP sends the relevant visible conversation from the checkpoint each time. Claude's tool restrictions depend on the CLI honoring its flags. Project tests cross a separate Docker boundary. [Source walkthrough](how-it-works.md) · [Security boundaries](security.md)

## Diagnose or qualify a provider

- If XP reports `No such file or directory: 'codex'` or `'claude'`, run `command -v` for that executable in the **same terminal** as XP. The subprocess uses that terminal's exported `PATH`. A different app or terminal may have its own environment.
- If the executable is present and invocation fails, check the saved login or selected credential mode, account and model access, quota, and whether the installed CLI supports the adapter flags. The terminal prints a generic error to keep provider diagnostics out of session records.
- Both adapters have deterministic tests for invocation, auth isolation, and response handling. To exercise a hosted model end to end, use `xp-agent eval --live --provider codex` or `xp-agent eval --live --provider claude` with an authorized account. These commands use a synthetic Money task and consume provider quota. The project records scripted acceptance and partial live Codex trials. A completed hosted Money result for either provider remains unverified. [Evaluation guide](pair-evaluations.md) · [Recorded validation](evaluation.md)
