# Recording the 30–60s demo

The story to sell in one shot: **one Floe key powers all three legs (STT + LLM
+ TTS), on one budget.** The most convincing frame is a split screen — the bot
talking on the left, the Floe dashboard's balance ticking down on the right —
because it shows the spend crossing three services on a single key, live.

## Setup (once, before recording)

```bash
cd examples
pip install -r requirements.txt
cp .env.example .env          # fill in FLOE_API_KEY
```

Give the agent key a **small spend cap** in the dashboard first (e.g. $0.50).
The cap makes the "one budget bounds the whole run" point concrete and keeps the
dashboard number visibly moving during the clip.

## Client

`bot.py` uses Pipecat's `WebsocketServerTransport`, which speaks Pipecat's
protobuf frame protocol — a raw browser mic will **not** connect. Use a matching
Pipecat client:

- The `websocket-client` example in the [pipecat repo](https://github.com/pipecat-ai/pipecat/tree/main/examples)
  (`client/` web app), or
- A Pipecat client SDK (JS/React/iOS/Android) pointed at `ws://localhost:8765`.

If you'd rather demo with the browser's built-in mic and no separate client,
swap the transport to `SmallWebRTCTransport` with the Pipecat prebuilt UI — but
that's a change to the example, not the default.

## Shot list (~45s)

1. **0–5s** — terminal: `python bot.py`. Show the `WebsocketServerTransport`
   coming up on `ws://localhost:8765`. One caption: *"One Floe key. STT + LLM +
   TTS."*
2. **5–10s** — connect the client; the log prints `Client connected — say hello.`
3. **10–35s** — speak two short turns (script below). Let the reply play aloud.
   Keep the **Floe dashboard** visible: the balance drops as STT, LLM, and TTS
   each meter on the same key.
4. **35–45s** — cut to the dashboard's per-request view showing all three legs
   billed under one agent. Caption: *"One budget bounds the whole call."*

## Spoken script (keep it tight — the LLM reply is spoken aloud)

- You: *"Hey — what can you help me with?"*
- (agent answers, one or two sentences)
- You: *"Great. Set a reminder for my 3pm call."*
- (agent answers)

## Export

- 30–60s, MP4 (or a <10 MB GIF for inline README embedding).
- Land the "one key, three legs, one budget" caption in the first 5 seconds —
  most viewers won't reach the end.

Once it's recorded, drop the file/URL into the **Demo** slot at the top of the
repo `README.md`.
