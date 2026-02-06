#!/usr/bin/env python3
"""Voxtral Transcribe V2 latency test — record mic audio and measure round-trip time."""

import io
import os
import sys
import time
import threading

import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import File

load_dotenv()

SAMPLE_RATE = 16000
CHANNELS = 1
MODEL = "voxtral-mini-latest"


def get_client() -> Mistral:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("Error: MISTRAL_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    return Mistral(api_key=api_key)


def record_audio() -> bytes:
    """Record mic audio until Enter is pressed. Returns WAV bytes."""
    frames: list = []
    stop_event = threading.Event()

    def callback(indata, frame_count, time_info, status):
        if status:
            print(f"  ⚠ {status}", file=sys.stderr)
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=callback,
    )

    print("🎙  Recording… press Enter to stop.")
    stream.start()
    input()
    stream.stop()
    stream.close()
    stop_event.set()

    if not frames:
        return b""

    import numpy as np
    audio = np.concatenate(frames, axis=0)

    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    wav_bytes = buf.getvalue()

    duration = len(audio) / SAMPLE_RATE
    size_kb = len(wav_bytes) / 1024
    print(f"  Recorded {duration:.1f}s ({size_kb:.0f} KB)")

    return wav_bytes


def transcribe(client: Mistral, wav_bytes: bytes) -> None:
    """Send WAV to Voxtral and print results with timing."""
    file = File(
        file_name="recording.wav",
        content=wav_bytes,
        content_type="audio/wav",
    )

    print("  Sending to Voxtral…")
    t0 = time.perf_counter()
    res = client.audio.transcriptions.complete(model=MODEL, file=file)
    api_latency = time.perf_counter() - t0

    audio_duration = len(wav_bytes) / (SAMPLE_RATE * 2)  # 16-bit PCM = 2 bytes/sample

    print()
    print(f"  Language:   {res.language}")
    print(f"  Transcript: {res.text}")
    print()
    print(f"  Audio duration:  {audio_duration:.1f}s")
    print(f"  API latency:     {api_latency:.2f}s")
    print(f"  Realtime factor: {api_latency / audio_duration:.2f}x" if audio_duration > 0 else "")
    print()


def main():
    print("=== Voxtral Transcribe V2 — Latency Test ===")
    print()

    client = get_client()

    while True:
        input("Press Enter to start recording (Ctrl+C to quit)… ")
        wav_bytes = record_audio()

        if not wav_bytes:
            print("  No audio captured, try again.")
            continue

        transcribe(client, wav_bytes)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDone.")
