The primary interface is now the REPL: run `xp-coding-agent` in your project, then `/provider claude haiku cli` or `/provider claude sonnet oauth-token`. Preferences persist for new plans; approved sessions retain their original provider/model/auth mode. The batch examples below remain valid for automation.

# Provider configuration and switching

The agent has one proposal contract and two adapters: Codex CLI and Claude Code. Neither model drives the checkout directly. Both return the same JSON shape to the same XP gates, edit policy and Docker runner.

## Choose a provider and model

For Claude Haiku, using saved Claude login:

```sh
uv run xp-agent plan /absolute/path/to/your-project \
  --task 'Describe one small behavior change and its expected result' \
  --source your_module.py --tests tests/test_your_module.py \
  --provider claude --model haiku --auth cli \
  --output .xp-runs/claude-plan.json
```

Use `--model sonnet` for Sonnet. Use `--provider codex --model gpt-6-luna` for Codex. Omit `--model` to select the provider default: `gpt-6-luna` or `haiku`. Model availability depends on your account. Aliases such as `haiku` and `sonnet` can resolve differently as the provider updates them; supply a full model ID supported by your account when you need a specific version. The plan records the requested identifier, not an independently resolved version.

Review the generated Markdown, then execute:

```sh
uv run xp-agent run .xp-runs/claude-plan.json \
  --approve FULL_APPROVAL_ID \
  --output .xp-runs/claude-run
```

Provider, model and authentication mode are part of the approval hash. `run` cannot override them. Plans created before provider selection was added retain their original hashes and use Codex with saved CLI authentication. Batch plans use schema version 2; interactive session plans use version 3 with runtime/context scopes and increments.

## Authenticate outside the project

The plan stores authentication **mode**, never a key or token. The agent does not read credential files itself; the provider CLI manages saved login. Environment credentials are forwarded only when explicitly selected and never passed to test containers. Use the same terminal environment when planning and running.

### Codex

For ChatGPT-managed access, use `codex login`, then `codex login status`, and select `--auth cli`. Sign in to the account/workspace authorized for the project. `CODEX_HOME`, if set, selects the CLI's home/configuration directory.

For direct API billing, put a key in `CODEX_API_KEY` and select `--auth api-key`:

```sh
read -s CODEX_API_KEY
export CODEX_API_KEY
# Add --provider codex --auth api-key to your plan command.
```

Alternatively, Codex supports saving API-key authentication through `codex login --with-api-key` using stdin; that saved credential is then used by `--auth cli`. Our `cli` mode does not guarantee subscription billing—it delegates to the saved login. Merely setting `OPENAI_API_KEY` does not configure this adapter.

References: [OpenAI authentication](https://learn.chatgpt.com/docs/auth), [non-interactive API-key use](https://learn.chatgpt.com/docs/non-interactive-mode).

### Claude saved login, including enterprise

Run `claude auth login` and `claude auth status`. For your organization's SSO flow, use `claude auth login --sso`. Select `--provider claude --auth cli`. `CLAUDE_CONFIG_DIR`, if set, is forwarded to the CLI.

Choose your authorized organization during login. Account entitlement, selected organization and managed policy enforcement remain Claude Code's responsibilities. The agent does not certify that the current login belongs to a particular organization, and the plan does not bind the credential's identity. Check the active account before sending project context.

The adapter excludes ordinary user/project settings, disables project tools and hooks, and requests no session persistence. Managed settings may still constrain execution. Organizations requiring custom gateways, cloud-provider credentials or special environment settings need a separately validated adapter configuration; those are not supported by this version. Do not remove organizational controls to make a request work.

### Claude API key

Set `ANTHROPIC_API_KEY` through your secret manager or a hidden prompt, then select `--provider claude --auth api-key`:

```sh
read -s ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY
```

This is explicit API authentication, not a way to reuse subscription quota. The adapter uses Claude Code's bare mode for this path; bare mode does not read saved OAuth/keychain credentials.

### Claude subscription OAuth token

For token-based automation, obtain a token yourself with:

```sh
claude setup-token
```

Store the generated value securely. To enter it without putting it into shell history:

```sh
read -s CLAUDE_CODE_OAUTH_TOKEN
export CLAUDE_CODE_OAUTH_TOKEN
```

Select `--provider claude --auth oauth-token`. This mode remains separate from API-key authentication. The adapter does not use bare mode here because that would exclude OAuth credentials. Tokens still depend on the associated account's entitlement and usage limits.

Reference: [Claude authentication and credential precedence](https://code.claude.com/docs/en/authentication). Do not paste the token or key into a coding chat. This project does not load `.env` files or require a secrets configuration file. Remove environment secrets with `unset VARIABLE_NAME` after use.

## When one provider runs out of quota

A provider error stops the run and preserves accepted work through the workflow's normal failure path. It does not automatically retry with another provider, change models, or send code to a second service.

To switch, create a **new plan** with the other provider and an authorized authentication mode, review it and run it into a new output directory. Preserve the previous run's report and patch. If useful accepted work is green, review/integrate it and run your project checks before planning the remaining change. An accepted red test by itself is intentionally failing and cannot serve as this version's required passing baseline.

There is no mid-run provider change. `/resume` continues an interactive session with its approved provider and remaining budgets; switching requires a new plan. Switching avoids dependence on one provider for subsequent runs, but cannot guarantee uninterrupted execution or quota at the second provider. The CLI works independently of the desktop conversation: you can invoke these commands directly from a terminal even when this chat's allowance is unavailable.

## Implementation

`ProposalBackend` in [backend.py](../xp_agent/backend.py) is a Python `Protocol`: an interface described by attributes (`provider`, `model`, `auth`) and `propose(phase, context, timeout)` plus `select(context, timeout)` for bounded interactive discovery. Implementations need not inherit from it; matching its shape is enough. The graph accepts any compatible object, including deterministic test doubles.

`create_backend()` chooses `CodexBackend` or `ClaudeBackend`. Interactive planning/session execution and live REPL evals call this factory; execution reconstructs the adapter from the approved plan. The graph remains provider-independent. Both adapters share the XP prompt, bounded context selection, JSON schema and response validation. Each request starts a fresh CLI process in a temporary directory.

The adapters handle different transport details:

| Detail | Codex | Claude |
|---|---|---|
| Invocation | `codex exec` | `claude --print` |
| Structured response | Schema file and final JSON output file | JSON schema flag and `structured_output` in result events |
| Tool restrictions | Read-only sandbox and disabled features; execution events rejected | Empty built-in tool list, empty strict MCP configuration, disabled skills/hooks; unexpected tool-use events rejected |
| Schema mechanism | Final response file | Internal `StructuredOutput` event allowed solely for schema output |
| Auth | Saved CLI credentials or `CODEX_API_KEY` | Saved CLI credentials, `ANTHROPIC_API_KEY`, or `CLAUDE_CODE_OAUTH_TOKEN` |
| Request bound | 180 seconds or remaining workflow time | Same |

Claude's tools-disabled mode is not an OS sandbox equivalent to Codex's read-only sandbox. The trusted host CLI can still access its own login/configuration. Both adapters rely on their installed CLIs honoring the supplied options. Raw provider diagnostics/events are not written to agent run records; failures use a generic actionable message to avoid persisting credentials. Provider CLIs may keep their own diagnostics outside this project's output directory.

No new provider SDK dependency is needed. A future direct API adapter can implement the same contract, but would need its own authentication, cancellation, structured-output and disclosure tests. A common application interface is useful even though the underlying provider APIs and login mechanisms differ.

Claude flags were checked against installed Claude Code 2.1.150 and the [CLI reference](https://code.claude.com/docs/en/cli-reference); output handling follows [programmatic use](https://code.claude.com/docs/en/headless). Unsupported flags on an older CLI cause failure, not a retry with weaker restrictions.

## Validate your configuration

```sh
# Deterministic tests, no provider credentials needed
uv run pytest

# Real containers and scripted adversarial evals, still no model request
XP_DOCKER_TESTS=1 uv run pytest

# Synthetic fixture only; makes real requests using your selected account
uv run xp-agent eval --live --provider claude --model haiku --auth oauth-token \
  --output eval-results/claude-haiku.json
```

Replace `--auth oauth-token` with your configured mode. Choose `--provider codex --model gpt-6-luna --auth cli` for Codex. Live evals report the selected provider, model and auth mode, without credential values. A successful smoke eval establishes that one synthetic XP cycle worked; it does not qualify a corporate account, guarantee coding quality or test every authentication mode.
