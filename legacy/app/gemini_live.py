"""Gemini Live push-to-talk session.

httpx has no WebSocket client. This module speaks the upgrade on a stdlib TLS socket.
A dropped socket is not resumed. The caller falls back to the unary WAV request.
"""

import base64
import hashlib
import json
import logging
import os
import queue
import socket
import ssl
import threading
import time
from urllib.parse import quote

from app.transcriber import TranscriptionResult

logger = logging.getLogger(__name__)

_HOST = "generativelanguage.googleapis.com"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_SETUP_TIMEOUT_S = 10.0
_FINAL_TIMEOUT_S = 20.0
_FINAL_GRACE_S = 0.75
_FINISH_WAIT_S = 45.0
_MAX_FRAME_BYTES = 8_000_000

_ACTIVITY_START = {"realtimeInput": {"activityStart": {}}}
_ACTIVITY_END = {"realtimeInput": {"activityEnd": {}}}


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def _audio_message(pcm: bytes) -> dict:
    return {
        "realtimeInput": {
            "audio": {
                "data": base64.b64encode(pcm).decode("ascii"),
                "mimeType": "audio/pcm;rate=16000",
            }
        }
    }


def _error_text(message: dict) -> str:
    err = message.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("status") or "gemini live error")
    if err:
        return str(err)
    return ""


def _parse_frame(buf: bytearray) -> tuple[tuple[int, int, bytes], int] | None:
    if len(buf) < 2:
        return None
    first = buf[0]
    second = buf[1]
    if first & 0x70:
        raise ConnectionError("gemini live sent an extended frame")
    fin = 1 if first & 0x80 else 0
    opcode = first & 0x0F
    masked = second & 0x80
    length = second & 0x7F
    offset = 2
    if length == 126:
        if len(buf) < 4:
            return None
        length = int.from_bytes(buf[2:4], "big")
        offset = 4
    elif length == 127:
        if len(buf) < 10:
            return None
        length = int.from_bytes(buf[2:10], "big")
        offset = 10
    if length > _MAX_FRAME_BYTES:
        raise ConnectionError("gemini live frame is too large")
    mask_len = 4 if masked else 0
    total = offset + mask_len + length
    if len(buf) < total:
        return None
    payload = bytes(buf[offset + mask_len:total])
    if masked:
        mask = bytes(buf[offset:offset + 4])
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return (fin, opcode, payload), total


class _SocketWebSocket:
    def __init__(self, sock: ssl.SSLSocket, label: str = "live"):
        self.sock = sock
        self.label = label
        self._buf = bytearray()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_json(self, timeout: float) -> dict | None:
        frame = self._next_data(timeout)
        if frame is None:
            return None
        opcode, payload = frame
        if opcode not in (0x1, 0x2) or not payload:
            return None
        message = json.loads(payload.decode("utf-8"))
        if isinstance(message, dict):
            return message
        return None

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.settimeout(10)
        self.sock.sendall(bytes(header) + mask + masked)

    def _fill(self, timeout: float) -> bool:
        self.sock.settimeout(max(timeout, 0.01))
        try:
            chunk = self.sock.recv(65536)
        except (TimeoutError, socket.timeout):
            return False
        except ssl.SSLError as exc:
            if "timed out" in str(exc).lower():
                return False
            raise
        if not chunk:
            raise ConnectionError(f"{self.label} socket closed")
        self._buf.extend(chunk)
        return True

    def _next_frame(self, timeout: float) -> tuple[int, int, bytes] | None:
        deadline = time.monotonic() + timeout
        while True:
            parsed = _parse_frame(self._buf)
            if parsed is not None:
                frame, used = parsed
                del self._buf[:used]
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._fill(remaining):
                return None

    def _next_data(self, timeout: float) -> tuple[int, bytes] | None:
        deadline = time.monotonic() + timeout
        parts: list[bytes] = []
        opcode: int | None = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if parts:
                    raise ConnectionError(f"incomplete {self.label} frame")
                return None
            frame = self._next_frame(remaining)
            if frame is None:
                if parts:
                    raise ConnectionError(f"incomplete {self.label} frame")
                return None
            fin, op, payload = frame
            if op == 0x9:
                self._send_frame(0xA, payload)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                raise ConnectionError(f"{self.label} socket closed")
            if op == 0x0:
                parts.append(payload)
            elif op in (0x1, 0x2):
                opcode = op
                parts = [payload]
            else:
                continue
            if fin and opcode is not None:
                return opcode, b"".join(parts)


def _accept_ok(headers: str, ws_key: str) -> bool:
    expected = base64.b64encode(
        hashlib.sha1((ws_key + _WS_GUID).encode("ascii")).digest()
    ).decode("ascii")
    for line in headers.split("\r\n"):
        if line.lower().startswith("sec-websocket-accept:"):
            return line.split(":", 1)[1].strip() == expected
    return True


def open_tls_websocket(
    host: str,
    path: str,
    extra_headers: dict[str, str] | None = None,
    label: str = "live",
) -> _SocketWebSocket:
    """Open one TLS WebSocket. `extra_headers` are sent on the handshake only."""
    raw = socket.create_connection((host, 443), timeout=10)
    try:
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise
    ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
    header_lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {ws_key}",
        "Sec-WebSocket-Version: 13",
        f"Origin: https://{host}",
    ]
    for name, value in (extra_headers or {}).items():
        if "\r" in value or "\n" in value:
            sock.close()
            raise ValueError(f"{label} header is not a single line")
        header_lines.append(f"{name}: {value}")
    request = "\r\n".join(header_lines) + "\r\n\r\n"
    try:
        sock.sendall(request.encode("ascii"))
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError(f"{label} handshake closed")
            data += chunk
            if len(data) > 65536:
                raise ConnectionError(f"{label} handshake too long")
    except Exception:
        sock.close()
        raise
    head, rest = data.split(b"\r\n\r\n", 1)
    text = head.decode("iso-8859-1")
    parts = text.split("\r\n", 1)[0].split()
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if status != 101 or not _accept_ok(text, ws_key):
        sock.close()
        raise RuntimeError(f"{label} handshake HTTP {status}")
    ws = _SocketWebSocket(sock, label)
    if rest:
        ws._buf.extend(rest)
    return ws


def _connect(api_key: str) -> _SocketWebSocket:
    path = (
        "/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="
        + quote(api_key, safe="")
    )
    return open_tls_websocket(_HOST, path, label="gemini live")


class GeminiLiveSession:
    """One push-to-talk turn. PCM queued before setup is sent only after activity start."""

    def __init__(self, api_key: str, setup: dict):
        self._api_key = api_key
        self._setup = setup
        self._out: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        self._lock = threading.Lock()
        self._sock_lock = threading.Lock()
        self._sock: ssl.SSLSocket | None = None
        self._pcm = bytearray()
        self._closing = False
        self._ready = threading.Event()
        self._done = threading.Event()
        self._finals: list[str] = []
        self._language = ""
        self._result: TranscriptionResult | None = None
        self._error: Exception | None = None
        self._turn_complete = False
        self.finish_wait_s = 0.0

    def start(self) -> None:
        threading.Thread(target=self._run, name="gemini-live", daemon=True).start()

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
            raise TimeoutError("gemini live finish timed out")
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
            raise RuntimeError("gemini live returned no result")
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
        text = " ".join(part for part in self._finals if part).strip()
        self._result = TranscriptionResult(text=text, language=self._language, latency=0.0)

    def _apply_server_message(self, message: dict) -> str:
        if "setupComplete" in message or "setup_complete" in message:
            logger.info("Gemini live setup complete")
            return "setup"
        error = _error_text(message)
        if error:
            raise RuntimeError(_redact(error, self._api_key))
        content = message.get("serverContent")
        if content is None:
            content = message.get("server_content")
        if not isinstance(content, dict):
            return "other"
        final = content.get("inputTranscription")
        if final is None:
            final = content.get("input_transcription")
        if isinstance(final, dict):
            text = str(final.get("text") or "").strip()
            if text:
                self._finals.append(text)
            for key in ("language", "languageCode", "language_code"):
                value = str(final.get(key) or "").strip()
                if value:
                    self._language = value
                    break
        if content.get("turnComplete") or content.get("turn_complete"):
            self._turn_complete = True
            logger.info("Gemini live turn complete")
            return "turn"
        if isinstance(final, dict):
            return "final"
        return "other"

    def _io_loop(self, ws: _SocketWebSocket) -> None:
        ws.send_text(json.dumps(self._setup))
        stashed: list[bytes] = []
        streaming = False
        end_requested = False
        end_sent = False
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
                    ws.send_text(json.dumps(_audio_message(payload)))
                else:
                    stashed.append(payload)

            if streaming and end_requested and not end_sent:
                ws.send_text(json.dumps(_ACTIVITY_END))
                end_sent = True
                finish_deadline = time.monotonic() + _FINAL_TIMEOUT_S

            if not streaming and time.monotonic() > setup_deadline:
                raise TimeoutError("gemini live setup timed out")

            message = ws.recv_json(0.05)
            if message is None:
                if finish_deadline is not None and time.monotonic() > finish_deadline:
                    if self._finals:
                        self._store_result()
                        return
                    raise TimeoutError("gemini live final timed out")
                continue

            event = self._apply_server_message(message)
            if event == "final" and end_sent:
                finish_deadline = time.monotonic() + _FINAL_GRACE_S
            if event == "setup" and not streaming:
                ws.send_text(json.dumps(_ACTIVITY_START))
                streaming = True
                self._ready.set()
                for chunk in stashed:
                    ws.send_text(json.dumps(_audio_message(chunk)))
                stashed.clear()
                if end_requested and not end_sent:
                    ws.send_text(json.dumps(_ACTIVITY_END))
                    end_sent = True
                    finish_deadline = time.monotonic() + _FINAL_TIMEOUT_S
            if self._turn_complete:
                self._store_result()
                return

    def _run(self) -> None:
        ws: _SocketWebSocket | None = None
        try:
            ws = _connect(self._api_key)
            self._set_sock(ws.sock)
            self._io_loop(ws)
        except Exception as exc:
            message = _redact(str(exc), self._api_key)
            if self._finals and self._result is None:
                self._store_result()
            elif self._result is None:
                self._error = RuntimeError(message)
        finally:
            if ws is not None:
                ws.close()
            self._done.set()
