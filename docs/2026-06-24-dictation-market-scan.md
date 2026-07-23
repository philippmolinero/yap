# Dictation Market Scan

Date: 2026-06-24

Purpose: identify the best current dictation apps to use as references and north stars for Yap.

## Executive Take

Yap sits closest to the "instant Mac push-to-talk" category, but the market is moving toward "voice as a universal writing layer." The strongest north stars are:

1. Wispr Flow for category ambition, onboarding, cross-app polish, dictionary/snippets, and enterprise trust.
2. Aqua Voice for real-time mode, contextual awareness, fast-feeling output, and modern AI-native positioning.
3. BetterDictation for the closest direct Mac reference: simple push-to-talk, local-first transcription, offline operation, and low-friction pricing.
4. Superwhisper for power-user depth: local/cloud model choice, custom prompts, BYO API keys, meeting/audio-file transcription, and coding workflows.
5. Dragon/Nuance for mature professional expectations: custom vocabularies, vertical workflows, commands, and reliability.
6. Otter.ai for the adjacent "capture, summarize, recall" direction if Yap ever expands into meetings or dictation history as a knowledge asset.

Yap should not try to match every surface area. The most compelling wedge remains: a tiny, Mac-native, always-ready dictation tool that feels faster and calmer than the heavier AI voice apps.

## Market Pattern

The current leaders are converging around five value propositions:

- Any-app dictation: voice input into whatever field is active, without a separate editor.
- Messy speech cleanup: filler removal, punctuation, grammar, formatting, and intent-preserving rewrite.
- Personalization: custom dictionaries, snippets, vocabulary learning, and style/custom instructions.
- Privacy/trust: local models, privacy modes, zero-data-retention claims, SOC 2/ISO/HIPAA posture for teams.
- Workflow expansion: meeting transcription, file transcription, AI commands, summaries, coding prompts, and team dictionaries.

For Yap, the key question is not "which features exist?" but "which features keep the core loop invisible?" Anything that adds configuration weight must pay rent by improving the hold-release-paste moment.

## North-Star Apps

### Wispr Flow

Official site: https://wisprflow.ai/
Pricing: https://wisprflow.ai/pricing
Privacy: https://wisprflow.ai/privacy

Why it matters:

- The clearest category leader for "voice replaces typing."
- Available across Mac, Windows, iPhone, and Android.
- Markets speed aggressively, including "4x faster than typing" and "220 wpm" style comparisons.
- Offers custom dictionary, snippets, 100+ languages, privacy mode, HIPAA-ready positioning, command mode, shared dictionary/snippets, and team admin/compliance.
- Pricing as of this scan: Basic free with weekly word limits; Pro listed at $12/user/month annually or $15/user/month monthly; Enterprise custom.

What to borrow:

- Treat dictation as a writing product, not just speech-to-text.
- Show before/after cleanup examples everywhere.
- Add personal vocabulary and snippets as first-class primitives.
- Make trust legible in the UI: what is sent, what is stored, what mode is active.
- Consider command mode later, but only after the core record/transcribe/paste loop is excellent.

What to avoid:

- Flow is becoming broad and team-oriented. Yap can differentiate by staying lighter, cheaper, and more Mac-native.

### Aqua Voice

Official site: https://aquavoice.com/
Pricing section: https://aquavoice.com/#pricing

Why it matters:

- Strong modern reference for real-time voice writing.
- User testimonials repeatedly call out speed, low friction, "real-time" mode, and context for coding/LLM workflows.
- Mac and iOS downloads are prominent.
- Pricing as of this scan: Starter free with 1,000 words, Aqua Engine, and 5 custom dictionary values; Pro $8/month billed annually with unlimited words, Avalon model, 800 custom dictionary values, and custom instructions; Team $12/month billed annually; Enterprise custom with SSO/SAML, zero data retention, advanced reporting, and team-wide dictionaries.

What to borrow:

- Real-time feedback can make dictation feel trustworthy before final paste.
- Custom instructions are a compact way to let users shape output without complicated settings.
- Context awareness is especially valuable for coding, support, and writing inside LLM tools.

What to avoid:

- Screen/app context can become privacy-sensitive and permission-heavy. Yap should only pursue this with explicit controls and clear user benefit.

### Superwhisper

Official site: https://superwhisper.com/

Why it matters:

- Strongest reference for power users and AI-native developers.
- Works in any app; includes meeting recording and transcription; supports 100+ languages; has custom prompt control.
- Pro adds BYO API keys, unlimited cloud/local AI models, translation to English, and audio/video file transcription.
- Pricing as of this scan: Free tier; Pro displayed at $8.49/month; Enterprise custom. The site also references Mac, Windows, and iOS availability.
- Testimonials emphasize coding with Cursor/LLMs and "AI-native operating system" style workflows.

What to borrow:

- Let advanced users bring their own model/API keys if it fits the architecture.
- Keep prompt customization available but tucked away.
- Audio/video file transcription is a natural adjacent feature, but not core to Yap's instant-dictation wedge.

What to avoid:

- Too many model knobs can make a lightweight menubar app feel like a lab bench.

### BetterDictation

Official site: https://www.betterdictation.com/

Why it matters:

- Closest direct reference for Yap's current shape.
- Mac-only, push-to-talk, system-level dictation into any app.
- Runs OpenAI Whisper on Apple Neural Engine for Apple Silicon Macs.
- Basic mode is offline and on-device; Pro cleanup uses OpenAI.
- Supports 100+ languages; offers stammer correction, automatic formatting, grammar correction, and post-processing prompts.
- Pricing as of this scan: Basic $39 lifetime single-device; Flex $49 lifetime plus $2/month billed annually for Pro; Studio $149 lifetime plus $2/month/device; separate Pro upgrade $2/month billed annually.

What to borrow:

- Simple pricing story: local transcription has low marginal cost, so a lifetime option is credible.
- Make push-to-talk and toggle-to-talk explicit modes.
- Lean into offline/privacy when local models are used.
- Keep the setup beginner-friendly.

What to avoid:

- It is Apple Silicon only. Yap can decide whether broad compatibility or peak local speed matters more.

### Dragon / Nuance

Official site: https://dragon.nuance.com/en-us/home-professional-and-consumer
Market coverage: https://www.techradar.com/best/dictation-software

Why it matters:

- Still the classic professional benchmark for dictation accuracy and vertical workflow support.
- The durable lessons are custom vocabulary, correction/training loops, command vocabularies, and specialized domains like legal/medical.

What to borrow:

- Build a correction loop that teaches the system user-specific names, acronyms, and terms.
- Let users maintain a visible vocabulary file or settings panel.
- Consider domain presets later: "email reply," "technical note," "medical-ish but not medical device," "code prompt," etc.

What to avoid:

- Dragon-style heavyweight UI, training, and enterprise ceremony would fight Yap's lightweight identity.

### Otter.ai

Official site/pricing: https://otter.ai/pricing

Why it matters:

- Not a direct dictation competitor, but a reference for capture workflows.
- Pricing page highlights meeting integrations, AI chat across meetings, live transcription, speaker identification, playback, multi-language support, imports, templates, advanced search, storage, and CRM integrations.
- Basic plan lists 300 monthly transcription minutes; Pro lists 1,200 in-app recording minutes; Business lists longer meetings, unlimited imports/recordings, admin, and concurrent meeting capture.

What to borrow:

- Yap's history could eventually become more than a list: search, replay, summarize, reuse, and export.
- Speaker ID and meeting workflows are only relevant if Yap expands beyond personal dictation.

What to avoid:

- Meeting assistant sprawl. Yap should remain personal-input first unless the product direction changes.

## Emerging Watchlist

### Google AI Edge Eloquent

Coverage:

- https://www.tomsguide.com/ai/google-just-launched-a-free-ai-dictation-app-that-fixes-your-speech-and-it-even-works-offline
- https://www.techradar.com/ai-platforms-assistants/i-tried-using-googles-new-offline-ai-dictation-app-and-polished-my-ramblings-surprisingly-well

Why it matters:

- New iOS offline dictation app from Google, reported in April 2026.
- Emphasizes on-device operation, filler removal, real-time cleanup, custom dictionaries, and optional Gemini-powered online refinement.
- Important signal: high-quality offline cleanup is becoming table stakes, not a niche feature.

Implication for Yap:

- Local-first cleanup may become a stronger differentiator than cloud LLM cleanup, especially for privacy-conscious Mac users.

### MacWhisper

Official site: https://www.macwhisper.com/

Why it matters:

- Known Mac transcription app built around Whisper, but harder to evaluate from the official page because the current site redirects to a Gumroad page that was not text-readable in this scan.
- More relevant for file transcription than universal push-to-talk dictation.

Implication for Yap:

- Worth a hands-on test if file transcription becomes part of the roadmap.

## Feature Matrix

| App | Best reference for | Platforms surfaced in scan | Pricing signal | Key features to study |
| --- | --- | --- | --- | --- |
| Wispr Flow | Category leader and polished universal voice input | Mac, Windows, iPhone, Android | Free + Pro $12/month billed annually or $15/month | Auto edits, dictionary, snippets, command mode, privacy mode, team dictionaries |
| Aqua Voice | Real-time AI dictation and context-aware writing | Mac, iOS | Free + Pro $8/month billed annually | Real-time mode, custom instructions, large dictionary, privacy/team controls |
| Superwhisper | Power-user model and prompt control | Mac, Windows, iOS | Free + Pro $8.49 | Local/cloud models, BYO keys, custom prompts, meetings, file transcription |
| BetterDictation | Closest Yap-like Mac push-to-talk product | macOS Apple Silicon | $39 lifetime basic + $2/month Pro | Offline local Whisper, push/toggle modes, simple setup, Pro cleanup |
| Dragon / Nuance | Professional dictation maturity | Windows/pro verticals | Premium/pro pricing | Custom vocab, training/correction, commands, vertical specialization |
| Otter.ai | Meeting capture and recall | Web, desktop, iOS, Android | Free + Pro/Business subscriptions | Live meeting transcription, speaker ID, summaries, imports, search |
| Google AI Edge Eloquent | Offline real-time cleanup signal | iOS reported | Free reported | On-device cleanup, dictionaries, optional Gemini online mode |

## Yap Product Implications

### Near-term north star

Yap should become "the fastest way to put clean words into any Mac app."

That means:

- Instant hold-to-talk must feel more important than dashboards, meetings, or team features.
- Cleanup quality must be visible in the result, not exposed as complexity.
- The overlay should reassure the user about state: recording, silence stopping, transcribing, cleaning, pasted.
- History should stay useful and quiet: recent dictations, copy again, maybe raw vs cleaned view.

### Differentiators to pursue

1. Fast, calm Mac-native feel
   - Better than webby overlays.
   - Minimal chrome.
   - Audible/subtle feedback.
   - Works from any focused field.

2. Transparent privacy modes
   - Cloud transcription/cleanup vs local transcription should be explicit.
   - If local models are added, make "offline/local" a simple mode, not a model picker first.

3. Personal vocabulary
   - Names, project terms, acronyms, product names.
   - Start with the existing `config/vocabulary.txt` concept and expose it in settings/history correction.

4. Style presets
   - "Clean dictation" default.
   - "Short message."
   - "Email reply."
   - "Technical note."
   - "Prompt for coding assistant."

5. Correction feedback loop
   - Save corrected phrases or rejected cleanup results.
   - Use history to improve future cleanup.

### Features to defer

- Meeting bot workflows.
- Team admin and compliance dashboards.
- Broad mobile support.
- Deep screen/app context.
- Heavy command-and-control automation.
- Too many model/provider settings in the main UI.

## Recommended Yap Bets

### Bet 1: Make the core loop visibly reliable

Borrow from BetterDictation's simplicity and Aqua's real-time trust signals. The user should always know whether Yap is recording, stopped by silence, transcribing, cleaning, pasting, or failed. This is higher-leverage than adding more providers.

### Bet 2: Turn vocabulary into a product feature

Wispr Flow, Aqua, Dragon, and Otter all point toward the same truth: names and domain terms matter. Yap already has `config/vocabulary.txt`; the next step is making vocabulary editable, discoverable, and fed into both transcription and cleanup.

### Bet 3: Add output style presets before deep prompt customization

Superwhisper proves prompt control is valuable, but Yap should start with opinionated presets: clean dictation, short message, email reply, technical note, and coding-assistant prompt. Hide raw prompt editing behind an advanced setting later.

### Bet 4: Preserve the lightweight privacy story

The market is training users to ask where audio and text go. Yap should show a simple provider/mode summary in Settings and eventually offer local transcription as a privacy/performance mode if model quality is good enough.

### Bet 5: Use history as a correction surface

Otter shows the value of searchable transcripts; Dragon shows the value of correction loops. Yap's history can become the place to copy again, compare raw vs cleaned text, add vocabulary from a transcript, and mark a cleanup as good or bad.

## Suggested Hands-On Benchmark

To turn this scan into product decisions, test Yap against the four closest apps:

1. BetterDictation
2. Wispr Flow
3. Aqua Voice
4. Superwhisper

Use the same prompts in the same target apps:

- Messages/Slack short reply: 10-20 seconds.
- Gmail/email paragraph: 30-60 seconds.
- Cursor/Claude/Codex coding instruction: 30-60 seconds with technical terms.
- Notes long-form ramble: 2-3 minutes with corrections and pauses.
- Multilingual or accent test if relevant.

Measure:

- Time from hotkey release to text appearing.
- Whether the active app receives text reliably.
- Cleanup quality.
- Punctuation and paragraph formatting.
- Handling of names/acronyms.
- Error recovery when network/model fails.
- Permission/onboarding friction.
- CPU/memory while idle and while transcribing.
- User trust: did it feel safe to send without rereading?

## Sources

- Wispr Flow homepage: https://wisprflow.ai/
- Wispr Flow pricing: https://wisprflow.ai/pricing
- Wispr Flow privacy/security: https://wisprflow.ai/privacy
- Aqua Voice homepage/pricing: https://aquavoice.com/
- Superwhisper homepage/pricing: https://superwhisper.com/
- BetterDictation homepage/pricing/FAQ: https://www.betterdictation.com/
- Otter.ai pricing: https://otter.ai/pricing
- Nuance Dragon: https://dragon.nuance.com/en-us/home-professional-and-consumer
- TechRadar best dictation software 2025: https://www.techradar.com/best/dictation-software
- Tom's Guide on Google AI Edge Eloquent: https://www.tomsguide.com/ai/google-just-launched-a-free-ai-dictation-app-that-fixes-your-speech-and-it-even-works-offline
- TechRadar hands-on with Google AI Edge Eloquent: https://www.techradar.com/ai-platforms-assistants/i-tried-using-googles-new-offline-ai-dictation-app-and-polished-my-ramblings-surprisingly-well
