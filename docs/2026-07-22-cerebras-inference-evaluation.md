# Cerebras Inference Evaluation for Yap

Date: 2026-07-22

Purpose: evaluate Cerebras as a replacement for Groq in Yap, using current first-party Cerebras sources, and recommend the smallest useful product and implementation changes.

## Executive recommendation

Add Cerebras as an **optional transcript-cleanup provider** and benchmark it against Groq before changing Yap's default. Use `gpt-oss-120b`, the only model that Cerebras currently classifies as a production model on its shared public endpoint. Keep Groq (or Mistral) for speech-to-text: Cerebras currently exposes text Chat Completions/Completions, not an audio transcription endpoint. The current [public model catalog](https://inference-docs.cerebras.ai/models/overview) and [GPT OSS model page](https://inference-docs.cerebras.ai/models/openai-oss) list only text input/output for the production model.

The migration is technically small, but the product decision should be evidence-led. Cerebras' headline output rate is attractive, yet Yap emits short answers; network time, queue time, time to first token, and model fidelity will matter more than peak tokens per second. A side-by-side corpus benchmark is the right gate before making Cerebras the default.

There is also an immediate credential action: the Cerebras key was pasted into chat. Treat it as exposed, revoke it, and issue a new key before any implementation or testing. The exposed value was not used or written to this repository.

## What Cerebras is and where it is heading

Cerebras, founded in 2015, builds wafer-scale AI systems and sells both on-premise systems and pay-as-you-go cloud inference. Its current company positioning is an inference-and-training platform built on its CS/Wafer-Scale Engine architecture, not merely another model vendor ([company overview](https://www.cerebras.ai/company)).

Recent product signals relevant to Yap:

- 2026-07-16: Cerebras introduced dual-bucket uncached/total-token rate limiting and changed new-account trial credits. The uncached-limit rollout completes on 2026-08-17 ([change log](https://inference-docs.cerebras.ai/support/change-log)).
- 2026-06-29: Gemma 4 31B and image inputs entered public preview. Cerebras reports about 1,851 output tokens/s and a 1.5-second first answer token inclusive of reasoning in the cited benchmark ([Gemma 4 announcement](https://www.cerebras.ai/blog/gemma-4-on-cerebras-the-fastest-inference-is-now-multimodal)). This is evidence of platform expansion, but it is not a Yap cleanup benchmark.
- 2026-05-19: Kimi K2.6 entered enterprise trials at a reported 981 tokens/s; it is not a shared public model ([Kimi K2.6 announcement](https://www.cerebras.ai/blog/cerebras-kimi-k2-Enterprise)).
- 2026-04-28: Cerebras described an ecosystem strategy spanning public cloud, dedicated/on-premise models, provider abstractions, observability tools, and voice platforms ([ecosystem update](https://www.cerebras.ai/blog/ecosystem)).
- The dedicated-endpoint catalog is much broader than the shared API and includes Qwen, GPT OSS, MiniMax, Gemma, Llama, Mistral, GLM, Kimi, DeepSeek, StepFun, Seed, and Apriel families. Dedicated endpoints require enterprise engagement and are not relevant to Yap's current personal-app scale ([dedicated endpoints](https://inference-docs.cerebras.ai/dedicated/overview)).

The useful strategic signal is sustained investment in fast inference and ecosystem compatibility. The counter-signal is rapid public-model churn: several Llama, Qwen, DeepSeek, and GLM versions were deprecated during 2025-2026 ([deprecations](https://inference-docs.cerebras.ai/support/deprecation)). Yap should therefore treat provider and model as configuration, not bake a model ID into cleanup logic.

## Current shared public model support

Snapshot from the [model catalog](https://inference-docs.cerebras.ai/models/overview), model pages, and unauthenticated [public model metadata endpoint](https://api.cerebras.ai/public/v1/models), looked up on 2026-07-22. Speeds below are Cerebras-advertised generation throughput, not independently measured Yap latency:

| Model | Documented stage | Modality | Advertised speed | Paid context / max output | Developer price per 1M tokens | Yap assessment |
| --- | --- | --- | ---: | ---: | ---: | --- |
| [`gpt-oss-120b`](https://inference-docs.cerebras.ai/models/openai-oss) | Production | Text in/out | ~3,000 tok/s | 131k / 40k | $0.35 input, $0.75 output | Recommended first candidate; production-supported and cheapest |
| [`gemma-4-31b`](https://inference-docs.cerebras.ai/models/gemma-4-31b) | Public preview | Text/image in, text out | ~1,850 tok/s | 131k / 40k | $0.99 input, $1.49 output | Interesting no-reasoning quality challenger; do not make the default while preview |
| [`zai-glm-4.7`](https://inference-docs.cerebras.ai/models/zai-glm-47) | Preview | Text in/out | ~1,000 tok/s | 131k / 40k | $2.25 input, $2.75 output | Do not adopt; Cerebras' [pricing page](https://inference-docs.cerebras.ai/support) schedules deprecation for 2026-08-17 |

Free-tier limits are lower: GPT OSS and Gemma document 65k context and 32k maximum output, while GLM documents 64k context and 40k output ([GPT OSS](https://inference-docs.cerebras.ai/models/openai-oss), [Gemma 4](https://inference-docs.cerebras.ai/models/gemma-4-31b), [GLM 4.7](https://inference-docs.cerebras.ai/models/zai-glm-47)). These windows are far beyond Yap's needs.

There is a live metadata inconsistency worth guarding against: the prose catalog and Gemma page label Gemma 4 as preview, while the unauthenticated model endpoint currently reports `preview: false` for it. Product documentation and the launch announcement still say public preview, so Yap should treat it as preview and should not rely on a single metadata flag for release safety.

All public models are documented as original, unpruned architectures. Cerebras says it uses selective weight-only quantization for storage, with sensitive layers and runtime operations kept at higher precision ([model catalog](https://inference-docs.cerebras.ai/models/overview)).

## API and SDK fit

Cerebras offers Python and TypeScript SDKs. The Python package is `cerebras_cloud_sdk`, imported as `from cerebras.cloud.sdk import Cerebras`; the API endpoint is `https://api.cerebras.ai/v1/chat/completions` ([quickstart](https://inference-docs.cerebras.ai/quickstart)).

It is also "mostly" OpenAI-compatible. Existing OpenAI clients can point to `https://api.cerebras.ai/v1`, but compatibility is not exact. Important differences include:

- Cerebras maps both `system` and `developer` roles to the same developer-level instruction layer for GPT OSS, so prompt behavior can differ from OpenAI.
- Non-standard parameters must go through `extra_body` when using the OpenAI client, but can be passed directly with the Cerebras SDK.
- `tools` and `response_format` cannot always be combined; GPT OSS rejects that combination.

See the [OpenAI compatibility guide](https://inference-docs.cerebras.ai/resources/openai). Yap currently uses the Groq SDK directly, so the cleanest addition is a `CerebrasCleanup` provider using Cerebras' native SDK rather than introducing the OpenAI SDK as a second abstraction.

For Yap's plain-text cleanup, structured outputs and tool calling add no direct value. Cerebras supports strict JSON-schema outputs through constrained decoding, plus strict, multi-turn, and parallel tool calling on compatible models ([structured outputs](https://inference-docs.cerebras.ai/capabilities/structured-outputs), [tool calling](https://inference-docs.cerebras.ai/capabilities/tool-use)). Wrapping cleaned text in JSON would add parsing and failure surface without improving the core paste path.

## Pricing and rate limits

Developer-tier public pricing is pay per token, with a $10 minimum self-serve purchase. New accounts receive $5 of credits after adding a verified payment method; credits expire after 30 days. A first pay-as-you-go purchase upgrades the account to Developer limits ([pricing](https://inference-docs.cerebras.ai/support), [change log](https://inference-docs.cerebras.ai/support/change-log)).

Current general limits ([rate-limit documentation](https://inference-docs.cerebras.ai/support/rate-limits)):

| Tier/model | RPM | TPM | Other caps |
| --- | ---: | ---: | --- |
| Free, any public model | 5 | 30k | 1M tokens/hour and 1M/day |
| Developer, GPT OSS | 1,000 | 1M | No documented daily cap |
| Developer, GLM | 500 | 500k | No documented daily cap |
| Developer, Gemma | 300 | 500k | No documented daily cap |

Limits are organization-wide, model-specific, continuously replenished token buckets. Cerebras pre-reserves estimated input plus `max_completion_tokens`, then reconciles to actual usage. Yap should therefore set a realistic completion bound rather than carry over its current 2,048-token maximum blindly.

At GPT OSS prices, a rough 500-token prompt plus 100-token result costs about $0.00025, or roughly 4,000 such cleanups per dollar. Actual cost depends on transcript length, system-prompt tokenization, reasoning tokens, and cache hits.

Prompt-prefix caching is automatic and can reduce input processing latency for repeated prefixes; the guaranteed TTL is five minutes and may extend to one hour ([prompt caching](https://inference-docs.cerebras.ai/capabilities/prompt-caching)). Yap's static cleanup instruction is a good shape for caching, but the benefit must be measured: a short prompt may not meet all cache eligibility thresholds, and it does not accelerate output decoding.

## Latency, reliability, and operational caveats

Cerebras' reported tokens-per-second figures are output-generation throughput, not a guarantee of end-to-end Yap latency. For a short cleanup, DNS/TLS, request upload, shared-queue delay, prompt processing, reasoning tokens, and time to first token can dominate. The correct comparison is release-to-paste latency measured from Yap, not provider TPS.

The public status page reported the following trailing-90-day availability when looked up on 2026-07-22: GPT OSS 99.97%, GLM 99.95%, Gemma 100%, and Developer Console 100% ([status page](https://status.cerebras.ai/)). This is a useful recent snapshot, not an SLA. Public/shared endpoints are subject to tier rate limits; predictable performance, reserved capacity, and production SLAs are positioned as dedicated/Enterprise features ([model catalog](https://inference-docs.cerebras.ai/models/overview), [dedicated endpoints](https://inference-docs.cerebras.ai/dedicated/overview)).

GPT OSS has model-specific caveats. It defaults to medium reasoning, and Cerebras only exposes `low`, `medium`, and `high` reasoning effort for it; unlike GLM/Gemma, there is no documented `none` setting. Its model page also warns that it may hallucinate tool calls, though Yap will not provide tools ([reasoning guide](https://inference-docs.cerebras.ai/capabilities/reasoning), [GPT OSS model notes](https://inference-docs.cerebras.ai/models/openai-oss)). For deterministic cleanup, set `reasoning_effort="low"` and verify that content remains faithful.

## Data, privacy, and legal posture

Cerebras' Cloud Privacy Policy says it does **not retain inputs and outputs** associated with training, inference, and chatbot services. It does retain service logs until they are no longer necessary to provide the service, without publishing a fixed retention period. It also says customer/partner processing is outside the policy's controller scope, and data may be processed in the United States and other countries ([Cloud Privacy Policy](https://cloud.cerebras.ai/privacy)).

The Cloud Terms say Cerebras claims no ownership over API prompts or outputs as between Cerebras and the user, but ownership and usage are also governed by the applicable third-party model terms. Usage/telemetry data may be used for service operation, analytics, and product improvement in aggregated or de-identified form ([Cloud Terms](https://cloud.cerebras.ai/terms)).

For a personal dictation app this is a comparatively strong stated input/output retention posture, but Yap should communicate the exact boundary: transcript text still leaves the Mac and is processed by Cerebras; service metadata/logs can remain; cross-border processing may occur; and third-party model terms apply. Do not market this as local or zero-data-processing.

## Recommended Yap changes

### 0. Rotate the exposed key

Revoke the key shared in chat and create a replacement in the Cerebras console. Store the replacement only through Yap's local `secrets.toml` flow (mode `0600`) or `CEREBRAS_API_KEY`; never place it in default config, tests, logs, docs, or git history.

### 1. Add Cerebras only to cleanup

- Add a `CerebrasCleanup` implementation beside `GroqCleanup` and `MistralCleanup`.
- Add `cerebras_api_key` / `CEREBRAS_API_KEY`, secure settings input, and `cleanup.provider = "cerebras"`.
- Default its model to `gpt-oss-120b` because it is production-classified, inexpensive, and least likely to disappear on short notice.
- Keep transcription provider selection independent. Cerebras cannot replace `GroqTranscriber`; switching the entire Groq dependency requires moving transcription to Mistral/Voxtral or another speech provider.
- Keep provider/model values configurable to absorb Cerebras' model churn.

### 2. Tune the request for dictation rather than reasoning

Start with:

- `temperature=0`
- `reasoning_effort="low"` for GPT OSS
- `max_completion_tokens` sized from the input length with a modest safety margin, capped around Yap's existing 2,048 limit; 256-512 is sufficient for typical short dictations
- no tools, no JSON schema, and no streaming for the first implementation
- explicit request timeout and bounded retry on 429/5xx with jitter

The current synchronous, non-streaming call is appropriate because Yap cannot paste a partial rewrite safely. Streaming would only complicate the atomic paste behavior.

### 3. Benchmark before changing the default

Build a fixed, local corpus of at least 50 representative English and German transcripts, including:

- short and long dictations
- filler words and stutters
- names, acronyms, and vocabulary terms
- questions
- quoted instructions and prompt-injection-shaped text
- mixed-language utterances
- cases that previously triggered meta-responses or dropped sentences

Run Groq, Cerebras GPT OSS, and Gemma 4 against identical prompts. Yap's benchmark corpus now contains 50 deterministic cases spanning short/long dictation, names/acronyms, questions, mixed language, quoted and prompt-injection-shaped speech, and prior suffix/meta failures. Record:

- exact meaningful-word preservation
- correct filler/stutter removal
- punctuation/question-mark correctness
- unexpected answering, summarization, translation, or meta-response rate
- p50/p95 provider latency and the benchmark's wall-clock release-to-paste proxy; use Yap's local JSONL for true hotkey-release-to-paste timing
- warm/cold behavior, final and recovered response status (including 429/5xx rate), estimated cost from current first-party price tables, and conservative unexpected-answer/summarization/translation flags

Promotion gate: Cerebras should become default only if it is at least as faithful as Groq and materially improves p95 release-to-paste latency without raising fallback/error frequency. Peak TPS alone is not sufficient.

### 4. Make fallback behavior explicit

For provider/network failures, preserve the raw transcript rather than delaying paste through a second slow cloud call. If an automatic secondary provider is added, make it optional and bounded to one attempt. Record provider, model, latency, final/recovered response status, finish reason, request/completion attempts, and fallback reason in local logs, but never transcript content or keys.

### 5. Use live model discovery for diagnostics, not silent model switching

The unauthenticated [public models endpoint](https://api.cerebras.ai/public/v1/models) exposes prices, limits, capabilities, and deprecation/preview flags. Yap can use it in a diagnostics/settings surface to warn that a configured model is unavailable or preview. It should not silently change models: prompt behavior and transcript fidelity can change materially across model families, and the current Gemma preview-flag mismatch shows why metadata needs conservative interpretation.

## Suggested decision

Proceed with a contained Cerebras cleanup-provider experiment. Do **not** remove Groq transcription, do **not** choose GLM 4.7, and do **not** switch the default until a representative end-to-end benchmark is green. The likely best first production configuration is:

- transcription: existing Groq Whisper or Mistral Voxtral
- cleanup: Cerebras `gpt-oss-120b`
- fallback on cleanup failure: raw transcript
- provider/model: user-selectable and logged without content

This captures Cerebras' main advantage—very fast text generation—without confusing text inference with speech transcription or coupling Yap to a fast-changing preview catalog.

## Gemma 4 use-case analysis

This section is a Gemma-specific snapshot looked up on 2026-07-22. Statements marked **Fact** come directly from the linked first-party Cerebras or Google sources. Statements marked **Inference** are product judgments for Yap and must be validated with a local benchmark.

### Capability facts

- **Fact — no audio or TTS:** Cerebras documents `gemma-4-31b` as **text and image input, text output**. Its public API metadata reports `architecture.modality: "text+vision"`, and its only endpoints are text Chat Completions and Completions. There is no audio-input or audio-output capability on the Cerebras endpoint ([Cerebras model page](https://inference-docs.cerebras.ai/models/gemma-4-31b), [live public metadata](https://api.cerebras.ai/public/v1/models/gemma-4-31b)). Google's native Gemma 4 model card independently says the 31B variant has no audio encoder; audio recognition is limited to smaller Gemma 4 variants. None of those audio-capable variants provides speech synthesis—their audio feature is audio-to-text ASR/translation ([Google Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)).
- **Fact — hosted limits:** Cerebras caps the hosted model at 131,072 context tokens and 40,960 completion tokens on paid access; its model page lists 65k context and 32k output on the free tier. This is lower than the native model card's 256k context, so Yap must design to the Cerebras-hosted limit ([model page](https://inference-docs.cerebras.ai/models/gemma-4-31b), [live public metadata](https://api.cerebras.ai/public/v1/models/gemma-4-31b)).
- **Fact — pricing and quotas:** Developer pricing is $0.99/M input tokens and $1.49/M output tokens. Free access is 5 RPM, 30k TPM, and 1M daily tokens; pay-as-you-go is 300 RPM and 500k TPM with no documented daily cap. Compared with Cerebras GPT OSS, Gemma costs about 2.8x more for input and 2.0x more for output and has lower Developer limits ([Gemma model page](https://inference-docs.cerebras.ai/models/gemma-4-31b), [rate limits](https://inference-docs.cerebras.ai/support/rate-limits), [GPT OSS model page](https://inference-docs.cerebras.ai/models/openai-oss)).
- **Fact — reasoning:** reasoning is disabled by default with `reasoning_effort="none"`. `low`, `medium`, and `high` all currently have the same effect: they turn reasoning on without graduated effort. Gemma does not support `raw` or `hidden` reasoning formats, nor `clear_thinking`/`preserve_thinking` ([reasoning guide](https://inference-docs.cerebras.ai/capabilities/reasoning)).
- **Fact — structured behavior:** the model supports streaming, JSON mode, structured outputs, strict constrained decoding, tool choice, strict tool calling, and parallel tool calling ([model page](https://inference-docs.cerebras.ai/models/gemma-4-31b), [live public metadata](https://api.cerebras.ai/public/v1/models/gemma-4-31b)). Cerebras' compatibility guide still warns against relying on `tools` and `response_format` together across models; use either tools or structured output, or two calls ([OpenAI compatibility](https://inference-docs.cerebras.ai/resources/openai)).
- **Fact — image inputs:** Chat Completions accepts base64 data-URI PNG/JPEG images; external URLs are unavailable during public preview. Developer/shared limits are five images and 10 MB total per request; the free-tier rate-limit table lists two images and 4 MB. Each image uses at most 280 image tokens and may be resized before analysis. The docs warn about small text, rotation, charts differentiated only by color/line style, exact spatial reasoning, counting, medical imagery, inaccurate captions, indirect prompt injection in image text, and unsafe verbatim output ([image-input guide](https://inference-docs.cerebras.ai/capabilities/image-inputs), [tier limits](https://inference-docs.cerebras.ai/support/rate-limits)).
- **Fact — speed claim, not a Yap guarantee:** Cerebras advertises roughly 1,850 output tokens/s. Its launch post says Artificial Analysis measured 1,851 tokens/s and a 1.5-second first answer token inclusive of reasoning. These are provider/benchmark claims, not a public latency SLA and not a measurement of a short Bangkok-to-Cerebras cleanup request from Yap ([Cerebras announcement](https://www.cerebras.ai/blog/gemma-4-on-cerebras-the-fastest-inference-is-now-multimodal)).
- **Fact — preview risk:** the model catalog and navigation label Gemma 4 as preview, and the launch says it is available in public preview "for a limited time." Preview models are described as evaluation-only and subject to discontinuation on short notice. The live metadata endpoint inconsistently reports `preview: false`; the conservative interpretation is therefore preview, not production ([model catalog](https://inference-docs.cerebras.ai/models/overview), [announcement](https://www.cerebras.ai/blog/gemma-4-on-cerebras-the-fastest-inference-is-now-multimodal), [live metadata](https://api.cerebras.ai/public/v1/models/gemma-4-31b)).
- **Fact — license and safety caveats:** Cerebras describes Gemma 4 as Apache 2.0 open-weight, and [Google's official model repository](https://huggingface.co/google/gemma-4-31B-it) metadata also identifies Apache 2.0. Google reports automated and human safety evaluation but still calls out bias, misinformation, privacy violations, harmful content, factual error, ambiguity, and the need for application-specific safeguards and monitoring ([Cerebras announcement](https://www.cerebras.ai/blog/gemma-4-on-cerebras-the-fastest-inference-is-now-multimodal), [Google model card](https://ai.google.dev/gemma/docs/core/model_card_4)). Use through Cerebras remains subject to Cerebras Cloud Terms and applicable third-party model terms ([Cloud Terms](https://cloud.cerebras.ai/terms)).

### Yap recommendation matrix

| Yap use case | Recommendation | Facts driving the decision | Product inference |
| --- | --- | --- | --- |
| Text-to-speech | **No** | Text-only output; no speech/audio output API | Gemma cannot generate Yap audio feedback or spoken playback. Use a dedicated TTS engine/provider. |
| Speech transcription | **No** | Cerebras-hosted 31B accepts text/images only; Google's 31B has no audio encoder | It cannot replace Groq Whisper or Mistral Voxtral. Smaller native Gemma variants having ASR does not make ASR available through this endpoint. |
| Transcript cleanup | **Benchmark challenger; not default** | Text-to-text, reasoning off by default, multilingual training, ~1,850 advertised tok/s; but preview, pricier and lower-limit than GPT OSS | No-reasoning-by-default may fit faithful cleanup better than GPT OSS's mandatory low/medium/high reasoning. Test it against GPT OSS and Groq for word preservation, German/English quality, meta-responses, and p95 release-to-paste latency. |
| Screenshot-aware dictation | **Later opt-in experiment** | Supports screenshots/OCR-like image understanding, up to five images/10 MB paid | A user-invoked "dictate about this screenshot" mode could add context for replies or coding prompts, but silent screen capture would create privacy/permission risk and violate Yap's low-chrome scope. |
| Image/document text extraction | **Possible adjacent feature** | Vision can read documents and screenshots, with stated small-text/accuracy limitations | Useful only with visible source attachment, untrusted-input handling, and user verification; not reliable enough for high-stakes or exact OCR. |
| Structured cleanup metadata | **Defer** | Strict JSON schema is supported | Raw-vs-cleaned spans or detected language could be returned reliably, but Yap's atomic plain-text paste does not currently need the extra schema/parsing surface. |
| Tool-driven actions | **Defer** | Strict and parallel tool calling are supported | Turning dictation into actions changes Yap from a post-processor into an agent and needs separate authorization/safety design. It is not a reason to choose Gemma for cleanup. |

### Cleanup-specific experiment design

**Inference:** Gemma is the most interesting second Cerebras cleanup candidate because reasoning can be fully disabled. Test `reasoning_effort="none"` and compare two sampling profiles: Yap's deterministic `temperature=0`, and Google's native-model recommendation of `temperature=1.0`, `top_p=0.95` (Cerebras metadata does not list `top_k`, so do not send Google's `top_k=64` recommendation blindly). The official sampling guidance was designed for general Gemma quality, while Yap needs unusually strict preservation; neither profile should be assumed best without the corpus benchmark ([Google model card](https://ai.google.dev/gemma/docs/core/model_card_4), [Cerebras parameter metadata](https://api.cerebras.ai/public/v1/models/gemma-4-31b)).

**Recommendation:** keep production `gpt-oss-120b` as the first Cerebras integration target, but include Gemma 4 in the benchmark. Promote Gemma only if its no-reasoning mode materially improves transcript fidelity or end-to-end latency, and even then keep it opt-in until Cerebras resolves the preview-status contradiction or graduates the model to an unambiguous production offering.

## Full shared-model comparison for Yap

This section is a live catalog snapshot from 2026-07-22. **Fact** means a value exposed by a first-party model page, capability guide, status page, or Cerebras' unauthenticated API. **Provider claim** means a performance number published by Cerebras, not a measured Yap result or latency SLA. **Inference** means a product recommendation that still needs the local dictation corpus benchmark.

### Shared/public catalog boundary

**Fact:** Cerebras' unauthenticated [`/public/v1/models`](https://api.cerebras.ai/public/v1/models) endpoint returned exactly these three model IDs for normal shared Cloud access:

1. `gpt-oss-120b`
2. `gemma-4-31b`
3. `zai-glm-4.7`

The [shared model catalog](https://inference-docs.cerebras.ai/models/overview) agrees with that three-model boundary. Cerebras' [Dedicated Inference](https://inference-docs.cerebras.ai/dedicated/overview) describes a broader enterprise-only/custom-deployment catalog that can include Qwen/Qwen3-Coder, smaller and safeguard GPT OSS variants, MiniMax, other Gemma variants, Llama 3/4, Mistral, newer GLM variants, Kimi, DeepSeek, StepFun, ByteDance Seed, ServiceNow Apriel, and customer weights. Those models are **not** returned by the normal shared endpoint and are therefore excluded from this Yap ranking. Their presence on Cerebras hardware or in enterprise material does not make them callable with an ordinary Cerebras Cloud key.

### Exact shared-model facts

| Model ID | Lifecycle on 2026-07-22 | Modalities | Reasoning controls | Structured output and tools | Shared hosted limits | Price per 1M tokens | Shared rate limits | Advertised performance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gpt-oss-120b` | **Production**; no announced deprecation | Text input, text output; no image or audio | Default `medium`; supports only `low`, `medium`, `high`; cannot be disabled | JSON mode, strict structured outputs, tool choice, and strict tool calling. Public metadata says no parallel tool calls. Cerebras rejects combining `tools` and `response_format`. | Paid: 131,072 context / 40,960 completion. Free: 65k / 32k. | $0.35 input / $0.75 output | Free: 5 RPM, 30k TPM, 1M tokens/day. Developer: 1,000 RPM, 1M TPM; no documented daily cap. | **Provider claim:** about 3,000 output tok/s. No current model-page TTFT claim located. |
| `gemma-4-31b` | **Preview** in catalog and launch material, available for a limited time; no dated retirement. Live metadata inconsistently says `preview: false`, so treat it as preview. | Text and image input, text output; no audio | Default `none`; `low`, `medium`, and `high` all merely enable reasoning and are currently equivalent. No `raw`/`hidden`, `clear_thinking`, or `preserve_thinking`. | JSON mode, strict structured outputs, strict tools, tool choice, and parallel tool calls. Do not combine `tools` and `response_format`. | Paid: 131,072 / 40,960. Free: 65k / 32k. Paid image limit: 5 images / 10 MB; free: 2 / 4 MB. | $0.99 / $1.49 | Free: 5 RPM, 30k TPM, 1M/day. Developer: 300 RPM, 500k TPM. | **Provider claim:** about 1,850 output tok/s; launch cites 1.5 s to first answer token inclusive of reasoning. Not a Yap/network SLA. |
| `zai-glm-4.7` | **Preview**, still active but scheduled for deprecation on **2026-08-17**. Its current metadata `deprecated: false` means not retired yet, not that retirement is unplanned. | Text input, text output; no image or audio | Reasoning enabled by default; `reasoning_effort="none"` disables it. The old `disable_reasoning` parameter was removed after 2026-07-21. `clear_thinking` defaults true. | JSON mode, strict structured outputs, strict tools, tool choice, and parallel tool calls. Do not combine `tools` and `response_format`. | Paid: 131,072 / 40,960. Free: 64k / 40k. | $2.25 / $2.75 | Free: 5 RPM, 30k TPM, 1M/day. Developer: 500 RPM, 500k TPM. | **Provider claim:** about 1,000 output tok/s. No current model-page TTFT claim located. |

Sources: [GPT OSS model page](https://inference-docs.cerebras.ai/models/openai-oss), [Gemma model page](https://inference-docs.cerebras.ai/models/gemma-4-31b), [GLM model page](https://inference-docs.cerebras.ai/models/zai-glm-4.7), [reasoning guide](https://inference-docs.cerebras.ai/capabilities/reasoning), [rate limits](https://inference-docs.cerebras.ai/support/rate-limits), [OpenAI compatibility](https://inference-docs.cerebras.ai/resources/openai), and the live [per-model API metadata](https://api.cerebras.ai/public/v1/models/gpt-oss-120b).

The shared quotas use more than a simple per-request bucket: the [rate-limit guide](https://inference-docs.cerebras.ai/support/rate-limits) also documents a total-token throughput bucket equal to three times the uncached TPM allowance. Context length is therefore not equivalent to sustained capacity.

### Reliability evidence, with limits

**Fact:** Cerebras' [public status page](https://status.cerebras.ai/) showed 90-day API-model uptime of 99.97% for GPT OSS, 99.95% for GLM 4.7, and 100% for Gemma 4 at lookup time. These are rolling provider status snapshots, not a contractual SLA, not per-region latency data, and not proof that short requests from Bangkok will meet Yap's release-to-paste target. Preview lifecycle risk remains distinct from recent service uptime.

### Fit for the current Yap pipeline

| Yap requirement | `gpt-oss-120b` | `gemma-4-31b` | `zai-glm-4.7` |
| --- | --- | --- | --- |
| Speech recognition / ASR | **No.** No audio input or transcription endpoint. | **No.** Cerebras' hosted 31B has no audio input. Smaller native Gemma variants with audio do not change this endpoint. | **No.** No audio input or transcription endpoint. |
| Faithful, strict cleanup | **Best production candidate.** Cheapest, highest advertised throughput, strict output available. Mandatory reasoning may add latency or over-edit, so test `low`. | **Best fidelity challenger.** Reasoning can be fully disabled, which may better preserve wording. Preview status prevents a default recommendation. | Technically capable with reasoning disabled, but imminent retirement makes evaluation and integration wasteful. |
| Formatting and rewrite | Strong candidate; production stability and high limits are favorable. Its tendency to reason and possible unspecified-tool hallucination mean Yap should send no tools and validate plain text. | Strong candidate, especially when image context is useful. Preview and lower limits weaken production suitability. | Capable, but price, lower advertised speed, preview status, and scheduled retirement dominate. |
| English, German, Thai | **Unverified per-language fit.** OpenAI publishes a [multilingual evaluation](https://deploymentsafety.openai.com/gpt-oss/multilingual-performance) for GPT OSS, but Cerebras does not establish dictation-cleanup quality for this exact EN/DE/Thai mix. Benchmark all three. | [Google's model card](https://ai.google.dev/gemma/docs/core/model_card_4) says out-of-box support for 35+ languages and pretraining across 140+, but neither Cerebras nor the cited card establishes equal cleanup quality in English, German, and Thai. Benchmark all three. | [Z.ai](https://z.ai/blog/glm-4.7) claims multilingual agentic-coding performance, not verified German/Thai prose cleanup. Do not infer dictation quality from coding benchmarks. |
| Screenshot context | **No.** Text-only. | **Yes, opt-in only.** It is the sole shared model with image input, subject to image limits and documented OCR/spatial/prompt-injection caveats. | **No.** Text-only. |
| Structured cleanup metadata | Supported, but unnecessary for the first plain-text integration. | Supported, including strict schemas; useful only if Yap later needs spans/language labels. | Supported, but not worth adopting before retirement. |
| Default-provider reliability | **Only viable Cerebras default candidate**, because it alone is production-classified. Still require retry, timeout, raw fallback, and local measurement. | Preview-only benchmark candidate, even though its status-page uptime was recently strong. | **Reject.** Scheduled retirement rules it out regardless of current uptime. |

The multilingual rows are deliberately conservative. Model-family multilingual breadth is not evidence that filler removal, punctuation, names, code-switching, and exact word preservation work equally well for dictation in each language. Thai also uses a different script and segmentation behavior, so an English/German-only score cannot stand in for Thai.

### Comparison with Yap's current Groq/Mistral design

**Current repo fact:** Yap's default transcription route is Groq `whisper-large-v3-turbo`, with a Mistral Voxtral implementation (`voxtral-mini-2602`) available as the alternative. Its default cleanup route is Groq `openai/gpt-oss-120b`, with Mistral `mistral-small-latest` as the alternative and Cerebras `gpt-oss-120b` as an opt-in route. The cleanup implementations use a strict preservation prompt, bounded completion budgets, retry/truncation guards, and raw-transcript fallback when a provider fails or returns unusable output.

That creates a clean integration boundary:

- **Fact:** none of the three shared Cerebras models can replace Groq Whisper or Mistral Voxtral. A Cerebras change affects only the text cleanup stage.
- **Inference:** implement Cerebras as a third `CleanupProvider`, not as a combined replacement for the transcription and cleanup stack.
- **Inference:** keep Groq Whisper as the transcription default during the cleanup benchmark so only one variable changes. Benchmark Mistral Voxtral independently if removing Groq as a vendor is a separate goal.
- **Fact:** Yap currently allows only `en` and `de` in its Groq transcription configuration and fallback order. Choosing a multilingual cleanup model does **not** add end-to-end Thai support. Thai first needs explicit transcription-language/config support and an ASR accuracy corpus, followed by cleanup testing.
- **Inference:** retain atomic non-streaming cleanup, the current strict prompt, and raw fallback. Do not enable tools for dictation cleanup. Structured JSON is optional and should not be added until a real consumer exists.
- **Inference:** for the first GPT OSS test use `reasoning_effort="low"`; for Gemma use `reasoning_effort="none"`. Compare preservation and p50/p95 release-to-paste latency rather than advertised TPS.

### Ranked recommendation

1. **Integrate `gpt-oss-120b` as an optional Cerebras cleanup provider and benchmark it first.** It is the only production-classified shared model, the least expensive, has the highest developer quota and advertised throughput, and has no announced retirement. Keep it opt-in until its mandatory low reasoning proves as faithful as the current Groq cleanup on the local corpus.
2. **Include `gemma-4-31b` as the cleanup-fidelity and screenshot-context challenger.** Fully disabled reasoning is attractive for strict cleanup, and it is the only shared vision model. Keep it experimental because Cerebras labels it preview/limited-time and its metadata disagrees with that label.
3. **Do not integrate `zai-glm-4.7`.** It is preview, the most expensive, the slowest by current provider claim, and scheduled to retire on 2026-08-17. Its capable reasoning and structured-output controls do not overcome the lifecycle boundary.

For the pipeline as a whole, retain Groq Whisper or Mistral Voxtral for ASR; Cerebras has no shared speech model. Do not claim Thai support until the transcription configuration and an EN/DE/Thai end-to-end corpus are green. Treat Gemma screenshot context as a separately authorized, user-visible feature rather than ambient capture. Finally, none of the three should become Yap's default from catalog facts alone: the promotion gate remains measured fidelity, p95 release-to-paste latency, error/fallback rate, and lifecycle stability.
