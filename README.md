# pipecat-floe

**Floe services for [Pipecat](https://github.com/pipecat-ai/pipecat).** One
Floe key for the LLM, STT, and TTS legs of a voice agent — metered per call
with pre-call spend caps.

Three drop-in Pipecat services:

- **`FloeLLMService`** — OpenAI-compatible LLM routed through Floe.
- **`FloeTTSService`** — OpenAI-compatible text-to-speech routed through Floe.
- **`FloeSTTService`** — streaming speech-to-text over Floe's WebSocket.

<!-- TODO: 30-60s demo video -->

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
at [dev-dashboard.floelabs.xyz](https://dev-dashboard.floelabs.xyz)) and:

```python
from pipecat_floe import FloeSTTService, FloeLLMService, FloeTTSService

stt = FloeSTTService()                              # streaming STT (WebSocket)
llm = FloeLLMService(model="openai/gpt-4o-mini")    # OpenAI-compatible
tts = FloeTTSService(model="openai/tts-1", voice="alloy")

# ...then drop stt / llm / tts into a Pipecat Pipeline as usual.
```

Three legs, one Floe key, one budget. Each service reads `FLOE_API_KEY` from the
environment (or pass `api_key=...`). A single spend cap on the agent bounds the
whole run — STT, LLM, and TTS together.

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
    base_url="https://credit-api.floelabs.xyz/v1", task_id=None, **kwargs
)

FloeTTSService(
    *, model="openai/tts-1", voice="alloy", api_key=None,
    base_url="https://credit-api.floelabs.xyz/v1", task_id=None, **kwargs
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
- `**kwargs` pass through to the underlying Pipecat base class (temperature,
  custom settings, keepalive, reconnect options, ...).

## Limits / footguns

| Limit | Detail |
| --- | --- |
| **STT is a dedicated plugin, not a base-URL swap** | The LLM and TTS legs are OpenAI-compatible base-URL swaps. Streaming STT is **not** — `FloeSTTService` speaks Floe's own WebSocket protocol (raw PCM up, JSON transcripts down). You cannot point Pipecat's `OpenAISTTService` at Floe for streaming. |
| **Model IDs must be fully qualified** | Use `provider/model`, e.g. `openai/gpt-4o-mini`, `anthropic/claude-sonnet-4-6`, `deepgram/nova-3`, `openai/tts-1`. A bare `gpt-4o-mini` will be rejected by Floe. |
| **STT audio format** | PCM only, in the declared `encoding` (`linear16` / `mulaw` / `alaw`) at `sample_rate` 8000–48000. Pipecat delivers `linear16` PCM by default, which matches. |
| **TTS sample rate** | The underlying OpenAI TTS service emits 24 kHz PCM; passing a different `sample_rate` logs a warning. |
| **`task_id` on TTS** | Attached via a custom `httpx` client's default headers. If you pass your own `http_client`, `task_id` is ignored for TTS (add the header to your client yourself). |
| **Welcome credit** | A new Floe agent key comes with welcome credit that covers the first calls. After that, keep the agent funded or capped — an empty balance surfaces as a `{"type":"error","code":"insufficient_balance"}` on STT and an error frame on LLM/TTS. |
| **Pipecat version** | Pinned to `pipecat-ai` 1.7.0 (see above). Re-verify on upgrade. |

## How it works

- **LLM / TTS** — thin subclasses of Pipecat's `OpenAILLMService` /
  `OpenAITTSService` pointed at `https://credit-api.floelabs.xyz/v1` with your
  Floe key. Streaming, metrics (usage + TTFB), and OpenTelemetry tracing are
  inherited unchanged.
- **STT** — a subclass of Pipecat's `WebsocketSTTService` (the same base used by
  Deepgram and Gladia). It opens
  `wss://credit-api.floelabs.xyz/v1/audio/transcriptions/stream` with an
  `Authorization: Bearer <FLOE_API_KEY>` header, streams `frame.audio` PCM up,
  and maps `is_final:false` → `InterimTranscriptionFrame`, `is_final:true` →
  `TranscriptionFrame`. A server `{"type":"error"}` is pushed to the pipeline as
  an `ErrorFrame` and the stream is torn down cleanly. Reconnect-with-backoff and
  audio buffering come from the base class.

## License

MIT — see [LICENSE](LICENSE).
