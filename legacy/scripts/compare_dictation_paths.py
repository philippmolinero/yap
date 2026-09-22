"""Compare Mistral and Gemini speech paths, then the full paste path vs today's setup.

Pytest does not collect this file. One pass over the four say clips in
benchmarks/model_benchmark.py. Live arms stream 16 kHz PCM at 1x and time
finish() after the last chunk. File arms time the request that starts only
after the clip exists. Gemini smart is the pasted text. Mistral and the
current Groq path then run the configured cleanup.
"""

import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.model_benchmark import SAMPLES, _meaningful_words_exact, _quality_score
from app.cleanup import create_cleanup
from app.config import load_config
from app.transcriber import create_transcriber


def _say_wav(sample: dict, directory: Path) -> Path:
    aiff = directory / f"{sample['id']}.aiff"
    wav = directory / f"{sample['id']}.wav"
    voices = [sample["voice"]]
    if sample["language"] == "de":
        voices.append("Anna")
    voices.append("Samantha")
    last_error = None
    for voice in voices:
        try:
            subprocess.run(["say", "-v", voice, "-o", str(aiff), sample["text"]], check=True)
            break
        except subprocess.CalledProcessError as exc:
            last_error = exc
    else:
        raise SystemExit(f"say failed for {sample['id']}: {last_error}")
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
        check=True,
    )
    return wav


def _wav_pcm(path: Path) -> tuple[bytes, float]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        if rate != 16000 or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise SystemExit(f"{path.name} is not 16 kHz mono 16-bit")
        frames = handle.getnframes()
        return handle.readframes(frames), frames / rate


def _stream(session, pcm: bytes, rate: int = 16000) -> None:
    frame_bytes = 1024 * 2
    for start in range(0, len(pcm), frame_bytes):
        chunk = pcm[start : start + frame_bytes]
        session.write_pcm(chunk)
        time.sleep(len(chunk) / 2 / rate)


def _live(transcriber, pcm: bytes) -> tuple[str, str, float, str]:
    session = transcriber.open_live_session()
    try:
        if not session.wait_until_ready(20):
            return "", "", 0.0, "setup failed"
        _stream(session, pcm)
        started = time.perf_counter()
        result = session.finish()
        return result.text, result.language, time.perf_counter() - started, ""
    except Exception as exc:
        return "", "", 0.0, exc.__class__.__name__
    finally:
        session.close()


def _file(transcriber, wav_path: Path) -> tuple[str, str, float, str]:
    try:
        started = time.perf_counter()
        result = transcriber.transcribe(wav_path.read_bytes())
        return result.text, result.language, time.perf_counter() - started, ""
    except Exception as exc:
        return "", "", 0.0, exc.__class__.__name__


def _cleanup(cleaner, text: str, language: str) -> tuple[str, float, str]:
    if not text.strip():
        return "", 0.0, "empty"
    try:
        started = time.perf_counter()
        result = cleaner.clean(text, language)
        return result.text, time.perf_counter() - started, ""
    except Exception as exc:
        return text, 0.0, exc.__class__.__name__


def _row(arm: str, sample: dict, text: str, wait_s: float, audio_s: float, error: str) -> dict:
    return {
        "arm": arm,
        "sample": sample["id"],
        "language": sample["language"],
        "audio_s": round(audio_s, 2),
        "wait_s": None if error else round(wait_s, 3),
        "quality": None if error else _quality_score(sample["text"], text),
        "exact": None if error else _meaningful_words_exact(sample["text"], text),
        "error": error,
        "text": text,
    }


def _mean(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None and not row.get("error")]
    if not values:
        return None
    return sum(values) / len(values)


def _print_table(title: str, rows: list[dict], wait_key: str) -> None:
    print(f"\n{title}")
    print(f"{'arm':<28} {'sample':<16} {'audio':>6} {wait_key:>8} {'quality':>8} exact")
    for row in rows:
        wait = "-" if row[wait_key] is None else f"{row[wait_key]:.3f}"
        quality = "-" if row["quality"] is None else f"{row['quality']:.3f}"
        exact = "-" if row["exact"] is None else ("yes" if row["exact"] else "no")
        error = f"  {row['error']}" if row["error"] else ""
        print(f"{row['arm']:<28} {row['sample']:<16} {row['audio_s']:6.2f} {wait:>8} {quality:>8} {exact}{error}")


def main() -> int:
    cfg = load_config()
    if not cfg.mistral_api_key or not cfg.gemini_api_key or not cfg.groq_api_key:
        print("missing mistral, gemini, or groq key")
        return 1
    cleanup_model = cfg.cleanup.model
    cleanup_key = {
        "cerebras": cfg.cerebras_api_key,
        "groq": cfg.groq_api_key,
        "mistral": cfg.mistral_api_key,
    }.get(cfg.cleanup.provider, "")
    cleaner = create_cleanup(cfg.cleanup.provider, cleanup_key, cleanup_model, enabled=cfg.cleanup.enabled)
    existing_name = f"existing {cfg.transcription.provider} {cfg.transcription.model}"
    existing = create_transcriber(
        provider=cfg.transcription.provider,
        mistral_api_key=cfg.mistral_api_key,
        groq_api_key=cfg.groq_api_key,
        gemini_api_key=cfg.gemini_api_key,
        model=cfg.transcription.model,
        allowed_languages=cfg.transcription.allowed_languages,
        fallback_languages=cfg.transcription.fallback_languages,
        language=cfg.transcription.language,
        mode=cfg.transcription.mode,
        vocabulary=cfg.vocabulary,
    )
    mistral_file = create_transcriber(
        provider="mistral",
        mistral_api_key=cfg.mistral_api_key,
        model="voxtral-mini-2602",
        vocabulary=cfg.vocabulary,
    )
    mistral_live = create_transcriber(
        provider="mistral",
        mistral_api_key=cfg.mistral_api_key,
        model="voxtral-mini-2602",
        vocabulary=cfg.vocabulary,
    )
    gemini_file = create_transcriber(
        provider="gemini",
        gemini_api_key=cfg.gemini_api_key,
        model="gemini-3.5-transcribe",
        mode="smart",
        allowed_languages=cfg.transcription.allowed_languages,
        vocabulary=cfg.vocabulary,
    )
    gemini_live = create_transcriber(
        provider="gemini",
        gemini_api_key=cfg.gemini_api_key,
        model="gemini-3.5-transcribe",
        mode="smart",
        allowed_languages=cfg.transcription.allowed_languages,
        vocabulary=cfg.vocabulary,
    )

    speech_rows = []
    pipeline_rows = []
    with tempfile.TemporaryDirectory(prefix="yap-compare-") as directory:
        folder = Path(directory)
        for sample in SAMPLES:
            wav_path = _say_wav(sample, folder)
            pcm, audio_s = _wav_pcm(wav_path)
            print(f"sample={sample['id']} audio_s={audio_s:.2f}", flush=True)

            speech_runs = [
                ("mistral file voxtral-mini-2602", *_file(mistral_file, wav_path)),
                ("mistral realtime", *_live(mistral_live, pcm)),
                ("gemini file 3.5-transcribe smart", *_file(gemini_file, wav_path)),
                ("gemini live 3.5-transcribe-live", *_live(gemini_live, pcm)),
            ]
            for arm, text, language, wait_s, error in speech_runs:
                speech_rows.append(_row(arm, sample, text, wait_s, audio_s, error))
                print(f"  speech {arm} wait={wait_s:.3f} err={error or '-'} text={text}", flush=True)

            current_text, current_language, current_wait, current_error = _file(existing, wav_path)
            pipeline_specs = [
                (existing_name, current_text, current_language, current_wait, current_error, True),
                ("mistral realtime + cleanup", speech_runs[1][1], speech_runs[1][2], speech_runs[1][3], speech_runs[1][4], True),
                ("gemini live smart", speech_runs[3][1], speech_runs[3][2], speech_runs[3][3], speech_runs[3][4], False),
            ]
            for arm, text, language, asr_wait, error, needs_cleanup in pipeline_specs:
                cleanup_s = 0.0
                pasted = text
                cleanup_error = ""
                if error:
                    pasted = ""
                elif needs_cleanup:
                    pasted, cleanup_s, cleanup_error = _cleanup(cleaner, text, language or sample["language"])
                row = _row(arm, sample, pasted, asr_wait + cleanup_s, audio_s, error or cleanup_error)
                row["asr_wait_s"] = None if error else round(asr_wait, 3)
                row["cleanup_s"] = None if error or cleanup_error else round(cleanup_s, 3)
                pipeline_rows.append(row)
                print(
                    f"  pipeline {arm} release={row['wait_s']} cleanup={row['cleanup_s']} err={row['error'] or '-'}",
                    flush=True,
                )

    _print_table("Speech models. wait is the request after the clip, or finish() after the last live chunk.", speech_rows, "wait_s")
    print("\nSpeech means")
    for arm in dict.fromkeys(row["arm"] for row in speech_rows):
        rows = [row for row in speech_rows if row["arm"] == arm]
        quality = _mean(rows, "quality")
        wait = _mean(rows, "wait_s")
        print(f"  {arm}: quality={quality:.3f} wait={wait:.3f}" if quality is not None and wait is not None else f"  {arm}: failed")

    _print_table(
        f"Whole pipeline vs existing. Cleanup is {cfg.cleanup.provider} {cleanup_model}. Gemini smart has no second call.",
        pipeline_rows,
        "wait_s",
    )
    print("\nPipeline means. wait is release-to-paste.")
    for arm in dict.fromkeys(row["arm"] for row in pipeline_rows):
        rows = [row for row in pipeline_rows if row["arm"] == arm]
        quality = _mean(rows, "quality")
        wait = _mean(rows, "wait_s")
        print(f"  {arm}: quality={quality:.3f} release={wait:.3f}" if quality is not None and wait is not None else f"  {arm}: failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
