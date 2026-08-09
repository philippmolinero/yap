#!/usr/bin/env python3
"""Benchmark Yap transcription and cleanup model candidates.

The benchmark uses deterministic macOS `say` fixtures by default so provider
latency and obvious language/correctness issues can be compared repeatably.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import statistics
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

from app.cleanup import CerebrasCleanup, CleanupResult, GroqCleanup, MistralCleanup
from app.transcriber import GroqTranscriber, Transcriber, TranscriptionResult

ASR_CANDIDATES = [
    ("mistral", "voxtral-mini-2602"),
    ("mistral", "voxtral-mini-latest"),
    ("groq", "whisper-large-v3-turbo"),
    ("groq", "whisper-large-v3"),
]

CLEANUP_CANDIDATES = [
    ("groq", "openai/gpt-oss-120b"),
    ("groq", "openai/gpt-oss-20b"),
    ("groq", "llama-3.1-8b-instant"),
    ("groq", "llama-3.3-70b-versatile"),
    ("mistral", "mistral-small-latest"),
    ("cerebras", "gpt-oss-120b"),
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

_CLEANUP_BASE_CASES = [
    {
        "id": "en_release",
        "language": "en",
        "raw": "I think we should ship the release on Friday.",
        "expected": "I think we should ship the release on Friday.",
    },
    {
        "id": "en_question",
        "language": "en",
        "raw": "Can you move the customer call to three PM tomorrow?",
        "expected": "Can you move the customer call to three PM tomorrow?",
    },
    {
        "id": "en_terms",
        "language": "en",
        "raw": "Use Cerebras, Voxtral Realtime, and the Yap pipeline for the test.",
        "expected": "Use Cerebras, Voxtral Realtime, and the Yap pipeline for the test.",
    },
    {
        "id": "en_quoted_request",
        "language": "en",
        "raw": "Please create a short overview of the project constraints.",
        "expected": "Please create a short overview of the project constraints.",
    },
    {
        "id": "en_stutter",
        "language": "en",
        "raw": "We need to to review the review queue before launch.",
        "expected": "We need to review the review queue before launch.",
    },
    {
        "id": "de_release",
        "language": "de",
        "raw": "Wir sollten die neue Version am Freitag veröffentlichen.",
        "expected": "Wir sollten die neue Version am Freitag veröffentlichen.",
    },
    {
        "id": "de_question",
        "language": "de",
        "raw": "Kannst du den Kundentermin auf morgen um zehn Uhr verschieben?",
        "expected": "Kannst du den Kundentermin auf morgen um zehn Uhr verschieben?",
    },
    {
        "id": "de_terms",
        "language": "de",
        "raw": "Wir testen Cerebras zusammen mit Voxtral Realtime im Yap-Projekt.",
        "expected": "Wir testen Cerebras zusammen mit Voxtral Realtime im Yap-Projekt.",
    },
    {
        "id": "de_quoted_request",
        "language": "de",
        "raw": "Bitte erstelle eine kurze Übersicht über die Projektgrenzen.",
        "expected": "Bitte erstelle eine kurze Übersicht über die Projektgrenzen.",
    },
    {
        "id": "de_stutter",
        "language": "de",
        "raw": "Wir müssen die die Vertriebsliste vor dem Start noch einmal prüfen.",
        "expected": "Wir müssen die Vertriebsliste vor dem Start noch einmal prüfen.",
    },
]

_FILLER_PREFIXES = [
    "so um ",
    "uh ",
    "actually ",
    "you know ",
    "also ähm ",
]


def build_cleanup_samples() -> list[dict]:
    """Build a deterministic 50-case cleanup corpus for provider comparisons."""
    samples = []
    for base in _CLEANUP_BASE_CASES:
        for variant, prefix in enumerate(_FILLER_PREFIXES, start=1):
            samples.append(
                {
                    "id": f"{base['id']}_{variant}",
                    "language": base["language"],
                    "raw_cleanup": prefix + base["raw"],
                    "expected_cleanup": base["expected"],
                }
            )
    return samples


CLEANUP_SAMPLES = build_cleanup_samples()


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
    expected: str = ""
    quality_score: float | None = None
    fallback_reason: str = ""


def _normalize_for_score(text: str) -> list[str]:
    return " ".join(text.casefold().split()).strip(" .?!,;:").split()


def _quality_score(expected: str, output: str) -> float | None:
    if not expected or not output:
        return None
    return difflib.SequenceMatcher(
        a=_normalize_for_score(expected),
        b=_normalize_for_score(output),
    ).ratio()


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def summarize(results: list[Result]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[Result]] = {}
    for result in results:
        groups.setdefault((result.stage, result.provider, result.model), []).append(result)
    summary = []
    for (stage, provider, model), items in sorted(groups.items()):
        latencies = [item.latency_s for item in items if item.latency_s is not None]
        scores = [item.quality_score for item in items if item.quality_score is not None]
        summary.append(
            {
                "stage": stage,
                "provider": provider,
                "model": model,
                "samples": len(items),
                "successes": len(latencies),
                "errors": sum(bool(item.error) for item in items),
                "fallbacks": sum(bool(item.fallback_reason) for item in items),
                "p50_latency_s": percentile(latencies, 0.50),
                "p95_latency_s": percentile(latencies, 0.95),
                "mean_quality_score": statistics.fmean(scores) if scores else None,
            }
        )
    return summary


def _load_env() -> None:
    load_dotenv(dotenv_path=ROOT / ".env")
    # The app stores keys in secrets.toml when configured through Settings.
    # Load their presence for a local benchmark without ever printing values.
    if not all(os.environ.get(name) for name in ("MISTRAL_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY")):
        from app.config import load_config

        config = load_config()
        os.environ.setdefault("MISTRAL_API_KEY", config.mistral_api_key)
        os.environ.setdefault("GROQ_API_KEY", config.groq_api_key)
        os.environ.setdefault("CEREBRAS_API_KEY", config.cerebras_api_key)


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


def transcribe(provider: str, model: str, wav_bytes: bytes) -> TranscriptionResult:
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
    return result


def clean(provider: str, model: str, text: str, language: str) -> CleanupResult:
    if provider == "groq":
        cleanup = GroqCleanup(api_key=os.environ["GROQ_API_KEY"], model=model)
    elif provider == "mistral":
        cleanup = MistralCleanup(api_key=os.environ["MISTRAL_API_KEY"], model=model)
    elif provider == "cerebras":
        cleanup = CerebrasCleanup(api_key=os.environ["CEREBRAS_API_KEY"], model=model)
    else:
        raise ValueError(f"Unknown cleanup provider: {provider}")
    result = cleanup.clean(text, language)
    return result


def run_asr(
    samples: list[dict] | None = None,
    candidates: list[tuple[str, str]] | None = None,
) -> list[Result]:
    available = {
        "mistral": bool(os.environ.get("MISTRAL_API_KEY")),
        "groq": bool(os.environ.get("GROQ_API_KEY")),
    }
    samples = samples or SAMPLES
    fixtures = build_audio_fixtures()
    results: list[Result] = []

    for provider, model in candidates or ASR_CANDIDATES:
        if not available.get(provider):
            continue
        for sample in samples:
            try:
                result = transcribe(provider, model, fixtures[sample["id"]])
                results.append(
                    Result(
                        stage="asr",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=result.language or sample["language"],
                        latency_s=result.latency,
                        output=result.text,
                        expected=sample.get("text", ""),
                        quality_score=_quality_score(sample.get("text", ""), result.text),
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
                        expected=sample.get("text", ""),
                    )
                )
    return results


def run_cleanup(
    samples: list[dict] | None = None,
    candidates: list[tuple[str, str]] | None = None,
) -> list[Result]:
    available = {
        "groq": bool(os.environ.get("GROQ_API_KEY")),
        "mistral": bool(os.environ.get("MISTRAL_API_KEY")),
        "cerebras": bool(os.environ.get("CEREBRAS_API_KEY")),
    }
    if not any(available.values()):
        return []

    samples = samples or CLEANUP_SAMPLES
    results: list[Result] = []
    for provider, model in candidates or CLEANUP_CANDIDATES:
        if not available.get(provider):
            continue
        for sample in samples:
            try:
                result = clean(provider, model, sample["raw_cleanup"], sample["language"])
                results.append(
                    Result(
                        stage="cleanup",
                        provider=provider,
                        model=model,
                        sample_id=sample["id"],
                        language=sample["language"],
                        latency_s=result.latency,
                        output=result.text,
                        expected=sample.get("expected_cleanup", ""),
                        quality_score=_quality_score(sample.get("expected_cleanup", ""), result.text),
                        fallback_reason=result.fallback_reason,
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
                        expected=sample.get("expected_cleanup", ""),
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
            if result.quality_score is not None:
                print(f"  quality={result.quality_score:.3f}")
            if result.fallback_reason:
                print(f"  fallback={result.fallback_reason}")
        print()


def write_json(results: list[Result], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": [asdict(result) for result in results],
        "summary": summarize(results),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_cleanup_corpus(path: Path) -> list[dict]:
    """Load a user-provided cleanup corpus with the same fields as the default."""
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Cleanup corpus must be a JSON array")
    required = {"id", "language", "raw_cleanup", "expected_cleanup"}
    missing = [str(item.get("id", "?")) for item in data if not required.issubset(item)]
    if missing:
        raise ValueError(f"Cleanup corpus entries missing fields: {', '.join(missing)}")
    return data


def parse_candidates(values: list[str] | None) -> list[tuple[str, str]] | None:
    """Parse repeated provider/model selectors such as ``cerebras:gpt-oss-120b``."""
    if not values:
        return None
    candidates = []
    for value in values:
        try:
            provider, model = value.split(":", 1)
        except ValueError as exc:
            raise SystemExit(f"Invalid --candidate {value!r}; use provider:model") from exc
        if not provider or not model:
            raise SystemExit(f"Invalid --candidate {value!r}; use provider:model")
        candidates.append((provider, model))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["all", "asr", "cleanup"], default="all")
    parser.add_argument("--json", type=Path, default=ROOT / "benchmarks" / "last_model_benchmark.json")
    parser.add_argument(
        "--cleanup-corpus",
        type=Path,
        help="JSON corpus with id, language, raw_cleanup, and expected_cleanup fields",
    )
    parser.add_argument("--limit", type=int, help="Limit each stage to the first N samples")
    parser.add_argument(
        "--candidate",
        action="append",
        help="Run only this provider:model candidate; repeat for side-by-side comparisons",
    )
    args = parser.parse_args()

    _load_env()

    cleanup_samples = load_cleanup_corpus(args.cleanup_corpus) if args.cleanup_corpus else CLEANUP_SAMPLES
    asr_samples = SAMPLES
    candidates = parse_candidates(args.candidate)
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("--limit must be positive")
        cleanup_samples = cleanup_samples[: args.limit]
        asr_samples = asr_samples[: args.limit]

    results: list[Result] = []
    if args.stage in ("all", "asr"):
        results.extend(run_asr(asr_samples, candidates))
    if args.stage in ("all", "cleanup"):
        results.extend(run_cleanup(cleanup_samples, candidates))

    print_results(results)
    write_json(results, args.json)
    print(f"Wrote {args.json}")


if __name__ == "__main__":
    main()
