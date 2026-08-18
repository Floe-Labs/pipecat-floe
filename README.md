# pipecat-floe

**Floe services for [Pipecat](https://github.com/pipecat-ai/pipecat).** Meter
every leg of a voice agent — LLM, STT, TTS — per call, on one Floe key, with
pre-call spend caps.

**BYOK-first.** Keep your own vendor key (e.g. OpenAI) and route the LLM and TTS
legs through Floe with `provider_key=...`: Floe meters the call and enforces your
spend caps, and bills only its service fee — your model bill stays with your
vendor. Prefer no vendor accounts? Drop `provider_key` and go **keyless** — Floe
manages the provider keys for you. Streaming STT is keyless today (Floe-managed
Deepgram). Either way: one Floe key, one ledger, one budget.

Three drop-in Pipecat services:

- **`FloeLLMService`** — OpenAI-compatible LLM routed through Floe.
- **`FloeTTSService`** — OpenAI-compatible text-to-speech routed through Floe.
- **`FloeSTTService`** — streaming speech-to-text over Floe's WebSocket.

*Built and maintained by [Floe Labs](https://floelabs.xyz) — the company behind
Floe, the service these adapters route to.*

<!-- TODO: 30-60s demo video -->

> Community integration. Tested with `pipecat-ai` 1.7.0 (Python 3.11+).

## Install

```bash
pip install pipecat-floe
```

This pulls in `pipecat-ai`, `websockets`, `httpx`, and `loguru`. For the
example bot you also want a transport + VAD:

```bash
pip install "pipecat-ai[silero,websocket]"
```

## Pipecat version compatibility

Built and verified against **`pipecat-ai` 1.7.0** (Python 3.11+). The services
subclass Pipecat's own `OpenAILLMService`, `OpenAITTSService`, and
`WebsocketSTTService`. Those base classes are stable, but Pipecat's import paths
and constructor kwargs do shift between releases — pin `pipecat-ai` and
re-verify when you upgrade.

## Quickstart

One key powers all three legs. Set `FLOE_API_KEY` in your environment (get a key
at [dev-dashboard.floelabs.xyz](https://dev-dashboard.floelabs.xyz)) — that alone
runs the **keyless** path. The **BYOK** snippet below *additionally* reads your own
vendor key (`OPENAI_API_KEY`); drop `provider_key=` to run keyless with no vendor
key at all.

```python
import os
from pipecat_floe import FloeSTTService, FloeLLMService, FloeTTSService

# BYOK — bring your own vendor key; Floe meters + caps and bills only its fee.
oai = os.environ["OPENAI_API_KEY"]
llm = FloeLLMService(model="openai/gpt-4o-mini", provider_key=oai)
tts = FloeTTSService(model="openai/tts-1", voice="alloy", provider_key=oai)
stt = FloeSTTService()                              # streaming STT — keyless (Floe-managed Deepgram)

# ...or go fully keyless: drop provider_key and Floe manages the vendor keys.
# Then drop stt / llm / tts into a Pipecat Pipeline as usual.
```

Three legs, one Floe key, one budget. Each service reads `FLOE_API_KEY` from the
environment (or pass `api_key=...`) — that's your Floe auth, separate from the
optional `provider_key` (your upstream vendor key, BYOK). A single spend cap on
the agent bounds the whole run — STT, LLM, and TTS together.

See [`examples/bot.py`](examples/bot.py) for a runnable pipeline wiring a
WebSocket transport → STT → LLM → TTS.

## Run the example

```bash
cd examples
pip install -r requirements.txt
cp .env.example .env      # fill in FLOE_API_KEY
python bot.py             # WebSocket server on ws://localhost:8765
```

Connect an audio WebSocket client to `ws://localhost:8765` and talk. Full
instructions in [`examples/README.md`](examples/README.md).

## Public API

```python
FloeLLMService(
    *, model="openai/gpt-4o-mini", api_key=None,
    base_url="https://credit-api.floelabs.xyz/v1", task_id=None,
    provider_key=None, **kwargs
)

FloeTTSService(
    *, model="openai/tts-1", voice="alloy", api_key=None,
    base_url="https://credit-api.floelabs.xyz/v1", task_id=None,
    provider_key=None, **kwargs
)

FloeSTTService(
    *, model="deepgram/nova-3", encoding="linear16", sample_rate=16000,
    language="en", api_key=None,
    base_url="wss://credit-api.floelabs.xyz/v1/audio/transcriptions/stream",
    **kwargs
)
```

- `api_key` defaults to the `FLOE_API_KEY` environment variable; a `ValueError`
  is raised if neither is set.
- `task_id` (LLM/TTS) tags calls with an `X-Floe-Task-Id` header so a per-task
  budget can bound one conversation.
- `provider_key` (**LLM/TTS — BYOK**) sends your upstream vendor key as the
  `X-Floe-Provider-Key` header, so Floe routes the call on *your* key and bills
  only its service fee (still metered, still spend-capped). Omit it for the
  keyless path. Streaming STT has no per-request BYOK — it uses Floe's managed
  Deepgram key.
- `**kwargs` pass through to the underlying Pipecat base class (temperature,
  custom settings, keepalive, reconnect options, ...).

## Limits / footguns

| Limit | Detail |
| --- | --- |
| **STT is a dedicated plugin, not a base-URL swap** | The LLM and TTS legs are OpenAI-compatible base-URL swaps. Streaming STT is **not** — `FloeSTTService` speaks Floe's own WebSocket protocol (raw PCM up, JSON transcripts down). You cannot point Pipecat's `OpenAISTTService` at Floe for streaming. |
| **Model IDs must be fully qualified** | Use `provider/model`, e.g. `openai/gpt-4o-mini`, `anthropic/claude-sonnet-4-6`, `deepgram/nova-3`, `openai/tts-1`. A bare `gpt-4o-mini` will be rejected by Floe. |
| **STT audio format** | PCM only, in the declared `encoding` (`linear16` / `mulaw` / `alaw`) at `sample_rate` 8000–48000. Pipecat delivers `linear16` PCM by default, which matches. |
| **TTS sample rate** | The underlying OpenAI TTS service emits 24 kHz PCM; passing a different `sample_rate` logs a warning. |
| **BYOK is LLM/TTS only** | `provider_key` (BYOK) is honored on the LLM and TTS legs — the keyless gateway accepts an optional `X-Floe-Provider-Key` header. Streaming STT has **no** per-request BYOK: it runs on Floe's managed Deepgram key regardless of `provider_key`. |
| **`task_id` / `provider_key` on TTS** | Attached via a custom `httpx` client's default headers. If you pass your own `http_client`, both are ignored for TTS (add the headers to that client yourself). |
| **Welcome credit** | A new Floe agent key comes with welcome credit that covers the first calls. After that, keep the agent funded or capped — an empty balance surfaces as a `{"type":"error","code":"insufficient_balance"}` on STT and an error frame on LLM/TTS. |
| **Pipecat version** | Pinned to `pipecat-ai` 1.7.0 (see above). Re-verify on upgrade. |

## How it works

- **LLM / TTS** — thin subclasses of Pipecat's `OpenAILLMService` /
  `OpenAITTSService` pointed at `https://credit-api.floelabs.xyz/v1` with your
  Floe key. Pass `provider_key=` and it rides as an `X-Floe-Provider-Key` header,
  so Floe meters + caps the call but bills only its fee on your upstream key
  (BYOK); omit it for keyless. Streaming, metrics (usage + TTFB), and
  OpenTelemetry tracing are inherited unchanged.
- **STT** — a subclass of Pipecat's `WebsocketSTTService` (the same base used by
  Deepgram and Gladia). It opens
  `wss://credit-api.floelabs.xyz/v1/audio/transcriptions/stream` with an
  `Authorization: Bearer <FLOE_API_KEY>` header, streams `frame.audio` PCM up,
  and maps `is_final:false` → `InterimTranscriptionFrame`, `is_final:true` →
  `TranscriptionFrame`. A server `{"type":"error"}` is pushed to the pipeline as
  an `ErrorFrame` and the stream is torn down cleanly. Reconnect-with-backoff and
  audio buffering come from the base class.

## Per-turn cost receipt

`FloeLLMService` logs a one-line cost receipt after every LLM turn — **on by
default** (pipecat-floe is a metering-branded service, so showing the cost is
on-brand). One line to disable:

```python
llm = FloeLLMService(model="openai/gpt-4o-mini", cost_receipts=False)
```

The receipt is logged at `INFO` via loguru (real line, captured against prod):

```text
floe · gpt-4o · $0.0012 est · left $99.88
```

The cost half is priced **locally** by [`floe-guard`](https://github.com/Floe-Labs/floe-guard)
(free, offline, no key — `est` means a local estimate). The `left $…` budget half
only appears when `FLOE_API_KEY` is set: it's a best-effort, fail-closed read of
your hosted Floe balance, so a failed read simply drops the budget and still
shows the cost. Without a key you get the cost line alone (`floe · gpt-4o ·
$0.0064 est`). A live-prod screenshot with the budget half is captured
separately with a funded key.

## License

MIT — see [LICENSE](LICENSE).
