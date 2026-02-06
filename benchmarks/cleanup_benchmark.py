#!/usr/bin/env python3
"""Benchmark cleanup providers: Groq vs Claude Haiku vs Mistral Small.

Sends sample raw transcripts to each provider and compares latency + quality.
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

CLEANUP_PROMPT = (
    "Clean up this raw speech transcript. Remove filler words (um, uh, like, you know), "
    "fix grammar and punctuation, but keep the original language and meaning. "
    "Do NOT translate. Do NOT add anything. Return ONLY the cleaned text, nothing else."
)

SAMPLES = [
    {
        "label": "English - technical",
        "text": (
            "so um I was thinking we should uh use Claude Code for this project "
            "because like it has really good you know context understanding and uh "
            "it can work with the CLAUDE.md file to understand the project better"
        ),
        "language": "en",
    },
    {
        "label": "English - casual",
        "text": (
            "hey so I just wanted to um let you know that the the meeting is uh "
            "moved to like 3 PM tomorrow and uh yeah we should probably prepare "
            "the the slides before then you know"
        ),
        "language": "en",
    },
    {
        "label": "German - technical",
        "text": (
            "also ähm ich denke wir sollten die die API Schnittstelle äh neu "
            "gestalten weil ähm die aktuelle Version ist halt nicht mehr zeitgemäß "
            "und äh ja wir brauchen bessere Fehlerbehandlung"
        ),
        "language": "de",
    },
    {
        "label": "Mixed - short",
        "text": "uh remind me to buy milk and uh eggs tomorrow morning",
        "language": "en",
    },
]


def benchmark_groq(text: str, language: str) -> tuple[str, float]:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CLEANUP_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    latency = time.perf_counter() - t0
    return resp.choices[0].message.content.strip(), latency


def benchmark_mistral(text: str, language: str) -> tuple[str, float]:
    from mistralai import Mistral

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    t0 = time.perf_counter()
    resp = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "system", "content": CLEANUP_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    latency = time.perf_counter() - t0
    return resp.choices[0].message.content.strip(), latency


def benchmark_haiku(text: str, language: str) -> tuple[str, float]:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    t0 = time.perf_counter()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=CLEANUP_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    latency = time.perf_counter() - t0
    return resp.content[0].text.strip(), latency


PROVIDERS = {
    "Groq (llama-3.3-70b)": benchmark_groq,
    "Mistral Small": benchmark_mistral,
    "Claude Haiku 4.5": benchmark_haiku,
}


def main():
    print("=== Cleanup Provider Benchmark ===\n")

    # Check which providers have API keys
    available = {}
    for name, fn in PROVIDERS.items():
        if name.startswith("Groq") and os.environ.get("GROQ_API_KEY"):
            available[name] = fn
        elif name.startswith("Mistral") and os.environ.get("MISTRAL_API_KEY"):
            available[name] = fn
        elif name.startswith("Claude") and os.environ.get("ANTHROPIC_API_KEY"):
            available[name] = fn

    if not available:
        print("Error: No API keys found. Set GROQ_API_KEY, MISTRAL_API_KEY, or ANTHROPIC_API_KEY.")
        sys.exit(1)

    print(f"Testing providers: {', '.join(available.keys())}\n")

    for sample in SAMPLES:
        print(f"--- {sample['label']} ---")
        print(f"Raw: {sample['text']}\n")

        for provider_name, fn in available.items():
            try:
                cleaned, latency = fn(sample["text"], sample["language"])
                print(f"  {provider_name}:")
                print(f"    Latency: {latency:.2f}s")
                print(f"    Output:  {cleaned}")
                print()
            except Exception as e:
                print(f"  {provider_name}: ERROR - {e}\n")

        print()

    print("Done.")


if __name__ == "__main__":
    main()
