# hermes-aipg-provider

A [Hermes Agent](https://hermes-agent.nousresearch.com) model-provider plugin for the
[AI Power Grid](https://aipowergrid.io), an OpenAI-compatible inference API whose open models are served
by independent GPU operators.

Community-written and unofficial. The author is a user of the grid, not part of the AIPG team.

## Install

```bash
hermes plugins install speteai/hermes-aipg-provider
```

Or by hand: put `__init__.py` and `plugin.yaml` into `$HERMES_HOME/plugins/model-providers/aipg/`.

Then set your Grid API key in `~/.hermes/.env`:

```
AIPG_API_KEY=your-key-here
```

and select the provider, for example in `~/.hermes/config.yaml`:

```yaml
model:
  default: "qwen38-flash-next-nvfp4"
  provider: "aipg"
```

## What it adds

- An `aipg` provider (aliases `ai-power-grid`, `aipowergrid`) selectable with `hermes model`,
  `--provider aipg`, or `/model <model-id> --provider aipg`.
- The model list comes live from the grid's `/v1/models` endpoint.
- `qwen38-flash-next-nvfp4` as the fallback and auxiliary model.

It is a plain provider profile: no tools, no hooks, no middleware.

## Tested

On 2026-11-15, Hermes Agent v0.23.1 on Linux x64, against the live grid:

- `hermes plugins validate .` passes.
- With `provider: "aipg"` and `qwen38-flash-next-nvfp4`, the agent wrote a Python script, ran it and
  wrote the result to a file (27 s, 4 model calls, about 52,000 tokens).

Not tested: Windows, macOS, the desktop app, long sessions.

## Known limits

- `gpt-oss-120b` is listed by the grid but does not work for agent runs at the moment: on multi-step
  tasks its tool call comes back inside the reasoning text, and the run ends without a reply
  ([aipg-documentation#70](https://github.com/AIPowerGrid/aipg-documentation/issues/70)). Use
  `qwen38-flash-next-nvfp4`.
- `grid/qwen3:8b` has an 8,192-token context, which is too small for Hermes.
- Hermes showed the cost of the test run as unknown. The grid's prices are at
  `https://api.aipowergrid.io/v1/pricing`; the account balance shows the real charge.

## Disclosure

- Network calls: only to `https://api.aipowergrid.io/v1` (inference and the `/models` list), made by
  Hermes with the API key you provide.
- Your prompts, tool definitions and tool results are sent to that API and processed in plain text on
  computers run by independent operators. Do not use it for confidential material without thinking
  about that.
- Usage is billed per token from a prepaid balance of your grid account. The plugin makes no payments.
- The API key is resolved through Hermes's own provider-credential route (`AIPG_API_KEY`,
  optional `AIPG_BASE_URL`). The plugin reads no files and stores nothing.
- No telemetry, no background processes, no self-updating code, no core overrides. It registers through
  the public `register_provider()` / `ProviderProfile` API only.

## Why standalone

Hermes's contribution policy asks for third-party integrations to ship as plugins rather than in the
core tree (see
[CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md#third-party-product-integrations-ship-as-a-standalone-plugin)).

## License

MIT
