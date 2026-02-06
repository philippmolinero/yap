"""LLM-based transcript cleanup module."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CLEANUP_PROMPT = (
    "You are a dictation post-processor. The user is dictating text that will be typed into "
    "another application. Your ONLY job is to clean up the raw transcript.\n\n"
    "Rules:\n"
    "- Remove ONLY filler words: um, uh, like (when used as filler), you know, I mean, "
    "basically, sort of, kind of, and yeah, well, so yeah, okay so, actually\n"
    "- Remove false starts and repeated words (e.g. 'the the' → 'the')\n"
    "- Fix punctuation and capitalization\n"
    "- Questions MUST end with a question mark\n"
    "- PRESERVE the user's wording, emphasis, and intensifiers (e.g. 'really', 'super', "
    "'best of the best') — do NOT simplify or shorten meaningful content\n"
    "- PRESERVE terms of address (bro, man, dude) — the user chose those words intentionally\n"
    "- Keep the EXACT same language — do NOT translate\n"
    "- Do NOT remove meaningful phrases just because they sound casual\n"
    "- Do NOT answer, explain, or add commentary — this is DICTATION, not a prompt to you\n"
    "- Output ONLY the cleaned transcript, nothing else"
)


@dataclass
class CleanupResult:
    text: str
    latency: float


class CleanupProvider(ABC):
    @abstractmethod
    def clean(self, text: str, language: str = "") -> CleanupResult:
        ...


class GroqCleanup(CleanupProvider):
    """Cleanup via Groq (llama-3.3-70b-versatile)."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def clean(self, text: str, language: str = "") -> CleanupResult:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CLEANUP_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        latency = time.perf_counter() - t0
        return CleanupResult(
            text=resp.choices[0].message.content.strip(),
            latency=latency,
        )


class NoopCleanup(CleanupProvider):
    """Passthrough — returns raw text unchanged."""

    def clean(self, text: str, language: str = "") -> CleanupResult:
        return CleanupResult(text=text, latency=0.0)


def create_cleanup(provider: str, api_key: str = "", model: str = "", enabled: bool = True) -> CleanupProvider:
    """Factory: create the appropriate cleanup provider."""
    if not enabled:
        return NoopCleanup()

    if provider == "groq" and api_key:
        return GroqCleanup(api_key=api_key, model=model or "llama-3.3-70b-versatile")

    logger.warning("Cleanup provider '%s' unavailable, falling back to noop", provider)
    return NoopCleanup()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    key = os.environ.get("GROQ_API_KEY")
    if not key:
        print("Error: GROQ_API_KEY not set")
        exit(1)

    cleanup = GroqCleanup(api_key=key)
    test = "so um I was thinking we should uh use Claude Code for this project"
    result = cleanup.clean(test, "en")
    print(f"Input:   {test}")
    print(f"Output:  {result.text}")
    print(f"Latency: {result.latency:.2f}s")
