"""End-to-end Gemini Live check. Pytest does not collect this file.

The key is read before any socket. A missing key prints gemini-key-missing and exits.
"""

import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHRASE = "Yap dictation live check"
CHUNK_FRAMES = 1024
REQUIRED_WORDS = ("yap", "dictation", "live", "check")


def load_gemini_key() -> str:
    secrets = Path.home() / ".config" / "yap" / "secrets.toml"
    if secrets.is_file():
        with secrets.open("rb") as handle:
            value = str(tomllib.load(handle).get("api_keys", {}).get("google", "")).strip()
        if value:
            return value
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _require_words(text: str) -> None:
    lowered = text.casefold()
    missing = [word for word in REQUIRED_WORDS if word not in lowered]
    if missing:
        raise SystemExit("missing words " + " ".join(missing))


def _build_wav(directory: Path) -> Path:
    aiff = directory / "yap-live.aiff"
    wav = directory / "yap-live.wav"
    subprocess.run(["say", "-o", str(aiff), PHRASE], check=True)
    subprocess.run(
        [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            str(aiff),
            str(wav),
        ],
        check=True,
    )
    return wav


def _feed(recorder, wav_path: Path) -> None:
    import soundfile as sf

    samples, rate = sf.read(wav_path, dtype="float32", always_2d=True)
    if rate != 16000:
        raise SystemExit(f"fixture rate {rate}")
    for start in range(0, len(samples), CHUNK_FRAMES):
        chunk = samples[start:start + CHUNK_FRAMES]
        recorder._callback(chunk, len(chunk), None, None)
        time.sleep(len(chunk) / rate)


def _run_session(key: str, wav_path: Path) -> None:
    from app.recorder import Recorder
    from app.transcriber import GeminiTranscriber

    transcriber = GeminiTranscriber(api_key=key, mode="smart", language="en")
    session = transcriber.open_live_session()
    recorder = Recorder()
    recorder.set_pcm_sink(session.write_pcm)
    if not session.wait_until_ready(15):
        session.close()
        raise SystemExit("gemini live setup failed")
    _feed(recorder, wav_path)
    started = time.perf_counter()
    result = session.finish()
    finish_s = time.perf_counter() - started
    print("phase=session")
    print("transcript=" + result.text)
    print(f"finish_s={finish_s:.3f}")
    print(f"chunk_frames={CHUNK_FRAMES}")
    _require_words(result.text)


def _run_pipeline(key: str, wav_path: Path) -> None:
    from app.cleanup import NoopCleanup
    from app.pipeline import Pipeline
    from app.recorder import Recorder
    from app.transcriber import GeminiTranscriber, skips_llm_cleanup
    import app.pipeline as pipeline_module

    if not skips_llm_cleanup("gemini", "smart"):
        raise SystemExit("gemini smart cleanup was not skipped")

    class FeedRecorder(Recorder):
        def start(self) -> None:
            self._clear_frames()
            self._reset_levels()

    transcriber = GeminiTranscriber(api_key=key, mode="smart", language="en")
    unary = {"count": 0}
    original = transcriber.transcribe

    def counting(wav_bytes: bytes):
        unary["count"] += 1
        return original(wav_bytes)

    transcriber.transcribe = counting
    opened: dict = {}
    original_open = transcriber.open_live_session

    def wrapped_open():
        session = original_open()
        original_finish = session.finish

        def wrapped_finish():
            started = time.perf_counter()
            try:
                return original_finish()
            finally:
                opened["finish_s"] = time.perf_counter() - started

        session.finish = wrapped_finish
        opened["session"] = session
        return session

    transcriber.open_live_session = wrapped_open
    pasted: list[str] = []
    pipeline_module.paste = lambda text, delay_ms=0: pasted.append(text)
    pipeline = Pipeline(
        recorder=FeedRecorder(),
        transcriber=transcriber,
        cleanup=NoopCleanup(),
        paste_delay_ms=0,
    )
    if not pipeline.start_recording(source="e2e"):
        raise SystemExit("pipeline did not start")
    _feed(pipeline.recorder, wav_path)
    if not pipeline.stop_recording_and_process(source="e2e"):
        raise SystemExit("pipeline did not return a transcript")
    text = pasted[0] if pasted else ""
    finish_s = float(opened.get("finish_s", 0.0))
    print("phase=pipeline")
    print("transcript=" + text)
    print(f"finish_s={finish_s:.3f}")
    print(f"unary_calls={unary['count']}")
    _require_words(text)
    if unary["count"] != 0:
        raise SystemExit("unary call followed a non-empty live transcript")


def main() -> int:
    key = load_gemini_key()
    if not key:
        print("gemini-key-missing")
        return 1
    with tempfile.TemporaryDirectory(prefix="yap-gemini-live-") as directory:
        wav_path = _build_wav(Path(directory))
        _run_session(key, wav_path)
        _run_pipeline(key, wav_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
