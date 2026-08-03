#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Floe streaming speech-to-text service for Pipecat.

Unlike the LLM and TTS legs (which are OpenAI-compatible base-URL swaps), Floe
streaming STT is a dedicated plugin: it opens a WebSocket to Floe, streams raw
PCM audio up, and receives JSON transcript messages back. This service is
modelled on Pipecat's own WebSocket STT services (Deepgram, Gladia): it
subclasses :class:`~pipecat.services.stt_service.WebsocketSTTService`, which
supplies the connect/receive/reconnect scaffolding, and implements the
Floe-specific wire protocol.

Wire protocol:
    Connect: ``wss://credit-api.floelabs.xyz/v1/audio/transcriptions/stream``
        with query params ``model``, ``encoding``, ``sample_rate``, ``language``.
    Auth: ``Authorization: Bearer <FLOE_API_KEY>`` header.
    Client -> server: raw binary PCM frames in the declared encoding.
    Server -> client: JSON ``{"type":"transcript","text","is_final","speech_final"}``
        and ``{"type":"error","code":...}`` (followed by a socket close).
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from urllib.parse import urlencode

from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import WebsocketSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt
from websockets.protocol import State

from pipecat_floe.constants import FLOE_API_KEY_ENV, FLOE_STT_WS_URL

# Encodings Floe's streaming endpoint accepts. linear16 is 16-bit PCM, which is
# what Pipecat transports deliver by default.
_VALID_ENCODINGS = ("linear16", "mulaw", "alaw")

# Sample-rate bounds accepted by the Floe streaming endpoint.
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 48000


class FloeSTTService(WebsocketSTTService):
    """Streaming speech-to-text over Floe's transcription WebSocket.

    Audio is streamed to Floe as raw PCM and transcripts arrive as JSON. Each
    non-final result is emitted as an
    :class:`~pipecat.frames.frames.InterimTranscriptionFrame`; each final result
    is emitted as a :class:`~pipecat.frames.frames.TranscriptionFrame`. A server
    ``{"type":"error"}`` message (for example ``insufficient_balance``) is
    surfaced to the pipeline via :meth:`push_error` and the stream is torn down
    cleanly. Transcription is metered on your Floe balance and bounded by any
    spend cap set on the agent key.

    The connect/receive/reconnect lifecycle (including audio buffering and
    exponential-backoff reconnect) is inherited from
    :class:`~pipecat.services.stt_service.WebsocketSTTService`.
    """

    def __init__(
        self,
        *,
        model: str = "deepgram/nova-3",
        encoding: str = "linear16",
        sample_rate: int = 16000,
        language: str = "en",
        api_key: str | None = None,
        base_url: str = FLOE_STT_WS_URL,
        **kwargs,
    ) -> None:
        """Initialize the Floe streaming STT service.

        Args:
            model: Fully qualified ``provider/model`` STT ID. Defaults to
                ``"deepgram/nova-3"``.
            encoding: Audio encoding of the PCM frames streamed to Floe. One of
                ``"linear16"``, ``"mulaw"``, ``"alaw"``. Defaults to
                ``"linear16"``.
            sample_rate: Audio sample rate in Hz (8000-48000). Defaults to
                16000.
            language: BCP-47 language hint. Defaults to ``"en"``.
            api_key: Floe agent key. If ``None``, the value of the
                ``FLOE_API_KEY`` environment variable is used.
            base_url: Floe streaming-STT WebSocket URL. Defaults to
                :data:`~pipecat_floe.constants.FLOE_STT_WS_URL`.
            **kwargs: Additional keyword arguments forwarded to
                :class:`~pipecat.services.stt_service.WebsocketSTTService`.

        Raises:
            ValueError: If no API key is provided and ``FLOE_API_KEY`` is unset,
                if ``encoding`` is unsupported, or if ``sample_rate`` is out of
                range.
        """
        resolved_key = api_key or os.environ.get(FLOE_API_KEY_ENV)
        if not resolved_key:
            raise ValueError(
                "A Floe API key is required. Pass api_key=... or set the "
                f"{FLOE_API_KEY_ENV} environment variable."
            )
        if encoding not in _VALID_ENCODINGS:
            raise ValueError(
                f"encoding must be one of {_VALID_ENCODINGS}, got {encoding!r}."
            )
        if not _MIN_SAMPLE_RATE <= sample_rate <= _MAX_SAMPLE_RATE:
            raise ValueError(
                f"sample_rate must be between {_MIN_SAMPLE_RATE} and "
                f"{_MAX_SAMPLE_RATE} Hz, got {sample_rate}."
            )

        super().__init__(sample_rate=sample_rate, **kwargs)

        self._api_key = resolved_key
        self._base_url = base_url
        self._model = model
        self._encoding = encoding
        self._language = language
        self._receive_task = None

    def can_generate_metrics(self) -> bool:
        """Whether this service reports processing metrics.

        Returns:
            ``True`` — the service reports TTFB and usage metrics via the
            inherited STT base-class hooks.
        """
        return True

    def _build_url(self) -> str:
        """Build the Floe streaming-STT WebSocket URL with query parameters.

        Returns:
            The connect URL including the ``model``, ``encoding``,
            ``sample_rate`` and ``language`` query parameters.
        """
        params = urlencode(
            {
                "model": self._model,
                "encoding": self._encoding,
                "sample_rate": self.sample_rate,
                "language": self._language,
            }
        )
        return f"{self._base_url}?{params}"

    async def start(self, frame: StartFrame) -> None:
        """Start the service and open the Floe STT connection.

        Args:
            frame: The start frame carrying pipeline audio settings.
        """
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame) -> None:
        """Stop the service on a graceful pipeline end.

        Args:
            frame: The end frame.
        """
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        """Cancel the service immediately.

        Args:
            frame: The cancel frame.
        """
        await super().cancel(frame)
        await self._disconnect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        """Stream a chunk of audio to Floe.

        Transcripts are delivered asynchronously by :meth:`_receive_messages`,
        so this generator sends the audio and yields ``None``.

        Args:
            audio: Raw PCM audio bytes in the configured encoding.

        Yields:
            ``None`` — results arrive over the WebSocket, not from this call.
        """
        await self.start_processing_metrics()
        if self._websocket and self._websocket.state is State.OPEN:
            try:
                await self._websocket.send(audio)
            except Exception as e:
                logger.warning(f"{self}: send failed, connection will reconnect: {e}")
        yield None

    async def _connect(self) -> None:
        """Open the WebSocket and start the receive loop."""
        await self._connect_websocket()
        await super()._connect()
        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(
                self._receive_task_handler(self._report_error)
            )

    async def _disconnect(self) -> None:
        """Stop the receive loop and close the WebSocket."""
        await super()._disconnect()
        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None
        await self._disconnect_websocket()

    async def _connect_websocket(self) -> None:
        """Establish the authenticated WebSocket connection to Floe."""
        try:
            if self._websocket and self._websocket.state is State.OPEN:
                return
            logger.debug(f"{self}: connecting to Floe STT WebSocket")
            headers = {"Authorization": f"Bearer {self._api_key}"}
            self._websocket = await self._websocket_connect(
                self._build_url(), additional_headers=headers
            )
            await self._call_event_handler("on_connected")
            logger.debug(f"{self}: connected to Floe STT WebSocket")
        except Exception as e:
            self._websocket = None
            await self.push_error(
                error_msg=f"Unable to connect to Floe STT: {e}", exception=e
            )

    async def _disconnect_websocket(self) -> None:
        """Close the WebSocket connection to Floe."""
        try:
            if self._websocket and self._websocket.state is State.OPEN:
                logger.debug(f"{self}: disconnecting from Floe STT WebSocket")
                await self._websocket.close()
        except Exception as e:
            await self.push_error(
                error_msg=f"Error closing Floe STT WebSocket: {e}", exception=e
            )
        finally:
            self._websocket = None
            await self._call_event_handler("on_disconnected")

    @traced_stt
    async def _handle_transcription(
        self, transcript: str, is_final: bool, language: Language | str | None = None
    ) -> None:
        """Trace hook for a completed final transcription.

        Args:
            transcript: The final transcript text.
            is_final: Whether the transcript is final (always ``True`` here).
            language: Detected/declared language, if any.
        """
        await self.stop_processing_metrics()

    async def _receive_messages(self) -> None:
        """Receive and dispatch JSON messages from the Floe STT WebSocket.

        Runs continuously (driven by the inherited receive-task handler). Each
        ``transcript`` message is emitted as an interim or final frame; each
        ``error`` message is surfaced via :meth:`push_error` and ends the loop
        so the connection is torn down cleanly.
        """
        if not self._websocket:
            return
        async for message in self._websocket:
            if isinstance(message, bytes):
                # The Floe STT stream is transcripts-only; ignore any binary.
                continue
            try:
                content = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"{self}: received non-JSON message: {message}")
                continue

            msg_type = content.get("type")
            if msg_type == "transcript":
                await self._handle_transcript_message(content)
            elif msg_type == "error":
                code = content.get("code", "unknown")
                await self.push_error(error_msg=f"Floe STT error: {code}")
                # The server closes the socket after an error; stop reading so
                # the connection is torn down rather than reconnected in a loop.
                return
            else:
                logger.debug(f"{self}: ignoring message type {msg_type!r}")

    async def _handle_transcript_message(self, content: dict) -> None:
        """Emit interim/final transcription frames from a transcript message.

        Args:
            content: The decoded ``{"type":"transcript", ...}`` payload.
        """
        text = content.get("text", "")
        if not text:
            return
        is_final = bool(content.get("is_final"))
        if is_final:
            # Report usage before the frame so tracing can attach it to the STT
            # span the frame closes — mirrors the Deepgram/Gladia services.
            await self.emit_stt_usage_metrics()
            await self.push_frame(
                TranscriptionFrame(
                    text,
                    self._user_id,
                    time_now_iso8601(),
                    self._language,
                    result=content,
                )
            )
            await self._handle_transcription(text, is_final, self._language)
        else:
            await self.push_frame(
                InterimTranscriptionFrame(
                    text,
                    self._user_id,
                    time_now_iso8601(),
                    self._language,
                    result=content,
                )
            )
