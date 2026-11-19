# hermes-aipg-provider

A [Hermes Agent](https://hermes-agent.nousresearch.com) model-provider plugin for the
[AI Power Grid](https://aipowergrid.io), an OpenAI-compatible inference API whose open models are served
by independent GPU operators.

Community-written and unofficial. The author is a user of the grid, not part of the AIPG team.

## Install

```bash
hermes plugins install speteai/hermes-aipg-provider
hermes plugins enable aipg-community
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

## Video (optional second plugin)

The folder `video/` is a separate plugin, `aipg-video`. It registers the grid as a backend for
Hermes's `video_generate` tool: clips of 2 to 10 seconds with sound, from a text prompt or from a
local start picture.

```bash
hermes plugins install speteai/hermes-aipg-provider#video
hermes plugins enable aipg-video
hermes config set video_gen.provider aipg
```

It uses the same `AIPG_API_KEY`. The model list comes live from the grid; with no model configured
the first video model that is online is used.

| Option of `video_generate` | On the grid |
| --- | --- |
| `duration` | 2, 3, 5, 8 or 10 seconds; another value is rounded down to the next of these; default 3 |
| `aspect_ratio` | `16:9` (960x544), `9:16` (544x960), `1:1` (704x704) |
| `resolution` | `480p` gives 768x448 in 16:9; everything else is the size above |
| `image_url` | a local image file. A web link is refused with a message, nothing is sent |

Cost and waiting:

- A clip is billed per second of video. Before sending, the plugin reads the grid's public price
  list and sets that price as the most the clip may cost; without a published price nothing is sent.
  In the test a 2-second clip cost $0.0408 and took about 28 seconds.
- A started clip cannot be cancelled. The tool call waits up to 10 minutes. If the clip is not
  ready by then, the tool reports the job id; the clip may still complete and be billed, and this
  plugin does not fetch it later.
- The result is saved in Hermes's cache folder (`cache/generated/videos/`) and the result names
  the cost and the job id.

## Tested

On 2026-11-15, Hermes Agent v0.23.1 on Linux x64, against the live grid:

- `hermes plugins validate .` passes.
- `hermes plugins install speteai/hermes-aipg-provider` plus `enable`, then a tool-using prompt through the
  installed plugin, with the key in `.env` and with the key as an environment variable.
- With `provider: "aipg"` and `qwen38-flash-next-nvfp4`, the agent wrote a Python script, ran it and
  wrote the result to a file (27 s, 4 model calls, about 52,000 tokens).

Not tested: Windows, macOS, the desktop app, long sessions.

Video plugin, on 2026-11-19, Hermes Agent at commit dfa38d1 (Python 3.14, Linux x64), against the
live grid with `LTX-2.5 Distilled BF16`:

- `hermes plugins validate video` passes.
- `hermes plugins install speteai/hermes-aipg-provider#video` plus `enable` in a fresh Hermes home; the
  tool then resolves the `aipg` backend.
- Through the handler of the `video_generate` tool, with the plugin enabled and
  `video_gen.provider: aipg`: a 2-second clip from text and one from a local picture, both saved
  as MP4; an empty prompt and a web link as start picture are refused without a request.

Not tested for video: a full agent conversation that calls the tool, delivery of the clip through
a chat platform, the 10-minute timeout, clips longer than 2 seconds through this plugin.

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
  Hermes with the API key you provide. The video plugin calls the same API itself (model status,
  price list, video jobs) and downloads the finished clip only from the grid's own storage
  (`*.aipg.art`, `*.aipowergrid.io`).
- Your prompts, tool definitions and tool results are sent to that API and processed in plain text on
  computers run by independent operators. Do not use it for confidential material without thinking
  about that.
- Usage is billed per token, and video per second of clip, from a prepaid balance of your grid
  account. The plugins make no payments.
- The API key is resolved through Hermes's own provider-credential route (`AIPG_API_KEY`,
  optional `AIPG_BASE_URL`). The provider plugin reads no files and stores nothing. The video plugin
  reads the key through Hermes's secret scope and writes only the clip into Hermes's cache.
- No telemetry, no background processes, no self-updating code, no core overrides. It registers through
  the public `register_provider()` / `ProviderProfile` API only.

## Why standalone

Hermes's contribution policy asks for third-party integrations to ship as plugins rather than in the
core tree (see
[CONTRIBUTING.md](https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md#third-party-product-integrations-ship-as-a-standalone-plugin)).

## License

MIT
