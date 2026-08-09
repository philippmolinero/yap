# Yap pipeline improvements

Date: 2026-08-09

This note records the implementation boundary for the six Yap follow-up tasks.

## Implemented in the current source tree

- Cleanup responses are treated as untrusted transcript data. The prompt forbids answering or summarizing the dictated text and requires the complete transcript to survive.
- Cerebras cleanup starts with a bounded completion budget, retries transient HTTP/network failures, retries a length-truncated completion with a larger bound, and pastes the raw transcript if the response is still incomplete or meta-text.
- Cleanup results now carry provider, model, finish reason, attempt count, and fallback reason. Pipeline logs record those diagnostics without transcript content.
- The bundled Groq cleanup model was moved from retired Llama 4 Scout to production `openai/gpt-oss-120b`; existing installs migrate the retired ID in memory.
- Settings now persists the cleanup model alongside the provider, so `gpt-oss-120b`, Gemma, and other explicitly configured models are not silently overwritten.
- Groq Whisper requests now use `temperature=0`, the configured vocabulary as a short spelling prompt, and `verbose_json` quality metadata. An optional `[transcription].language` ISO-639-1 hint is available for single-language workflows; blank keeps automatic detection. The existing language guard remains in place.
- The app writes mode-0600, transcript-free stage measurements to `~/.config/yap/pipeline_metrics.jsonl`. Each record includes audio duration, recorder-stop time, ASR time, cleanup time, total time, provider/model IDs, language, character count, and error/fallback reasons.
- The benchmark harness now has a deterministic 50-case English/German cleanup corpus, p50/p95 latency, quality similarity, error/fallback counts, and an optional JSON corpus input for real recordings.

## ASR quality boundary

Groq remains the default ASR route. Vocabulary prompting is a low-risk accuracy improvement for names and project terms; the benchmark can compare it with Mistral Voxtral and Groq `whisper-large-v3`. A larger ASR model should only be used as an explicit quality fallback because it increases cost and latency. The benchmark output, rather than provider marketing WER, is the decision evidence for that change.

Run a local smoke comparison with keys already configured in Yap:

```bash
.venv/bin/python benchmarks/model_benchmark.py --stage cleanup --limit 10 --json /tmp/yap-cleanup-smoke.json
```

Use `--cleanup-corpus path/to/corpus.json` for a user-recorded corpus. Entries require `id`, `language`, `raw_cleanup`, and `expected_cleanup`.

## Voxtral Realtime decision

Mistral's official Realtime API exposes `voxtral-mini-transcribe-realtime-2602` over a WebSocket and emits transcription text deltas while PCM audio is sent. The documented Python client accepts 16 kHz PCM and a configurable `target_streaming_delay_ms`; see the [Realtime transcription guide](https://docs.mistral.ai/studio-api/audio/speech_to_text/realtime_transcription) and [client authentication guide](https://docs.mistral.ai/studio-api/audio/speech_to_text/realtime_transcription/client_auth).

It is technically a fit for *live preview*, but not a drop-in replacement for Yap's current atomic workflow:

1. The recorder would need to send audio frames continuously while the Right Option key is held.
2. Partial deltas would need a draft buffer and overlay; they must not be pasted because later deltas can revise earlier words.
3. On release, Yap would need to wait for the final event, run cleanup once, and paste exactly one final string.
4. Cancellation, reconnects, duplicate final events, and a network failure during an active recording would need explicit state handling.

The current product requirement is final dictation pasted after release, not live captions. Therefore Realtime remains an opt-in future UX experiment, while the batch Voxtral/Groq path stays the production path. This preserves the simple atomic paste contract and avoids paying for streaming complexity without a visible user benefit.

## Promotion gate

Do not change the default cleanup or ASR provider from these code changes alone. Promote a model only after a representative corpus shows acceptable meaningful-word preservation, punctuation, prompt-shaped dictation handling, p50/p95 release-to-paste latency, fallback/error rate, and cost. The local measurements are the authoritative evidence; advertised tokens-per-second figures are not.
