"""Mistral Realtime push-to-talk session.

The batch call is POST /v1/audio/transcriptions. Realtime is a different socket:
wss://api.mistral.ai/v1/audio/transcriptions/realtime with model
voxtral-mini-transcribe-realtime-2602. Audio is pcm_s16le at 16 kHz. The
final transcript is transcription.done. A dropped socket is not resumed.
"""

import base64
import json
import logging
import queue
import socket
import ssl
import threading
import time
from urllib.parse import quote

from app.gemini_live import open_tls_websocket
from app.transcriber import TranscriptionResult

logger = logging.getLogger(__name__)

REALTIME_MODEL = "voxtral-mini-transcribe-realtime-2602"
_HOST = "api.mistral.ai"
_SETUP_TIMEOUT_S = 10.0
_FINAL_TIMEOUT_S = 25.0
_FINISH_WAIT_S = 45.0
_MAX_APPEND_BYTES = 200_000

_SESSION_UPDATE = {
    "type": "session.update",
    "session": {
        "audio_format": {"encoding": "pcm_s16le", "sample_rate": 16000},
        "target_streaming_delay_ms": 480,
    },
}
_FLUSH = {"type": "input_audio.flush"}
_END = {"type": "input_audio.end"}


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def _append_message(pcm: bytes) -> dict:
    return {
        "type": "input_audio.append",
        "audio": base64.b64encode(pcm).decode("ascii"),
    }


def _chunks(pcm: bytes):
    for start in range(0, len(pcm), _MAX_APPEND_BYTES):
        yield pcm[start : start + _MAX_APPEND_BYTES]


def _error_text(message: dict) -> str:
    err = message.get("error")
    if isinstance(err, dict):
        detail = err.get("message")
        if isinstance(detail, dict):
            return str(detail.get("detail") or detail)
        return str(detail or err.get("code") or "mistral realtime error")
    if err:
        return str(err)
    return ""


class MistralRealtimeSession:
    """One push-to-talk turn. PCM queued before session.updated is sent after it."""

    def __init__(self, api_key: str, model: str = REALTIME_MODEL):
        self._api_key = api_key
        self._model = model or REALTIME_MODEL
        self._out: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        self._lock = threading.Lock()
        self._sock_lock = threading.Lock()
        self._sock: ssl.SSLSocket | None = None
        self._pcm = bytearray()
        self._closing = False
        self._ready = threading.Event()
        self._done = threading.Event()
        self._deltas: list[str] = []
        self._language = ""
        self._final_text = ""
        self._result: TranscriptionResult | None = None
        self._error: Exception | None = None
        self.finish_wait_s = 0.0

    def start(self) -> None:
        threading.Thread(target=self._run, name="mistral-realtime", daemon=True).start()

    def wait_until_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ready.is_set():
                return True
            if self._done.is_set():
                return False
            time.sleep(0.02)
        return self._ready.is_set()

    def write_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self._lock:
            if self._closing:
                return
            self._pcm.extend(pcm)
            if self._done.is_set():
                return
            self._out.put(("pcm", bytes(pcm)))

    def finish(self) -> TranscriptionResult:
        started = time.perf_counter()
        with self._lock:
            self._closing = True
        self._out.put(("end", None))
        if not self._done.wait(_FINISH_WAIT_S):
            self._shutdown_socket()
            raise TimeoutError("mistral realtime finish timed out")
        self.finish_wait_s = time.perf_counter() - started
        result = self._result
        if result is not None and result.text.strip():
            with self._lock:
                self._pcm.clear()
            result.latency = self.finish_wait_s
            return result
        if self._error is not None:
            raise self._error
        if result is None:
            raise RuntimeError("mistral realtime returned no result")
        result.latency = self.finish_wait_s
        return result

    def close(self) -> None:
        with self._lock:
            self._closing = True
        self._out.put(("close", None))
        self._shutdown_socket()
        self._done.wait(2)

    def _set_sock(self, sock: ssl.SSLSocket) -> None:
        with self._sock_lock:
            self._sock = sock

    def _shutdown_socket(self) -> None:
        with self._sock_lock:
            sock = self._sock
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _drain(self) -> list[tuple[str, bytes | None]]:
        commands: list[tuple[str, bytes | None]] = []
        while True:
            try:
                commands.append(self._out.get_nowait())
            except queue.Empty:
                return commands

    def _store_result(self) -> None:
        text = self._final_text.strip() or "".join(self._deltas).strip()
        self._result = TranscriptionResult(text=text, language=self._language, latency=0.0)

    def _apply(self, message: dict) -> str:
        kind = str(message.get("type") or "")
        error = _error_text(message) if kind == "error" or message.get("error") else ""
        if error:
            raise RuntimeError(_redact(error, self._api_key))
        if kind == "session.created":
            logger.info("Mistral realtime session created")
            return "created"
        if kind == "session.updated":
            logger.info("Mistral realtime session updated")
            return "updated"
        if kind == "transcription.language":
            self._language = str(message.get("audio_language") or "").strip()
            return "language"
        if kind == "transcription.text.delta":
            delta = str(message.get("text") or "")
            if delta:
                self._deltas.append(delta)
            return "delta"
        if kind == "transcription.done":
            self._final_text = str(message.get("text") or "")
            language = str(message.get("language") or "").strip()
            if language:
                self._language = language
            logger.info("Mistral realtime transcription done")
            return "done"
        return "other"

    def _send_pcm(self, ws, pcm: bytes) -> None:
        for chunk in _chunks(pcm):
            ws.send_text(json.dumps(_append_message(chunk)))

    def _io_loop(self, ws) -> None:
        created = False
        streaming = False
        end_requested = False
        end_sent = False
        stashed: list[bytes] = []
        setup_deadline = time.monotonic() + _SETUP_TIMEOUT_S
        finish_deadline: float | None = None

        while True:
            for kind, payload in self._drain():
                if kind == "close":
                    return
                if kind == "end":
                    end_requested = True
                    continue
                if end_requested or not isinstance(payload, bytes):
                    continue
                if streaming:
                    self._send_pcm(ws, payload)
                else:
                    stashed.append(payload)

            if streaming and end_requested and not end_sent:
                ws.send_text(json.dumps(_FLUSH))
                ws.send_text(json.dumps(_END))
                end_sent = True
                finish_deadline = time.monotonic() + _FINAL_TIMEOUT_S

            if not streaming and time.monotonic() > setup_deadline:
                raise TimeoutError("mistral realtime setup timed out")

            message = ws.recv_json(0.05)
            if message is None:
                if finish_deadline is not None and time.monotonic() > finish_deadline:
                    if self._final_text or self._deltas:
                        self._store_result()
                        return
                    raise TimeoutError("mistral realtime final timed out")
                continue

            event = self._apply(message)
            if event == "created" and not created:
                created = True
                ws.send_text(json.dumps(_SESSION_UPDATE))
            if event == "updated" and not streaming:
                streaming = True
                self._ready.set()
                for chunk in stashed:
                    self._send_pcm(ws, chunk)
                stashed.clear()
                if end_requested and not end_sent:
                    ws.send_text(json.dumps(_FLUSH))
                    ws.send_text(json.dumps(_END))
                    end_sent = True
                    finish_deadline = time.monotonic() + _FINAL_TIMEOUT_S
            if event == "done":
                self._store_result()
                return

    def _run(self) -> None:
        ws = None
        try:
            path = "/v1/audio/transcriptions/realtime?model=" + quote(self._model, safe="")
            ws = open_tls_websocket(
                _HOST,
                path,
                extra_headers={"Authorization": f"Bearer {self._api_key}"},
                label="mistral realtime",
            )
            self._set_sock(ws.sock)
            self._io_loop(ws)
        except Exception as exc:
            message = _redact(str(exc), self._api_key)
            if (self._final_text or self._deltas) and self._result is None:
                self._store_result()
            elif self._result is None:
                self._error = RuntimeError(message)
        finally:
            if ws is not None:
                ws.close()
            self._done.set()
