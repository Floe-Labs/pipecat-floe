# Example: three-leg Floe voice bot

A minimal [Pipecat](https://github.com/pipecat-ai/pipecat) voice bot whose
**STT, LLM, and TTS all meter on one Floe key** — one key, one ledger, one
budget. The transport is Pipecat's built-in local WebSocket server, so it runs
with no cloud-transport account.

```
WebSocket client  ⇄  bot.py
   ├─ STT  FloeSTTService  → Floe streaming transcription (WebSocket)
   ├─ LLM  FloeLLMService  → Floe keyless inference (OpenAI-compatible)
   └─ TTS  FloeTTSService  → Floe keyless speech      (OpenAI-compatible)
   all three legs → one FLOE_API_KEY · one budget
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in FLOE_API_KEY
python bot.py             # starts a WebSocket server on ws://localhost:8765
```

Then connect an audio WebSocket client (for example a Pipecat client SDK, or
the websocket-client examples in the Pipecat repo) to `ws://localhost:8765` and
start talking.

Set a **spend cap** on the Floe agent (dashboard, or `PUT /v1/agents/spend-limit`)
to bound the whole run — STT + LLM + TTS together.

<!-- TODO: 30-60s demo video -->

## Notes

- Model IDs are fully qualified `provider/model` (for example
  `openai/gpt-4o-mini`, `deepgram/nova-3`, `openai/tts-1`) — that is what Floe
  expects.
- A live run needs a **funded** Floe agent key. New keys come with Floe welcome
  credit that covers the first calls.
