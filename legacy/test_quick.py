#!/usr/bin/env python3
"""Quick non-interactive latency test — records 5 seconds then transcribes."""

import io
import os
import sys
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import File

load_dotenv()

SAMPLE_RATE = 16000
CHANNELS = 1
MODEL = "voxtral-mini-latest"
DURATION = 8  # seconds

api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    print("Error: MISTRAL_API_KEY not set.")
    sys.exit(1)

client = Mistral(api_key=api_key)

print(f"Recording {DURATION}s — speak now!")
audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32")
sd.wait()
print("Recording done.")

buf = io.BytesIO()
sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
wav_bytes = buf.getvalue()

audio_duration = len(audio) / SAMPLE_RATE
print(f"Audio: {audio_duration:.1f}s ({len(wav_bytes)/1024:.0f} KB)")

file = File(file_name="recording.wav", content=wav_bytes, content_type="audio/wav")

print("Sending to Voxtral…")
t0 = time.perf_counter()
res = client.audio.transcriptions.complete(model=MODEL, file=file)
api_latency = time.perf_counter() - t0

print()
print(f"Language:       {res.language}")
print(f"Transcript:     {res.text}")
print()
print(f"Audio duration:  {audio_duration:.1f}s")
print(f"API latency:     {api_latency:.2f}s")
print(f"Realtime factor: {api_latency / audio_duration:.2f}x")
