# Yap pipeline benchmark

Date: 2026-08-09

## Cleanup corpus

The live run used Yap's deterministic 50-case English/German cleanup corpus (10 semantic utterances × 5 filler variants), identical prompts, and serial requests. Quality is a token-sequence similarity against the expected cleaned text; it is a diagnostic score, not a human WER or a promotion guarantee.

| Provider/model | Samples | Errors | Fallbacks | Mean quality | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cerebras `gpt-oss-120b` | 50 | 0 | 0 | 0.998 | 0.45 s | 0.59 s |
| Groq `openai/gpt-oss-120b` | 50 | 0 | 0 | 0.996 | 1.82 s | 4.95 s |
| Mistral `mistral-small-latest` (after wrapper guard) | 50 | 0 | 0 | 0.996 | 0.54 s | 0.64 s |

The first Mistral run exposed a real integration issue: the model sometimes returned the `<transcript>` delimiters. Yap now strips only an accidental outer wrapper without rewriting the content. The rerun brought its mean diagnostic score from 0.920 to 0.996. Cerebras was the fastest and most stable in this run, but the corpus is synthetic and short; it does not justify changing the default by itself.

## ASR smoke corpus

The separate four-case `say`-generated English/German ASR smoke run was too small for a quality decision. It produced the following indicative averages:

| Provider/model | Mean latency | Mean diagnostic score |
| --- | ---: | ---: |
| Mistral `voxtral-mini-2602` | 0.81 s | 0.925 |
| Mistral `voxtral-mini-latest` | 0.73 s | 0.925 |
| Groq `whisper-large-v3-turbo` | 0.61 s | 0.914 |
| Groq `whisper-large-v3` | 0.48 s | 0.902 |

The cases included project terminology, a scheduling question, and German technical prose. They are synthesized speech, not the user's microphone recordings, so the next quality decision should use real Yap recordings and human review of names, accents, and noisy segments. Groq's API documentation recommends the full `whisper-large-v3` model when accuracy is more important than speed, while Turbo is the cost/performance option ([Groq Speech to Text](https://console.groq.com/docs/speech-to-text)).

## Current decision

- Keep Groq Whisper Turbo as the ASR default; add vocabulary prompting and retain the language guard.
- Keep Cerebras GPT‑OSS as an opt-in cleanup provider. The live corpus supports continuing the trial, not silently promoting it.
- Keep Mistral cleanup available; its wrapper issue is fixed.
- The retired Groq Llama 4 Scout cleanup ID is migrated to `openai/gpt-oss-120b`, which Groq lists as a current production model. See [Groq model deprecations](https://console.groq.com/docs/deprecations) and [supported models](https://console.groq.com/docs/models).
- Use `~/.config/yap/pipeline_metrics.jsonl` for real release-to-paste p50/p95 measurements. It contains timings and diagnostics only, not transcript text.
