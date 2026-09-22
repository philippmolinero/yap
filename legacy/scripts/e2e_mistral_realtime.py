"""End-to-end Mistral Realtime check. Pytest does not collect this file.

The key is read before any socket. A missing key prints mistral-key-missing and exits.
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


def load_mistral_key() -> str:
    secrets = Path.home() / ".config" / "yap" / "secrets.toml"
    if secrets.is_file():
        with secrets.open("rb") as handle:
            value = str(tomllib.load(handle).get("api_keys", {}).get("mistral", "")).strip()
        if value:
            return value
    value = os.environ.get("MISTRAL_API_KEY", "").strip()
    if value:
        return value
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, item = raw.split("=", 1)
            if key.strip() == "MISTRAL_API_KEY":
                return item.strip().strip('"').strip("'")
    return ""


def _require_words(text: str) -> None:
    lowered = text.casefold()
    missing = [word for word in REQUIRED_WORDS if word not in lowered]
    if missing:
        raise SystemExit("missing words " + " ".join(missing) + " in " + text)


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
        chunk = samples[start : start + CHUNK_FRAMES]
        recorder._callback(chunk, len(chunk), None, None)
        time.sleep(len(chunk) / rate)


def _run_session(key: str, wav_path: Path) -> None:
    from app.recorder import Recorder
    from app.transcriber import Transcriber

    transcriber = Transcriber(api_key=key)
    session = transcriber.open_live_session()
    recorder = Recorder()
    recorder.set_pcm_sink(session.write_pcm)
    if not session.wait_until_ready(15):
        session.close()
        raise SystemExit("mistral realtime setup failed")
    _feed(recorder, wav_path)
    started = time.perf_counter()
    result = session.finish()
    finish_s = time.perf_counter() - started
    print("phase=session")
    print("transcript=" + result.text)
    print(f"finish_s={finish_s:.3f}")
    print(f"language={result.language}")
    _require_words(result.text)


def _run_pipeline(key: str, wav_path: Path) -> None:
    from app.cleanup import NoopCleanup
    from app.pipeline import Pipeline
    from app.recorder import Recorder
    from app.transcriber import Transcriber
    import app.pipeline as pipeline_module

    class FeedRecorder(Recorder):
        def start(self) -> None:
            self._clear_frames()
            self._reset_levels()

    transcriber = Transcriber(api_key=key)
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
        raise SystemExit("batch call followed a non-empty realtime transcript")


def main() -> int:
    key = load_mistral_key()
    if not key:
        print("mistral-key-missing")
        return 1
    with tempfile.TemporaryDirectory(prefix="yap-mistral-realtime-") as directory:
        wav_path = _build_wav(Path(directory))
        _run_session(key, wav_path)
        _run_pipeline(key, wav_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
