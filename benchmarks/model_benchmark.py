#!/usr/bin/env python3
"""Benchmark Yap transcription and cleanup model candidates.

The benchmark uses deterministic macOS `say` fixtures by default so provider
latency and obvious language/correctness issues can be compared repeatably.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cleanup import GroqCleanup
from app.transcriber import GroqTranscriber, Transcriber

ASR_CANDIDATES = [
    ("mistral", "voxtral-mini-2602"),
    ("mistral", "voxtral-mini-latest"),
    ("groq", "whisper-large-v3-turbo"),
    ("groq", "whisper-large-v3"),
]

CLEANUP_CANDIDATES = [
    ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("groq", "openai/gpt-oss-20b"),
    ("groq", "llama-3.1-8b-instant"),
    ("groq", "llama-3.3-70b-versatile"),
]

SAMPLES = [
    {
        "id": "en_technical",
        "language": "en",
        "voice": "Samantha",
        "text": (
            "I think we should use Claude Code for this project because it understands "
            "the repository context and the AGENTS file very well."
        ),
        "raw_cleanup": (
            "so um I think we should uh use Claude Code for this project because like "
            "it understands the repository context and the AGENTS file very well"
        ),
    },
    {
        "id": "en_casual",
        "language": "en",
        "voice": "Samantha",
        "text": "Can you move the meeting to three PM tomorrow and send me the updated notes?",
        "raw_cleanup": (
            "can you um move the the meeting to three PM tomorrow and uh send me the "
            "updated notes"
        ),
    },
    {
        "id": "de_technical",
        "language": "de",
        "voice": "Anna",
        "text": (
            "Ich denke, wir sollten die API Schnittstelle neu gestalten, weil die "
            "aktuelle Version bessere Fehlerbehandlung braucht."
        ),
        "raw_cleanup": (
            "also ähm ich denke wir sollten die die API Schnittstelle äh neu gestalten "
            "weil die aktuelle Version halt bessere Fehlerbehandlung braucht"
        ),
    },
    {
        "id": "de_casual",
        "language": "de",
        "voice": "Anna",
        "text": "Kannst du den Termin auf morgen um zehn Uhr verschieben?",
        "raw_cleanup": "ähm kannst du den den Termin auf morgen um zehn Uhr verschieben",
    },
]


@dataclass
class Result:
    stage: str
    provider: str
    model: str
    sample_id: str
    language: str
    latency_s: float | None
    output: str
    error: str = ""


def _load_env() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")


def _run_say(text: str, voice: str, output: Path) -> None:
    cmd = ["say", "-v", voice, "-o", str(output), text]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _aiff_to_wav_bytes(path: Path) -> bytes:
    # soundfile is already a runtime dependency and handles AIFF reliably.
    import soundfile as sf

    data, sample_rate = sf.read(path, dtype="int16", always_2d=True)
    with tempfile.NamedTemporaryFile(suffix=".wav") as out:
        with wave.open(out.name, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(data[:, 0].tobytes())
        return Path(out.name).read_bytes()


def build_audio_fixtures() -> dict[str, bytes]:
    fixtures = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for sample in SAMPLES:
            aiff = tmp_path / f"{sample['id']}.aiff"
            try:
                _run_say(sample["text"], sample["voice"], aiff)
            except subprocess.CalledProcessError:
                fallback_voice = "Samantha" if sample["language"] == "en" else "Anna"
                _run_say(sample["text"], fallback_voice, aiff)
            fixtures[sample["id"]] = _aiff_to_wav_bytes(aiff)
    return fixtures


def transcribe(provider: str, model: str, wav_bytes: bytes) -> tuple[str, str, float]:
    if provider == "mistral":
        transcriber = Transcriber(
            api_key=os.environ["MISTRAL_API_KEY"],
            model=model,
            vocabulary=["Claude Code", "AGENTS", "API", "Yap", "Voxtral", "Groq"],
        )
    elif provider == "groq":
        transcriber = GroqTranscriber(api_key=os.environ["GROQ_API_KEY"], model=model)
    else:
        raise ValueError(f"Unknown ASR provider: {provider}")

    result = transcriber.transcribe(wav_bytes)
    return result.text, result.language, result.latency


def clean(provider: str, model: str, text: str, language: str) -> tuple[str, float]:
    if provider != "groq":
        raise ValueError(f"Unknown cleanup provider: {provider}")
    cleanup = GroqCleanup(api_key=os.environ["GROQ_API_KEY"], model=model)
    result = cleanup.clean(text, language)
    return result.text, result.latency


def run_asr() -> list[Result]:
    available = {
        "mistral": bool(os.environ.get("MISTRAL_API_KEY")),
        "groq": bool(os.environ.get("GROQ_API_KEY")),
    }
    fixtures = build_audio_fixtures()
    results: list[Result] = []

    for provider, model in ASR_CANDIDATES:
        if not available.get(provider):
            continue
        for sample in SAMPLES:
            try:
                text, detected_language, latency = transcribe(provider, model, fixtures[sample["id"]])
                results.append(
                    Result(
                        stage="asr",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=detected_language or sample["language"],
                        latency_s=latency,
                        output=text,
                    )
                )
            except Exception as exc:
                results.append(
                    Result(
                        stage="asr",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=sample["language"],
                        latency_s=None,
                        output="",
                        error=str(exc),
                    )
                )
    return results


def run_cleanup() -> list[Result]:
    if not os.environ.get("GROQ_API_KEY"):
        return []

    results: list[Result] = []
    for provider, model in CLEANUP_CANDIDATES:
        for sample in SAMPLES:
            try:
                text, latency = clean(provider, model, sample["raw_cleanup"], sample["language"])
                results.append(
                    Result(
                        stage="cleanup",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=sample["language"],
                        latency_s=latency,
                        output=text,
                    )
                )
            except Exception as exc:
                results.append(
                    Result(
                        stage="cleanup",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=sample["language"],
                        latency_s=None,
                        output="",
                        error=str(exc),
                    )
                )
    return results


def print_results(results: list[Result]) -> None:
    for result in results:
        latency = "error" if result.latency_s is None else f"{result.latency_s:.2f}s"
        print(f"[{result.stage}] {result.provider}/{result.model} {result.sample_id} {latency}")
        if result.error:
            print(f"  ERROR: {result.error}")
        else:
            print(f"  {result.output}")
        print()


def write_json(results: list[Result], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["all", "asr", "cleanup"], default="all")
    parser.add_argument("--json", type=Path, default=ROOT / "benchmarks" / "last_model_benchmark.json")
    args = parser.parse_args()

    _load_env()

    results: list[Result] = []
    if args.stage in ("all", "asr"):
        results.extend(run_asr())
    if args.stage in ("all", "cleanup"):
        results.extend(run_cleanup())

    print_results(results)
    write_json(results, args.json)
    print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
