"""See whether Cerebras cleanup still changes Mistral Realtime and Gemini Live text.

Speaks one clean line and two filler lines. Prints the live transcript and the
same text after the configured cleanup pass. Pytest does not collect this file.
"""

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cleanup import create_cleanup
from app.config import load_config
from app.transcriber import create_transcriber
from scripts.compare_dictation_paths import _live, _say_wav, _wav_pcm

CASES = [
    {
        "id": "en_clean",
        "language": "en",
        "voice": "Samantha",
        "text": "Can you move the meeting to three PM tomorrow and send me the updated notes?",
    },
    {
        "id": "en_filler",
        "language": "en",
        "voice": "Samantha",
        "text": (
            "so um I think we should uh use Claude Code for this project because like "
            "it understands the repository context and the AGENTS file very well"
        ),
    },
    {
        "id": "de_filler",
        "language": "de",
        "voice": "Anna",
        "text": (
            "also ähm ich denke wir sollten die die API Schnittstelle äh neu gestalten "
            "weil die aktuelle Version halt bessere Fehlerbehandlung braucht"
        ),
    },
]


def _show(label: str, before: str, after: str, cleanup_s: float) -> None:
    changed = before.strip() != after.strip()
    print(f"  {label}")
    print(f"    live:    {before}")
    print(f"    cleanup: {after}")
    print(f"    changed={changed} cleanup_s={cleanup_s:.3f}")


def main() -> int:
    cfg = load_config()
    cleanup_key = {
        "cerebras": cfg.cerebras_api_key,
        "groq": cfg.groq_api_key,
        "mistral": cfg.mistral_api_key,
    }.get(cfg.cleanup.provider, "")
    cleaner = create_cleanup(
        cfg.cleanup.provider,
        cleanup_key,
        cfg.cleanup.model,
        enabled=cfg.cleanup.enabled,
    )
    mistral = create_transcriber(provider="mistral", mistral_api_key=cfg.mistral_api_key, model="voxtral-mini-2602")
    gemini = create_transcriber(
        provider="gemini",
        gemini_api_key=cfg.gemini_api_key,
        model="gemini-3.5-transcribe",
        mode="smart",
        allowed_languages=cfg.transcription.allowed_languages,
    )
    with tempfile.TemporaryDirectory(prefix="yap-cleanup-need-") as directory:
        folder = Path(directory)
        for case in CASES:
            wav = _say_wav(case, folder)
            pcm, audio_s = _wav_pcm(wav)
            print(f"\n{case['id']} audio_s={audio_s:.2f}")
            print(f"  spoken: {case['text']}")
            for label, transcriber in (("mistral realtime", mistral), ("gemini live smart", gemini)):
                text, language, wait_s, error = _live(transcriber, pcm)
                if error:
                    print(f"  {label} error={error}")
                    continue
                started = time.perf_counter()
                result = cleaner.clean(text, language or case["language"])
                cleanup_s = time.perf_counter() - started
                print(f"    asr_wait_s={wait_s:.3f}")
                _show(label, text, result.text, cleanup_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
