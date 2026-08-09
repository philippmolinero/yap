# Yap pipeline benchmark

Date: 2026-08-09

## Cleanup corpus

The live run used Yap's expanded deterministic 50-case English/German corpus, identical prompts, and serial requests. It covers short and long dictation, names/acronyms, questions, mixed-language speech, quoted and prompt-injection-shaped speech, and the previously observed dropped-suffix failure. Quality is a punctuation-sensitive token-sequence similarity against the expected cleaned text; it is a diagnostic score, not a human WER or a promotion guarantee.

| Provider/model | Samples | Errors | Fallbacks | Mean quality | Exact meaningful words | p50 | p95 | Est. cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cerebras `gemma-4-31b` | 50 | 0 | 0 | 0.994 | 94% | 0.45 s | 1.56 s | $0.0262 |
| Cerebras `gpt-oss-120b` | 50 | 0 | 0 | 0.990 | 100%* | 0.41 s | 0.60 s | $0.0095 |
| Groq `openai/gpt-oss-120b` | 50 | 0 | 0 | 0.991 | 100% | 3.30 s | 6.26 s | $0.0045 |
| Mistral `mistral-small-latest` | 50 | 0 | 0 | 0.962 | 94% | 0.57 s | 0.79 s | $0.0044 |

The run confirms a meaningful trade-off: Gemma had the highest aggregate Cerebras quality but changed “three” to “3” in three question cases; GPT‑OSS was cheaper, faster, and preserved all normalized meaningful-word sequences, although it normalized typographic hyphens. Mistral produced likely-summary flags on 6% of cases and a punctuation mismatch on 2%. Groq had the highest p95 but no error in this rerun. Cost estimates use current first-party prices and approximate tokens, so billing exports remain the final cost authority.

\* GPT‑OSS exact-word scoring normalizes typographic hyphen variants; punctuation and wording remain separately scored.

The input framing now JSON-escapes markup so a dictated closing tag remains data. Yap also strips only an accidental outer transcript wrapper without rewriting content.

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
- Keep Cerebras GPT‑OSS as an opt-in cleanup provider. It is fast, inexpensive, and operationally clean here, but its injection-shaped summarization flag means the live corpus supports continuing the trial, not silently promoting it.
- Keep Gemma 4 as a preview-only benchmark challenger. It scored best on this corpus, but it is more expensive and preview-lifecycle risk remains unresolved; do not make it the default from one synthetic run.
- Keep Mistral cleanup available; its wrapper issue is fixed.
- The retired Groq Llama 4 Scout cleanup ID is migrated to `openai/gpt-oss-120b`, which Groq lists as a current production model. See [Groq model deprecations](https://console.groq.com/docs/deprecations) and [supported models](https://console.groq.com/docs/models).
- Use `~/.config/yap/pipeline_metrics.jsonl` for real release-to-paste p50/p95 measurements. It contains timings and diagnostics only, not transcript text.
- The benchmark's `release_to_paste_s` field is a wall-clock provider-call proxy when only one stage is selected. Use the app JSONL's `total_s` for the actual hotkey-release-to-paste decision, and inspect `cleanup_status_code`, `cleanup_request_attempts`, `cleanup_finish_reason`, and `fallback_reason` for transient and truncation behavior.
- The final summary artifact is [benchmarks/2026-08-09-cleanup-expanded-summary.json](../benchmarks/2026-08-09-cleanup-expanded-summary.json); the full raw output remains local because it contains synthetic transcript text.
