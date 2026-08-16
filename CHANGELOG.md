# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-16

### Added

- **BYOK for the LLM and TTS legs.** `FloeLLMService` and `FloeTTSService` now
  accept an optional `provider_key=...` that is sent as the `X-Floe-Provider-Key`
  header, so Floe routes the call on *your* upstream vendor key and bills only
  its service fee — while still metering the call and enforcing your spend caps.
  Omit it for the keyless path (Floe-managed provider keys). Streaming STT has no
  per-request BYOK: it runs on Floe's managed Deepgram key.

### Changed

- README reframed **BYOK-first**: bring your own vendor key for LLM/TTS and add
  Floe metering + spend caps, or go keyless. STT documented as keyless.

## [0.1.0] - 2026-08-03

### Added

- Initial release of `pipecat-floe`: Floe services for Pipecat.
- `FloeLLMService` — OpenAI-compatible LLM routed through Floe, with optional
  `X-Floe-Task-Id` header support.
- `FloeTTSService` — OpenAI-compatible text-to-speech routed through Floe, with
  optional `X-Floe-Task-Id` header support.
- `FloeSTTService` — streaming speech-to-text over Floe's WebSocket protocol
  (raw PCM up, JSON transcripts down), emitting `InterimTranscriptionFrame` /
  `TranscriptionFrame` and reporting usage + TTFB metrics.
- Runnable example bot (`examples/bot.py`) wiring a WebSocket transport through
  all three legs on one Floe key.

[0.2.0]: https://github.com/Floe-Labs/pipecat-floe/releases/tag/v0.2.0
[0.1.0]: https://github.com/Floe-Labs/pipecat-floe/releases/tag/v0.1.0
