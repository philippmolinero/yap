# Competitive roadmap: Yap, Aqua Voice, and Wispr Flow

Date: 2026-10-22

Issue: [PHI-354](https://linear.app/smoovara/issue/PHI-354/yap-reverse-engineer-aqua-voice-wispr-flow-then-substantially-improve)

This is the public-research half of that issue. It describes Yap as the Swift app in `macos/` works today, compares it with Aqua Voice and Wispr Flow from public sources, and proposes follow-up pull requests. A later pass on Philipp's Mac, with the apps installed and [REA](https://github.com/morluto/rea), should answer the questions at the end. That pass should record behavior. It should not copy model weights, prompts, UI assets, or other proprietary material into this repo.

The June 2026 [dictation market scan](2026-06-24-dictation-market-scan.md) is still useful as a wider map (Superwhisper, BetterDictation, Dragon, Otter). Pricing and feature claims for Aqua and Wispr in that note are out of date. This document replaces them for those two products. The August pipeline notes describe the retired Python app under `legacy/` (Groq or Mistral for speech, then a separate cleanup model). They are not a description of the running app.

Granola had no accessible notes on Yap, Aqua, Wispr, Gemma, or a microphone in the last 30 days. The product direction used here is the issue itself: study how Aqua and Wispr work, and treat a local model or a better microphone as possible parts of the fix, not as the plan. The issue records that a Gemma 4 E4B model and a Jabra microphone were recommended and that no decision was made.

## Yap today

Yap is a personal macOS menu-bar app. Hold Right Option or Right Control, speak, release, and the text is pasted into the app that was focused when the key went down. Double-tap the same key within 300 ms for hands-free; tap again to stop. There is no account, no subscription, and no second device. The Gemini API key lives in the Keychain.

### Architecture

| Piece | Where | What it does |
| --- | --- | --- |
| Menu bar, Settings, overlay, hotkey, mic, paste | `macos/Sources/Yap/` | The shell. SwiftUI `MenuBarExtra`, a floating capsule, a listen-only `CGEventTap`, `AVAudioEngine`, clipboard `Cmd+V`. |
| Config, Gemini client, pipeline, history, metrics | `macos/Sources/YapCore/` | No AppKit. The pipeline is an actor: record, transcribe, paste. |
| State | `~/.config/yap/` | `config.toml`, `vocabulary.txt`, `history.json` (15 strings), transcript-free `pipeline_metrics.jsonl`, `yap.log`, and a WAV only when transcription fails. |

Permissions are Input Monitoring (the trigger), Microphone, and Accessibility (posting `Cmd+V` and reactivating the target app). Launch at login is a Settings toggle.

### Pipeline

1. **Key down.** The pipeline stores the frontmost app's pid and bundle URL. That is the paste target. Nothing about the app is sent to Gemini. A live session opens if the transcriber can stream.
2. **Capture.** `AVAudioEngine` taps the default input, converts to 16 kHz mono PCM16, and keeps the frames in memory. The same frames are written to the Gemini live socket. Audio is buffered locally until the socket setup completes, then flushed in order. The socket sends are strictly serialized: setup, activity start, audio, activity end. Gemini's own activity detection is disabled, so the key is the turn boundary.
3. **While held.** The overlay says "Listening" and draws a level meter. The start chime plays on the first audio frame, not on key down. Silence below an RMS of 0.008 for 5 seconds (configurable, or off) stops the recording. A hotkey watchdog releases a stuck hold when macOS drops the key-up.
4. **Key up.** The recorder stops and the frames are also encoded as one WAV. Queued live frames are drained, then the turn is closed. The app waits for Gemini's finalized input transcription. If that text is empty or the socket fails with nothing usable, the WAV is posted to Gemini's unary transcription endpoint. A transport failure that already produced partial text keeps that text instead of falling through.
5. **Paste.** There is no second model call. Smart mode asks Gemini's transcription API for cleaned text. Verbatim asks for the words as spoken, fillers included. The paster snapshots the clipboard, writes the transcript, activates the original app if it is still running, waits the configured 50 ms, posts `Cmd+V`, and restores the clipboard about 350 ms later. If the target has quit, or Accessibility is missing, the text stays on the clipboard and the menu says so.
6. **After.** The line is prepended to history. Metrics record durations, provider, model, language, character count, success, and whether the live socket was used. They do not record the words. A failed transcription stashes the WAV for "Retry Failed Dictation". Sleep cancels the recording and drops the hotkey tap until wake.

Default model id is `gemini-3.5-transcribe`. The live socket uses that id plus `-live`. Language defaults to the allowed list `en` and `de` (sent as `en` and `de-DE`). Settings can pin English, German, or Thai, or leave detection on. Vocabulary is a newline list, capped at 100 terms, sent as Gemini `customVocabulary` / `custom_vocabulary`. The bundled seed list is mostly project names (`Claude Code`, `Voxtral`, `Cerebras`, and similar). Editing it means "Open Vocabulary", which opens the text file.

### Latency path

Release-to-paste time is the sum of:

- Stopping the audio engine and building the WAV (the WAV is not on the live path's critical section, but stop is).
- Draining audio that was still queued, including anything buffered before setup completed.
- Gemini finalizing the turn. A transcript that arrives after the activity end, before turn-complete, starts a 0.75 s grace window so a late chunk can land. Turn-complete with text already in hand completes immediately. The final wait is otherwise capped at 20 s, setup at 10 s, and the unary fallback at 45 s plus retries.
- Clipboard write, the 50 ms paste delay, and up to another 50 ms if the target app has to be activated.

The live socket is opened on key down, not kept warm while idle. The microphone engine also starts on key down. Partials from the live socket are accumulated and joined at the end. The overlay never shows them. No number in this repo is a measured release-to-paste latency for this Gemini path. The August benchmark's sub-second cleanup figures are for the retired two-step pipeline.

### UX surfaces

- **Trigger.** Right Option, Right Control, or both. Hold to talk, double-tap to toggle. Not remappable to an arbitrary key, mouse button, or Fn.
- **Overlay.** A small capsule: "Listening" with a waveform, then "Transcribing", then gone. No draft text, no app name, no "pasted" confirmation.
- **Menu.** Status line, Stop, Retry, a Recent menu of 15 clipped lines (click pastes again, without switching back to the original app), Settings, Open Vocabulary, Quit.
- **Settings.** API key, Smart vs Verbatim, language, which of the two trigger keys, silence auto-stop from 2 to 20 seconds, the three permissions, launch at login.
- **Sound.** Start on first frame, stop when processing begins, the system error sound on failure.

What the product deliberately does not have: an account, a cloud history, per-app tone, snippets, a command or edit mode, screen context, a dictionary UI, a microphone picker, streaming words into the focused field, or a "send" command.

## Aqua Voice, from public sources

Aqua is a commercial dictation app for Mac, Windows, iPhone, and Android, from a Y Combinator W24 company. On the desktop you hold one key and it inserts cleaned text at the cursor in any field. The company's own description of the product, updated in the copy fetched for this note, is [aquavoice.com/llms.txt](https://aquavoice.com/llms.txt).

### Model

Aqua replaced an earlier Whisper pipeline with **Avalon**, its own speech model, in August 2025. The [launch post](https://aquavoice.com/blog/introducing-avalon) says Avalon is trained for human-computer speech (prompts, code, email), not audiobooks, and that user audio was not used for training unless the user opted in. The [model card](https://app.aquavoice.com/research/avalon-model-card.pdf) says training mixed public audio, audio from the internet, and a subset from opted-in Aqua users.

Published figures, all Aqua's own reporting unless noted:

- Open ASR Leaderboard, October 2025: Avalon v1 at 6.24% average WER, which Aqua describes as 6th overall and 1st among proprietary models at that snapshot ([leaderboard post](https://aquavoice.com/blog/avalon-openasr-leaderboard), [Hugging Face board](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard)).
- Avalon 1.5, April 2026, with the iOS app: 5.55% WER on that board, more than twice as fast as v1, and a 76% win rate in Aqua's blind comparison with ElevenLabs Scribe v2 ([iOS post](https://aquavoice.com/blog/aqua-voice-for-ios)).
- AISpeak-10, Aqua's own English technical-term set: Avalon 97.4% versus Whisper Large v3 at 65.1% on the [homepage](https://aquavoice.com/). The same page's llms.txt also lists ElevenLabs Scribe 78.8%, Voxtral Mini 59.5%, and NVIDIA Canary 51.5%.
- A [9to5Mac](https://9to5mac.com/2025/08/15/aqua-voice-shows-just-how-good-mac-dictation-could-be-if-apple-just-tried/) side-by-side on one passage: 17 errors for macOS Dictation, 1 for Aqua.

Instant Mode runs on Avalon. Realtime Mode streams audio to a third-party realtime provider. The subprocessor list is in the [Trust Center](https://app.vanta.com/aquavoice.com/trust/6f0ehpcbakfh2e73cnoo3r). There is also an OpenAI-compatible batch API, `avalon-v1.5`, priced at $0.39 per audio hour ([API docs](https://aquavoice.com/docs/api)).

Aqua describes the product as Avalon fused with language-model post-processing, not raw ASR ([llms.txt](https://aquavoice.com/llms.txt)). The public pages do not name the post-processing model.

### Latency claims

From the same llms.txt, which is marketing copy rather than a measured SLA:

- "Starts in under 50 ms" and "inserts text in about a second (as fast as ~450 ms)."
- Instant Mode, the default on every plan: startup under 200 ms, text about 450 ms after you stop. The 50 ms and 200 ms startup figures both appear in that file.
- Realtime Mode: words appear while you talk. The text is still inserted when you finish, not keystroke by keystroke into the target app.

The [realtime page](https://aquavoice.com/realtime) says the live line is rough and then "resolves into clean, punctuated text a beat behind you." [Deep Context](https://aquavoice.com/deep-context) claims it reads the screen during speech and, if it is not finished when you stop, the paste proceeds without it.

### UX that matters for Yap

- **Hotkey.** Default is Fn on Mac and Alt on Windows ([llms.txt](https://aquavoice.com/llms.txt)). Keybindings are editable, more than one binding is allowed, and a conflict with the default is a documented FAQ ([FAQ](https://aquavoice.com/info/faq)). Hold to talk is Instant Mode.
- **Hands-free and realtime.** Double-press the Aqua key (or hold it and tap Space) to go hands-free. Realtime is on by default in that mode. Settings also offer "Realtime always" and "Instant always" ([realtime FAQ](https://aquavoice.com/realtime)).
- **Inline editing.** [Edit Mode](https://aquavoice.com/guide/edit-mode) (desktop 0.17.0, July 2026, every plan): if text is selected, the same hold-to-talk key becomes an edit. A chip shows how many words are selected. You say the change ("make it shorter", "it's T-O-N-I", or just the corrected sentence) and the selection is replaced. Nothing selected means ordinary dictation. Search fields, the address bar, and selections over 6,000 characters stay in dictation. There is no spoken undo. iOS has a separate voice edit of the last transcript.
- **Context.** [Deep Context](https://aquavoice.com/deep-context) is off until you enable it, on every desktop plan. One screenshot at the start of the dictation, words and code pulled out, image discarded. Privacy Mode also redacts the extracted words. It needs macOS Screen Recording. The published examples are the ones Yap feels: "Geoff" versus "Jeff", `TaskFilters` versus "task filters", names in an open mail thread. The dictionary is the stable list. Deep Context is the list for this screen only.
- **Dictionary, replacements, instructions.** The [dictionary](https://aquavoice.com/guide/dictionary) is a list of hard words and keeps casing, including invented names. [Replacements](https://aquavoice.com/guide/replacements) expand a short spoken phrase into a URL, a prompt, or boilerplate, and are a different feature from the dictionary. [Custom instructions](https://aquavoice.com/guide/custom-intructions) are natural-language rules with good and bad examples (email shape, no em dashes, UK spelling, how hard to cut fillers). Pro and above. An [Aqua CLI](https://aquavoice.com/docs/cli) can edit dictionary, replacements, and instructions from a terminal and sync them to the account.
- **Per-app formatting.** The [FAQ](https://aquavoice.com/info/faq) says Aqua formats for the app you are in. Custom instructions are the user-facing control. File tagging in Cursor and Windsurf turns a spoken filename into an `@file` mention ([guide](https://aquavoice.com/guide/file-tagging)).
- **Send it.** On Realtime, ending with "send it" (also Japanese, Spanish, French, German "schick es ab", Russian) strips the command, inserts the text, and presses a send shortcut. Auto picks Enter in Slack, Command-Enter or Ctrl-Enter in Gmail and Outlook, and no send key in Notes or Word. A mid-sentence "send it" is left as words ([realtime page](https://aquavoice.com/realtime), [send-it post](https://aquavoice.com/blog/introducing-send-it)). Max and Business, with a free-tier preview inside the first 1,000 words.
- **History and privacy.** Local history of transcripts and audio ([llms.txt](https://aquavoice.com/llms.txt)). Audio is processed in the cloud and is not sold. Privacy Mode off (the default) may store transcripts to improve the product. Privacy Mode on stores no transcripts. Session metadata can still be collected. Business can force Privacy Mode and zero data retention. SOC 2 Type II, ISO 27001, and GDPR and HIPAA programs ([trust writeups](https://aquavoice.com/blog/soc2)).
- **Not the wedge.** Computer Control (voice agent for pointer and keyboard, Max, Mac beta) and Aqua Pet are real, and they are the wrong direction for a one-person menu-bar tool.

### Pricing

Fetched from [aquavoice.com/pricing](https://aquavoice.com/pricing) on 2026-10-22:

| Plan | Price | What they list |
| --- | --- | --- |
| Free | $0 | 1,000 words, Avalon. Realtime can be tried inside that allowance. |
| Pro | $8/month billed annually, or $10 month-to-month | Unlimited words, custom instructions, expanded custom dictionary. |
| Max | $24/month billed annually, or $30 month-to-month | Pro, plus live words, "send it", early access. |
| Business | $19/seat/month billed annually, or $24 month-to-month, 2 seats minimum | Max, plus SSO/SAML, SCIM, reporting, zero data retention, team dictionaries. |

Students get 70% off Pro and Max. The June scan's "5 dictionary entries versus 800" is no longer on the pricing page. Current copy only says "expanded." Dictionary size is an open question for the local pass.

49 languages are listed, including English, German, and Thai ([llms.txt](https://aquavoice.com/llms.txt)).

## Wispr Flow, from public sources

Wispr Flow is the broad commercial product: dictation in every app, on Mac, Windows, iPhone, and Android, plus a meeting notetaker. The homepage promise is that the text reads like you wrote it ([wisprflow.ai](https://wisprflow.ai/)).

### Model

Flow is cloud transcription plus a formatting pass. The September 2025 engineering note by Sahaj Garg sets the internal budget at a full transcript and LLM formatting within 700 ms of stopping: under 200 ms ASR, under 200 ms LLM, under 200 ms of network ([technical challenges](https://wisprflow.ai/post/technical-challenges)). That is a target, not a published SLA. The 9 July 2026 [what's-new](https://wisprflow.ai/whats-new) note says dictation latency was down 30% since the start of the year, again without a millisecond figure.

On 17 September 2026 Flow switched everyone to **Canto**, the first model from the Wispr Advanced Interfaces Lab ([what's new](https://wisprflow.ai/whats-new), [research note](https://wisprflow.ai/canto)). Canto is pretrained on millions of hours, then supervised-fine-tuned and post-trained with GRPO. The research note's eval is 10 hours of opted-in English Flow dictations from more than 2,300 speakers, plus a 3-hour challenge set (noise, whisper, far-field, one- and two-word clips). On the challenge set they rank Canto behind Gemini 3.1 Pro and ahead of the other realtime models they tested. On LibriSpeech, FLEURS, and Common Voice, without context, Canto only ties for the lead on LibriSpeech. They are explicit that read-speech benchmarks are the wrong distribution for dictation.

A LinkedIn post from the lab the same day states a 3.4% word error rate on that roughly 10-hour set, lowest among the models they compared (Google, OpenAI, AssemblyAI, Deepgram) ([post](https://www.linkedin.com/feed/update/urn:li:activity:7506406382796087296)). The figure is in the post, not in the article text. It is their eval, on their audio.

Canto is given the user's dictionary at runtime. The research note spends its length on the failure mode that matters for Yap: a dictionary term that sounds like the word you actually said ("Barry" versus "berry"). Reinforcement learning made the model more willing to use context and also more willing to follow a phonetically similar distractor. They treat "when to trust the list" as an open training problem.

The same lab note describes learning from user edits by grafting only the span that looks like a recognition fix, and discarding rewrites where the person changed their mind. The 2025 engineering note had already named this as the goal: never make the same mistake twice, with personalization data staying on device because of the latency and privacy budget.

### UX that matters for Yap

- **Hotkey.** Mac default is hold Fn to talk. Hands-free is Fn+Space, and double-tapping push-to-talk still toggles hands-free if that binding is cleared. Command Mode defaults to Fn+Ctrl. Paste-last and copy-last have their own shortcuts. Up to four bindings per action, at most three keys, mouse buttons allowed ([shortcuts](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts)).
- **Cleanup strength.** Auto Cleanup replaced a single smart-formatting switch. Four levels: None (verbatim, mistakes included), Light (fillers and grammar), Medium (clarity), High (rewrite for brevity). The raw text remains available in history as "Undo AI edit" ([what's new, 24 April 2026](https://wisprflow.ai/whats-new)). The homepage demo is the "actually, not Friday, the following Monday" correction.
- **Styles per app category.** Personal messages, work messages, email, and other. Formal, Casual, Very Casual (personal only), and Excited. Email style also adds greetings, sign-offs, and line breaks. The help center says these style rules are English-only ([styles](https://docs.wisprflow.ai/articles/2368263928-how-to-setup-flow-styles)).
- **Context awareness.** On by default on Mac and Windows. It reads text, and the help center says it does not take screenshots. Context can include the app, the website, the text before and after the cursor, the selection, on-screen text, code symbols, and conversation history. Password fields are skipped. Banking apps are skipped. If the read is slow, it is dropped so dictation is not delayed. With the feature off, Flow still sends the app name and site domain to pick a tone, and still matches capitalization and spacing locally from the text around the cursor ([context awareness](https://docs.wisprflow.ai/articles/4678293671-feature-context-awareness)). Browsers are recognized as the site, so Slack in Chrome is work chat and Gmail in Chrome is email. Cursor and Windsurf get file tagging. Continuing a lowercase Slack draft stays lowercase.
- **Dictionary and snippets.** You can add terms, and the homepage says Flow also learns names and jargon. [Snippets](https://docs.wisprflow.ai/articles/5784437944-create-and-use-snippets) are a spoken trigger expanded to saved text, including inside a sentence. Personal wins over team on the same trigger. The longest match wins. Desktop snippets can carry rich text as of the changelog.
- **Command Mode and transforms.** [Command Mode](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode) is a separate hold shortcut, off until enabled, paid plans. You speak an instruction. Flow sends the box contents and the selection (copying the selection if it cannot read it) and pastes the result without the normal dictation formatter. It also drafts into an empty box, and can open a web search. Transforms are the other edit surface: highlight text, run Polish or Prompt Engineer, or your own prompt. A transform can also run after every dictation. Auto Cleanup is "while you dictate." Transforms are "this text, this instruction" ([what's new, 1 May 2026](https://wisprflow.ai/whats-new)).
- **History.** Cloud or local depending on sync settings. Quitting mid-dictation saves audio and History can finish it. Scratchpad is a floating notepad (Option+S), separate from dictation.
- **Microphone advice.** The homepage FAQ says the built-in mic is enough, a closer mic helps when you speak quietly, and AirPods and other Bluetooth headsets are the setup they tell people to avoid because of compression and clipped onsets ([homepage FAQ](https://wisprflow.ai/)).
- **Privacy.** Transcription is always in the cloud. "Improve the model for everyone" (formerly Privacy Mode) controls training use. Private Cloud Sync controls whether audio and transcripts are stored. Both off is what they call zero data retention ([data controls](https://wisprflow.ai/data-controls), [privacy](https://wisprflow.ai/privacy)). SOC 2 Type II, ISO 27001, HIPAA. Context awareness is a separate toggle from training opt-out.
- **Not the wedge.** Notetaker, team dictionaries, SSO, insights, streaks, and leaderboards are the enterprise product around the dictation loop. Yap should not grow a meeting bot to copy them.

### Pricing

US card prices from the help center article updated shortly before this note, and the [pricing page](https://wisprflow.ai/pricing):

| Plan | Price | What they list |
| --- | --- | --- |
| Free | $0 | Desktop allowance 2,000 words/week, hard stop at 5,000, reset Sunday. iOS and Android have smaller pooled limits. Dictionary, snippets, limited notetaker. At the allowance, dictation slows. At the cap, it stops. |
| Pro | $15/user/month, or $12/month billed annually ($144/year) | Unlimited dictation, longer notetaker history, team billing. Command Mode is documented as a paid feature. |
| Growth | $23/user/month dictation-only ($18 annual), or $33 with Notetaker ($26 annual) | SSO, admin, org-wide HIPAA. Notetaker is the expensive add. |
| Enterprise | Custom | SCIM, MDM, training forced off. |

Trials: 14 days by default, 30 with a referral, 90 for students ([plans article](https://docs.wisprflow.ai/articles/9559327591-flow-plans-and-what-s-included)). 100+ languages. For accuracy they recommend selecting the language you are speaking rather than leaving several selected ([homepage FAQ](https://wisprflow.ai/)).

## Feature matrix

"Yap" is the Swift app. "Public" means the vendor's site, docs, or changelog. Blank cells would hide uncertainty, so unknowns are marked.

| Capability | Yap today | Aqua Voice | Wispr Flow |
| --- | --- | --- | --- |
| Where it runs | macOS menu bar, one Mac | Mac, Windows, iOS, Android | Mac, Windows, iOS, Android |
| Activation | Hold Right Option and/or Right Control. Double-tap toggles hands-free. | Hold Fn (Mac) or Alt (Windows). Double-press hands-free. Bindings are editable. | Hold Fn. Fn+Space hands-free. Double-tap push-to-talk also toggles. Mouse buttons allowed. |
| Insert | Clipboard, then `Cmd+V`, then restore. Reactivates the app from key-down. | Inserts at the cursor. Mechanism not public. | Pastes at the cursor. Command Mode copies the selection if it cannot read it. |
| Live words before paste | Partials are received and hidden. Overlay says Listening / Transcribing. | Realtime shows words in the toolbar, then cleans them. Instant does not. Realtime is Max. | Not described as a live caption. The bar shows processing states such as "Cleaning up…". |
| Cleanup | One switch: Smart or Verbatim, inside the Gemini transcription request. No second model. | Avalon plus an unnamed LM post-process. Custom instructions on Pro. | Separate ASR and LLM. Auto Cleanup has four strengths. Raw text kept. |
| Self-corrections ("actually, Monday") | Not a documented behavior. Smart mode may do some of this. Unmeasured. | Marketed via realtime mid-sentence fixes ("change Thursday to Friday") before send. | Homepage and help center. A primary demo. |
| Names and code on screen | Static `vocabulary.txt`, 100 terms, every turn. No screen read. | Deep Context: one screenshot at start, words extracted, image dropped. Off by default. Every desktop plan. | Context awareness reads text (not screenshots): field, selection, on-screen words, code symbols. On by default. Dropped if slow. |
| Personal dictionary | Text file, opened in an editor. Seeded with a few project names. | In-app dictionary, casing preserved, synced, CLI. Size of "expanded" is not published. | In-app dictionary, can learn terms, shared on teams. Injected into Canto at runtime. |
| Snippets | None. | Replacements: spoken phrase to saved text. | Snippets, including mid-sentence and rich text on desktop. |
| Tone per app | None. The bundle id is stored only to paste back. | Formats for the destination app. Custom instructions. File tags in Cursor and Windsurf. | Four app categories, four styles. English-only style rules. Email structure. Local casing match even if context upload is off. |
| Edit existing text | None. | Same hotkey, if a selection exists. Every desktop plan. | Command Mode (separate key, paid) and Transforms (Polish, Prompt Engineer, custom). |
| Send the message by voice | None. | "Send it" and localized equivalents, app-specific shortcut, Max. | Not the same feature. Command Mode can search or draft. |
| Languages | Settings: auto, English, German, Thai. Default bias en + de. | 49 listed, including German and Thai. | 100+. They prefer one language selected. Style formatting is English-only. |
| History | 15 final strings. No audio, no raw-versus-cleaned. | Local transcripts and audio. | History with undo-AI-edit. Crash recovery of audio. Optional cloud sync. |
| Privacy posture | Audio goes to Gemini with the user's own key. Metrics and logs store no transcript. Failed audio stays local. | Cloud. Privacy Mode skips transcript storage. Business zero-retention. SOC 2, ISO 27001, GDPR, HIPAA program. | Cloud always. Training opt-out and storage opt-out are separate. SOC 2, ISO 27001, HIPAA. |
| Latency, as claimed | No current-app measurement in the repo. | About 450 ms after you stop in Instant Mode. Startup 50 ms or 200 ms, both stated. | Internal target: 700 ms for ASR plus LLM. "Down 30% since January 2026," no absolute number. |
| Mic | Default input. No picker. No Bluetooth warning. | Not specified in the pages read. | Built-in mic is fine. They advise against Bluetooth headsets. |
| Price to the person using it | Gemini API usage. | $8/month annual for the writing features. $24/month annual for live words and send. | $12/month annual for unlimited. Free tier is 2,000 desktop words/week. |

## Gaps, ranked

Ranked for one person dictating into Slack, mail, notes, and coding agents on a Mac. Impact is how often the current loop produces text you have to fix, or makes you wait. Effort is one change in this Swift app, not a company.

| Rank | Gap | Impact | Effort | Why it is this high |
| --- | --- | --- | --- | --- |
| 1 | The words on screen never reach the model. Names, file names, and function names depend on a hand-edited list of 100. | Highest. This is the mistake you notice in Claude Code, Cursor, and email. | Medium | Both products built a feature for it. Aqua's examples are exactly this failure. Yap already has a per-turn vocabulary channel and already holds the target pid. |
| 2 | Cleanup is a single global switch, with no per-app tone and no measured self-correction behavior. | Highest. Every paste. A Slack line and a German email should not come out the same shape. | Medium | Wispr's category styles and Aqua's instructions are the writing product. Yap's Smart mode is an opaque API enum. |
| 3 | No replacements. Repeated signatures, links, and prompt preambles are re-dictated. | High, daily, and it does not need a model. | Low | Both products split this from the dictionary on purpose. A spoken phrase is not a spelling. |
| 4 | You cannot see words until the paste. Long turns feel like a wait, and a bad paste is the first feedback. | High for trust. | Medium | The live socket already returns partial transcripts. The overlay throws them away. Aqua's realtime page is this feeling, minus their Max-only send command. |
| 5 | No way to speak a change to text that is already selected. | High once dictation is good enough that the leftover work is editing. | Medium | Aqua made this the same key, which is the interaction to copy. Wispr needed a second key and a paid plan. Paste-over-selection already works if the selection is still selected. |
| 6 | Release-to-paste latency is unmeasured on the Gemini path, and the socket and mic both start cold. | High if the wait is the complaint. Unknown until measured. | Medium to measure, then small or large | Aqua's whole pitch is ~450 ms. Wispr's budget is 700 ms including the LLM. Yap cannot choose a model or a microphone honestly until `pipeline_metrics.jsonl` has a current p50 and p95. |
| 7 | Dictionary is a file, and a correction never teaches the next turn. | Medium, and it compounds with rank 1. | Low | The list exists. The UI and the correction loop do not. |
| 8 | No "send it." | Medium for chat. Easy to press the wrong key in the wrong app. | Medium | Aqua's version is carefully last-phrase and per-app. Worth doing after the paste itself is trustworthy. |
| 9 | Microphone is whatever macOS defaults to. Bluetooth is a known dictation hazard, and a Jabra was suggested with no decision. | Unknown. Could dominate accuracy and the clipped first syllable. | Low for a picker and a warning. Buying hardware is outside the repo. | Wispr's FAQ is the public evidence. Do not buy from this document. |

Explicitly not gaps Yap should close in this round: meeting notetaker, team admin, SSO, mobile clients, a voice agent that drives the pointer, a pet, streaks, and leaderboards. Those are how the commercial apps expand. They do not make the hold-release-paste moment better.

## Proposals

Each item is one pull request against `macos/`. Order is the order to do them. Later items assume the measurement PR has landed so a change can be accepted or reverted on evidence.

### 1. Report release-to-paste from the metrics file

Add `Yap --metrics` (or a section of `--doctor`) that reads `pipeline_metrics.jsonl` and prints count, p50, and p95 of `totalSeconds` and `transcriptionSeconds`, split by `usedLive` and by success. Do not print text. The fields already exist on `PipelineMeasurement`.

Done when a local run of ten dictations produces a p50 and a p95 for the live path, and the August benchmark is no longer the number people quote. This PR does not change the model.

### 2. Turn-local context from the focused field and window

On key down, if a new Settings switch is on, read the focused element's text and the window title through Accessibility, which Yap already requires to paste. Extract a bounded set of tokens that look like names, CamelCase, snake_case, and file names. Merge them in front of `vocabulary.txt` for that turn only, still capped at 100. Do not write them to disk. Do not take a screenshot. Default the switch to off.

This is Wispr's text context, not Aqua's screenshot. A screenshot sees pixels the accessibility tree misses, and it needs Screen Recording. The local REA pass should decide whether the tree is enough before anyone adds a screenshot.

Done when a dictation of "task filters" with `TaskFilters` in the focused editor comes back as `TaskFilters` with the switch on, and the same audio without the switch does not gain that spelling from a previous turn. Tests use a fake context source, not a live UI.

### 3. App-category formatting in front of the paste

Classify the stored bundle id (and, where Accessibility can see it, the site) into chat, email, code, or prose. Apply a small local pass after transcription:

- Chat: if the field already starts in lowercase, do not capitalize the continuation. Drop a trailing period on a short utterance. Do not invent this for Thai or for a single proper noun.
- Email: keep Smart mode's sentences. Do not add a sign-off in this PR.
- Code and terminal: do not capitalize identifiers the context pass just recovered. Prefer Verbatim-like preservation of symbols when the utterance is clearly a path or a flag.
- Prose: leave Smart mode's text alone.

Ship the categories as data in Settings, with a default map for the apps actually used (Slack, Messages, Mail, Cursor, Terminal, and a few browsers). Unknown apps stay on the global Smart/Verbatim switch.

Done when the same Smart transcript is formatted two different ways for two bundle ids in a unit test, and a German or Thai transcript is not run through the English chat rules.

### 4. Replacements

A `replacements.toml` of spoken trigger to expansion, edited in Settings, applied to the finished transcript before paste. Longest match wins. Case-insensitive trigger, expansion pasted as stored. No network.

Done when "my email" inside a longer sentence expands, and a trigger that is also a dictionary word does not fire unless the whole token matches.

### 5. Show the live partial in the overlay

Thread partial input transcripts out of `GeminiLiveSession` into the capsule as a single updating line. Paste only the final string, once. If the final differs from the last partial, the overlay can show the corrected line for a moment before it hides. Do not insert partials into the target app.

Done when a test double that emits two partials and a final results in one paste of the final text, and the overlay model observed the partials.

### 6. Dictionary in Settings, plus one correction action

Replace "Open Vocabulary" as the primary UI with an add/remove list bound to `vocabulary.txt`. Keep the file as the storage format. In the Recent menu, add "Remember spelling…" on the last item: the person marks a span, and that span is appended to the list if it is not already there and the list is under 100.

Done when a term added in Settings is on the next Gemini payload, and a duplicate is not stored twice.

### 7. Selection edit on the same key

At key down, if Accessibility reports a non-empty selection under a few thousand characters, record it. On release, send that selection plus the utterance to one text call whose only job is to return the replacement, then paste, which overwrites the selection. No selection means today's dictation path, including context and replacements. Refuse to edit password fields. If the selection cannot be read, dictate as usual.

Done when a fixture selection "see you Tuesday" and the utterance "make it Monday" pastes "see you Monday" and does not also paste the words "make it Monday". This PR needs a prompt that is tested against "delete that", a spelling correction, and an utterance that is obviously new dictation rather than an edit. If that last case is unreliable, gate the feature behind a switch instead of guessing.

### 8. Warm the live socket, not the microphone

After launch and after wake, open the Gemini live setup and keep it idle until the next hold, with a timeout and a reconnect. Do not start `AVAudioEngine` while idle. The menu-bar mic indicator should stay off until the key goes down.

Done when a test shows audio frames from the start of a turn are not held for setup, and a failure of the warm socket falls back to today's connect-on-key-down path. Compare `--metrics` before and after on the same kind of utterance before calling it a win.

### 9. Optional send phrase, off by default

If the finished text ends with "send it" or "schick es ab", strip that phrase and, for an allowlist of bundle ids, post Enter or Command-Enter. Everywhere else, strip nothing and paste the words. A mid-sentence occurrence is pasted as words.

Done when the allowlist and the two phrases are covered by tests, and an unknown app never receives Enter. Ship the switch off.

Leave these out until the nine above have been measured: a second cleanup model (Gemma or otherwise), a screenshot Deep Context, a microphone implementation, file tagging, and any sync or account.

## What the local REA pass should answer

REA on the Mac where Aqua and Wispr are installed. Inspect behavior, versions, and which system APIs fire. Write findings up as notes. Do not copy binaries, model weights, prompts, icons, or transcript fixtures from those apps into git.

### Timing

- On a hold-to-talk Instant/push-to-talk turn, when does the first network write happen relative to key down, first audio frame, and key up? Is a socket already open while idle?
- What is release-to-visible-text for a 5-second utterance and for a 30-second one, on this machine and this network? Five trials each. Yap's `--metrics` from PR 1 is the comparison number.
- Does any local log already record their stage timings? If so, note the field names, not the contents of transcripts.
- Does the mic device open on key down or stay open? Is there a visible recording indicator while idle?

### Audio

- Sample rate, channel count, and whether they stream PCM or an encoded chunk.
- Do they select a device, warn on Bluetooth, or apply their own gain? The Jabra question waits on this plus a Yap recording of the same sentence on the built-in mic and on a wired headset.
- What happens to the first 200 ms of speech?

### Context

- Aqua Deep Context: one screenshot or more, resolution, and is the image OCR'd locally or uploaded? What is extracted (all text, or tokens)? Is the image written anywhere, even briefly?
- Wispr: which Accessibility attributes are read (value, selected text, bounds of other elements)? Is any pixel capture used despite the docs saying no?
- For both: is context attached to the ASR request, a second LLM request, or both? What is sent when the feature is off, besides the app name?
- How many dictionary terms are actually attached, and does a long list change latency?
- Can a distractor in the dictionary override a clearly spoken common word? Try "berry" with "Barry" saved, on a quiet mic and a noisy one.

### Formatting and editing

- Is cleanup a second request after ASR, or one response? If a prompt is stored locally, describe its rules in a sentence or two. Do not paste the prompt into the repo.
- Does Auto Cleanup / Smart rewrite "actually, Monday" style repairs before paste? Keep the before and after in the REA notes, not in git.
- Edit Mode and Command Mode: how do they read the selection (AX, copy, both)? What do they paste back (plain string, styled pasteboard)?
- Send-it: the concrete shortcut table for Slack, Gmail, Messages, and a notes app, and whether the command is detected on device.

### Product facts the sites left open

- Aqua's current dictionary cap on Free versus Pro, since the pricing page no longer states one.
- Whether Aqua Instant Mode is Avalon-only or still has a formatting request after ASR.
- Which third party receives Aqua Realtime audio, from the app's own network list rather than the marketing page.
- Wispr's achieved p50 and p95 if the client records them, against the 700 ms target.
- Whether either app's "learns your words" path writes a new dictionary entry automatically, or only biases the next request.

### Out of scope for that pass

Model extraction, bypassing license checks, and anything that would turn their client into a Yap dependency. The output of the pass should be a short addendum to this file: what they confirmed, what they could not see, and which of the nine PRs to reorder.

## Sources

Aqua Voice:

- [Homepage](https://aquavoice.com/)
- [Pricing](https://aquavoice.com/pricing)
- [Product overview used by their site (llms.txt)](https://aquavoice.com/llms.txt)
- [Realtime Mode](https://aquavoice.com/realtime)
- [Deep Context](https://aquavoice.com/deep-context)
- [Dictionary](https://aquavoice.com/guide/dictionary)
- [Custom instructions](https://aquavoice.com/guide/custom-intructions)
- [Edit Mode](https://aquavoice.com/guide/edit-mode)
- [Replacements](https://aquavoice.com/guide/replacements) and [file tagging](https://aquavoice.com/guide/file-tagging)
- [FAQ](https://aquavoice.com/info/faq)
- [CLI](https://aquavoice.com/docs/cli)
- [Introducing Avalon](https://aquavoice.com/blog/introducing-avalon) and the [model card PDF](https://app.aquavoice.com/research/avalon-model-card.pdf)
- [Avalon on the Open ASR Leaderboard](https://aquavoice.com/blog/avalon-openasr-leaderboard)
- [Aqua Voice for iOS, including Avalon 1.5](https://aquavoice.com/blog/aqua-voice-for-ios)
- [Introducing Send It](https://aquavoice.com/blog/introducing-send-it)
- [9to5Mac comparison](https://9to5mac.com/2025/08/15/aqua-voice-shows-just-how-good-mac-dictation-could-be-if-apple-just-tried/)

Wispr Flow:

- [Homepage](https://wisprflow.ai/)
- [Pricing](https://wisprflow.ai/pricing)
- [Plans and limits](https://docs.wisprflow.ai/articles/9559327591-flow-plans-and-what-s-included)
- [What's new](https://wisprflow.ai/whats-new)
- [Canto research note](https://wisprflow.ai/canto)
- [Lab LinkedIn post stating 3.4% WER](https://www.linkedin.com/feed/update/urn:li:activity:7506406382796087296)
- [Technical challenges (latency budget)](https://wisprflow.ai/post/technical-challenges)
- [Shortcuts](https://docs.wisprflow.ai/articles/2612050838-supported-unsupported-keyboard-hotkey-shortcuts)
- [Context awareness](https://docs.wisprflow.ai/articles/4678293671-feature-context-awareness)
- [Styles](https://docs.wisprflow.ai/articles/2368263928-how-to-setup-flow-styles)
- [Snippets](https://docs.wisprflow.ai/articles/5784437944-create-and-use-snippets)
- [Command Mode](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode)
- [Data controls](https://wisprflow.ai/data-controls) and [privacy](https://wisprflow.ai/privacy)

Yap, in this repo:

- `macos/README.md`
- `macos/Sources/YapCore/Pipeline.swift`, `GeminiClient.swift`, `AppConfig.swift`
- `macos/Sources/Yap/AppModel.swift`, `HotkeyMonitor.swift`, `Microphone.swift`, `Paster.swift`, `SettingsView.swift`
- [June 2026 market scan](2026-06-24-dictation-market-scan.md)
- [August 2026 pipeline notes](2026-08-09-yap-pipeline-improvements.md), which apply to `legacy/`
