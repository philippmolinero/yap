# Dictation loop plan

Yap stays a small always-ready Mac dictation tool. Five PRs shorten the wait after the hotkey, put the text back in the app that was focused at key down, and lock the cleanup instruction to a checked baseline.

The person dictating gets a paste that survives a focus change, a start chime that waits for the mic, and no second cleanup call on Gemini smart. The next engineer gets one press-time record and five checks that each stand alone.

The program enforces the verification rule in How to read this. PR order is yap-eval, yap-paste, yap-cue, yap-context, yap-warmup.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. Owners stop at merge-ready. The operator lands the stack. yap-paste, yap-cue, yap-context, and yap-warmup are the operator review items.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] On the operator's go, arm a `/goal` with this exact text. "docs/plans/2026-09-22-dictation-loop.md. PR order yap-eval, yap-paste, yap-cue, yap-context, yap-warmup. A PR is verified only when its unit, live, and perf boxes are all checked. The operator lands the stack. Done when every box in this plan has evidence."
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:pstack/skills/swarm/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:pstack/skills/principle-prove-it-works/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/principle-sequence-verifiable-units/SKILL.md`
  - [ ] `git show origin/main:pstack/skills/show-me-your-work/SKILL.md`
- [ ] Arm the 30-minute audit tick. In a local session, a real terminal `/loop`. In a cloud root, a cloud-sleeper wake chain. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk and the armed /goal. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a status message to the operator in chat, whether or not anything changed, with the queue table of PR, owner, state, and head SHA, the verdicts since the last tick, what merged, open operator gates, and blockers."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges, or base it on the parent branch when the execution playbook stacks.
  - [ ] yap-eval and yap-paste are independent and first. Both branch from `main`.
  - [ ] yap-cue after yap-paste. Both edit `app/main.py`. The cue behavior does not depend on the paste behavior.
  - [ ] yap-context after yap-cue. Both edit `app/main.py`. yap-context also edits `app/pipeline.py`, which yap-paste edits.
  - [ ] yap-warmup after yap-context. Both edit `app/pipeline.py` and `app/transcriber.py`. yap-warmup also edits `app/recorder.py`.
- [ ] Hold the file boundaries. yap-eval touches only `benchmarks/model_benchmark.py`, `evals/cleanup/`, and `tests/test_model_benchmark.py`. yap-paste touches only `app/paster.py`, `app/pipeline.py`, `app/main.py`, `tests/test_paster.py`, and `tests/test_pipeline.py`. yap-cue touches only `app/recorder.py`, `app/main.py`, `tests/test_recorder.py`, and `tests/test_pipeline.py`. yap-context touches only `app/press_context.py`, `app/transcriber.py`, `app/pipeline.py`, `app/main.py`, `tests/test_transcriber.py`, `tests/test_pipeline.py`, and `tests/test_history.py`. yap-warmup touches `app/gemini_live.py`, `app/transcriber.py`, `app/pipeline.py`, `app/recorder.py`, and `scripts/e2e_gemini_live.py`. This execution adds no new unit tests.
- [ ] Hold the review gate. yap-paste, yap-cue, yap-context, and yap-warmup change an interaction. They wait for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`. If `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, with `origin pr create --status open --base <base-branch>` or `gh pr create --base <base-branch>` according to the resolved forge. A stack child targets its parent branch.
- [ ] Run `.venv/bin/python -m pytest -q` once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review.
- [ ] Triage every Bugbot and security-reviewer comment per `pstack/skills/poteto-mode/references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before babysit and again before the merge-ready report.

### Verdict and merge, for every PR

- [ ] At the merge-ready head SHA, run the swarm per `pstack/skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. One audit lane that reads the diff and the receipts and distrusts the PR body.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner. A new head gets a fresh swarm and a fresh verdict.
- [ ] On a clean verdict the root appends the PR to the one linear stack. No owner merges. Compare `git patch-id` of the base-to-head diff at the verdict SHA with the diff after any later rebase. An unchanged patch-id preserves the code verdict. A changed patch goes back through the swarm before delivery.

### Boot recipe, for every live lane

Each live lane runs on its own cloud VM at the PR head. This app is a rumps menubar process. `control-ui` and `control-cli` do not drive it. Appendix C records that gap. The lane still runs the commands below and saves a screenshot.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Create no network servers. Use the repo `.venv`. Wait until `.venv/bin/python -m pytest -q --collect-only` prints a test count.
- [ ] Drive the lane with `.venv/bin/python -m pytest -q` on the test named in the lane. Read-only diagnostics are the pytest output and `pipeline_metrics.jsonl` when the lane names it. Do not type into the menubar from the VM.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` and return the paths with the report.

## Score the cleanup prompt (yap-eval)

**Depends on.** None.

**Files.**

- [ ] Edit `benchmarks/model_benchmark.py`.
- [ ] Edit `tests/test_model_benchmark.py`.
- [ ] Create `evals/cleanup/baseline.json`.

**Build.**

- [ ] Add a baseline check that hashes `CLEANUP_PROMPT` from `app/cleanup.py` and compares it to `prompt_sha256` in `evals/cleanup/baseline.json`.
- [ ] Keep `build_cleanup_samples` as the 50-case English and German corpus. Do not add a second corpus.
- [ ] Do not edit the string `CLEANUP_PROMPT`. Punctuation and capitalization stay allowed changes inside that string.
- [ ] Add `python -m benchmarks.model_benchmark --check-baseline evals/cleanup/baseline.json`. The command exits 0 when the hash matches and exits non-zero when `CLEANUP_PROMPT` changes without a baseline update. It makes no provider call.

**You see.**

- [ ] `.venv/bin/python -m benchmarks.model_benchmark --check-baseline evals/cleanup/baseline.json` prints `baseline-ok` and exits 0 on this PR.
- [ ] A one-character edit to `CLEANUP_PROMPT`, reverted before commit, makes the same command exit non-zero.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_model_benchmark.py` gains `test_cleanup_prompt_matches_checked_baseline`. Run `.venv/bin/python -m pytest -q tests/test_model_benchmark.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `tests/test_model_benchmark.py` at trunk and head. Trunk has the 50-case scorer and no `evals/cleanup/baseline.json`. Record that. Gate the new baseline check plus a still-green corpus test. Save `/tmp/swarm-yap-eval/worker-1/regression.png`. Pass when head prints `baseline-ok` and trunk still passes `test_default_cleanup_corpus_has_fifty_cases_and_bilingual_coverage`.
- [ ] Lane 2. Run the fifty-case count test. Save `/tmp/swarm-yap-eval/worker-2/fifty-cases.png`. Pass when the test reports 50 cases and both English and German.
- [ ] Lane 3. Run `test_quality_score_keeps_question_punctuation_significant`. Save `/tmp/swarm-yap-eval/worker-3/question-mark.png`. Pass when the test exits 0.
- [ ] Lane 4. Run `test_behavior_flags_detect_prefix_meta_and_punctuation_failures`. Save `/tmp/swarm-yap-eval/worker-4/behavior-flags.png`. Pass when the test exits 0.
- [ ] Lane 5. Run `test_meaningful_word_preservation_is_exact_per_case`. Save `/tmp/swarm-yap-eval/worker-5/word-preservation.png`. Pass when the test exits 0.
- [ ] Lane 6. Load sample `en_question` through `build_cleanup_samples`. Save `/tmp/swarm-yap-eval/worker-6/en-question.png`. Pass when `expected_cleanup` still ends with a question mark.
- [ ] Lane 7. Load sample `en_names_acronyms`. Save `/tmp/swarm-yap-eval/worker-7/names.png`. Pass when the expected text still contains `Cerebras` and `Voxtral Realtime`.
- [ ] Lane 8. Load one German sample from `build_cleanup_samples`. Save `/tmp/swarm-yap-eval/worker-8/german.png`. Pass when `language` is `de`.
- [ ] Lane 9. Confirm `CLEANUP_PROMPT` on head equals `CLEANUP_PROMPT` on trunk. Save `/tmp/swarm-yap-eval/worker-9/prompt-unchanged.png`. Pass when the two strings are equal.
- [ ] Lane 10. Run the baseline command with network disabled. Save `/tmp/swarm-yap-eval/worker-10/offline.png`. Pass when it prints `baseline-ok` without a socket error.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `.venv/bin/python -m benchmarks.model_benchmark --check-baseline evals/cleanup/baseline.json` at head, and wall time of `.venv/bin/python -m pytest -q tests/test_model_benchmark.py` at trunk and head. Trunk has no baseline command. The diff-added work is the hash check. The end state the user waits for is an unchanged cleanup instruction.
- [ ] Probe. Run the pytest file at trunk, then the baseline command at head, then the pytest file at head. Repeat the pair three times and record the median.
- [ ] Baseline. Record the trunk pytest median first.
- [ ] Rule. The head pytest median may not exceed the trunk median by more than 2 seconds. The baseline command median must finish in under 5 seconds. A missing `baseline-ok` line fails the PR.

**Review gate.** None. yap-eval is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends this PR to the base-branch stack. The operator lands the stack bottom-up.

## Restore the clipboard and the focused app (yap-paste)

**Depends on.** None.

**Files.**

- [ ] Edit `app/paster.py`.
- [ ] Edit `app/pipeline.py`.
- [ ] Edit `app/main.py`.
- [ ] Edit `tests/test_paster.py`.
- [ ] Edit `tests/test_pipeline.py`.

**Build.**

- [ ] At the start of `Pipeline.start_recording`, before `Recorder.start`, store the frontmost app from `NSWorkspace.sharedWorkspace().frontmostApplication()`. Keep the process identifier and the bundle URL in memory on the pipeline. Do not send them to a provider.
- [ ] Change `paste` in `app/paster.py` so it reads `generalPasteboard` items before `clearContents`, writes the transcript, posts Cmd+V, then restores the saved items after `delay_ms`.
- [ ] Add a generation counter inside `paste` so an older restore cannot overwrite a newer paste.
- [ ] Pass the stored app into the `paste` call in `Pipeline._process_audio`. Activate that app with `activateWithOptions_` before the keystroke.
- [ ] If that app is gone, do not post Cmd+V, do not restore the previous clipboard, and leave the transcript on `generalPasteboard`.
- [ ] Report that case through a new pipeline notice callback. `YapApp` sets `status_item.title` to `Status: Paste target closed. Text is on the clipboard.` Do not call `_on_pipeline_error`. That path plays `SoundFeedback.play_error` and sets `Status: Transcription failed`.
- [ ] Leave `YapApp._on_recent_click` calling `paste` with no target app. Recent-menu paste restores the clipboard and does not activate the recording target.

**You see.**

- [ ] A pipeline paste into a still-running target app logs `paste restored clipboard` and the target app is frontmost before Cmd+V.
- [ ] A pipeline paste whose stored process has exited logs `paste target missing` and the status line is `Status: Paste target closed. Text is on the clipboard.`

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_paster.py` gains `test_paste_restores_previous_clipboard_after_keystroke` and `test_paste_leaves_transcript_when_target_app_is_gone`. `tests/test_pipeline.py` gains `test_start_recording_stores_frontmost_app`. Run `.venv/bin/python -m pytest -q tests/test_paster.py tests/test_pipeline.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `tests/test_paster.py` at trunk and head. Trunk clears `generalPasteboard` and does not restore it. Record that. Gate the restore plus the end state that the previous clipboard string is back after the keystroke. Save `/tmp/swarm-yap-paste/worker-1/regression.png`. Pass when head restores the fake pasteboard string and trunk still passes `test_paste_prefers_cgevent_over_osascript`.
- [ ] Lane 2. Paste with a live target app double. Save `/tmp/swarm-yap-paste/worker-2/refocus.png`. Pass when activate is called before `_paste_via_cgevent`.
- [ ] Lane 3. Paste with a dead target. Save `/tmp/swarm-yap-paste/worker-3/target-gone.png`. Pass when Cmd+V is not posted and the transcript remains on the pasteboard.
- [ ] Lane 4. Two overlapping `paste` calls. Save `/tmp/swarm-yap-paste/worker-4/generation.png`. Pass when the older restore does not replace the newer transcript before the newer restore.
- [ ] Lane 5. Recent-menu paste with no target. Save `/tmp/swarm-yap-paste/worker-5/recent-menu.png`. Pass when no app is activated and the clipboard is still restored.
- [ ] Lane 6. Missing Accessibility trust. Save `/tmp/swarm-yap-paste/worker-6/accessibility.png`. Pass when `_show_accessibility_alert_once` still runs and the transcript is on the pasteboard.
- [ ] Lane 7. Unknown trust state. Save `/tmp/swarm-yap-paste/worker-7/osascript.png`. Pass when the osascript fallback still runs, matching `test_paste_uses_osascript_when_trust_state_is_unknown`.
- [ ] Lane 8. Notice callback for a missing target. Save `/tmp/swarm-yap-paste/worker-8/quiet-status.png`. Pass when the notice text is the closed-target status and `play_error` is not called.
- [ ] Lane 9. `start_recording` while state is already `RECORDING`. Save `/tmp/swarm-yap-paste/worker-9/ignored-start.png`. Pass when the stored frontmost app is left unchanged.
- [ ] Lane 10. Empty WAV from `Recorder.stop`. Save `/tmp/swarm-yap-paste/worker-10/empty-audio.png`. Pass when `paste` is not called.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time from entering `paste` until it returns, at trunk and head, with `delay_ms` 0 and a fake pasteboard. Trunk lacks restore. Also time the user-visible end state, which is the keystroke posted or the quiet status set.
- [ ] Probe. Run `tests/test_paster.py` at trunk and head, interleaved, three times. The test records `time.perf_counter` around `paste`.
- [ ] Baseline. Record the trunk median return time first.
- [ ] Rule. Do not ratio the restore against trunk, because trunk does not restore. Head `paste` with `delay_ms` 0 returns in under 100 ms. The restore timer is excluded from that return. The quiet-status path sets the status string in the same call that skips Cmd+V.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 3 screenshots into `docs/plans/media/yap-paste-review-refocus.png` and `docs/plans/media/yap-paste-review-target-gone.png`.
- [ ] Record a 30 to 60 second video on the operator Mac of a dictation paste, then a dictation whose target app was quit during transcription. Save it as `docs/plans/media/yap-paste-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends this PR to the base-branch stack. The operator lands the stack bottom-up.

## Cue when the mic delivers frames (yap-cue)

**Depends on.** yap-paste.

**Files.**

- [ ] Edit `app/recorder.py`.
- [ ] Edit `app/main.py`.
- [ ] Edit `tests/test_recorder.py`.
- [ ] Edit `tests/test_pipeline.py`.

**Build.**

- [ ] In `Recorder._callback`, set a `threading.Event` after the frame is appended. Clear that event in `Recorder.start`.
- [ ] Stop calling `SoundFeedback.play_start` directly from `YapApp._on_state_change` and `YapApp._on_thai_state_change` when the state becomes recording.
- [ ] Play the start chime from a daemon thread that waits on the frame event. If the event is already set when recording begins, play immediately. If recording ends with no frame, do not play the start chime.
- [ ] Do not block `Pipeline.start_recording` or the hotkey thread on that wait. `Recorder.start` still returns when `InputStream.start` finishes.
- [ ] In `Recorder.stop`, when `abort` is false and the default input transport is Bluetooth, keep the stream open for 0.22 seconds so `_callback` can append the tail, then close. Name the constant `_BLUETOOTH_STOP_LINGER_S`.
- [ ] Read the transport with CoreAudio `kAudioDevicePropertyTransportType` through the same style of framework load `app/paster.py` uses for ApplicationServices. `sounddevice.query_devices` does not expose transport type. If the query fails, do not linger.
- [ ] Do not linger when `abort` is true. Silence auto-stop in `YapApp` calls `stop_recording_and_process` with `abort_recording_stop=True`. Leave that path immediate.
- [ ] Keep the overlay show on `PipelineState.RECORDING` where it is today, so the capsule can appear before the chime.

**You see.**

- [ ] A recording whose first `_callback` is delayed logs `start chime after first frame` and does not log `play_start` before that line.
- [ ] A Bluetooth non-abort stop logs `bluetooth stop linger` with `0.22`. An abort stop does not log that line.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_recorder.py` gains `test_stop_lingers_only_for_bluetooth_non_abort` and `test_frame_event_is_set_on_first_callback`. `tests/test_pipeline.py` gains `test_start_recording_returns_without_waiting_for_a_frame`. Run `.venv/bin/python -m pytest -q tests/test_recorder.py tests/test_pipeline.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `tests/test_recorder.py` at trunk and head. Trunk plays no frame gate and does not linger. Record that. Gate the frame event plus a stop that still returns WAV bytes. Save `/tmp/swarm-yap-cue/worker-1/regression.png`. Pass when head sets the frame event and trunk still passes `test_start_and_stop_are_serialized`.
- [ ] Lane 2. First callback delayed until after `start` returns. Save `/tmp/swarm-yap-cue/worker-2/delayed-frame.png`. Pass when `start_recording` has returned before `play_start`.
- [ ] Lane 3. Frame already queued when the recording state is set. Save `/tmp/swarm-yap-cue/worker-3/frame-already.png`. Pass when `play_start` runs without a wait.
- [ ] Lane 4. Stop with no frames. Save `/tmp/swarm-yap-cue/worker-4/no-frame.png`. Pass when `play_start` is not called and `stop` returns empty bytes.
- [ ] Lane 5. Bluetooth non-abort stop. Save `/tmp/swarm-yap-cue/worker-5/bluetooth-linger.png`. Pass when the stream stays open for 0.22 seconds and the extra callback frame is inside the WAV.
- [ ] Lane 6. Built-in transport non-abort stop. Save `/tmp/swarm-yap-cue/worker-6/builtin-stop.png`. Pass when the extra wait is 0.
- [ ] Lane 7. Abort stop on a Bluetooth transport. Save `/tmp/swarm-yap-cue/worker-7/abort-stop.png`. Pass when the extra wait is 0.
- [ ] Lane 8. Transport query raises. Save `/tmp/swarm-yap-cue/worker-8/query-failed.png`. Pass when stop does not linger and does not raise.
- [ ] Lane 9. Thai practice recording state. Save `/tmp/swarm-yap-cue/worker-9/thai-chime.png`. Pass when Thai also waits for the frame event, and `ThaiPracticeCapture` still stores the WAV.
- [ ] Lane 10. Silence auto-stop. Save `/tmp/swarm-yap-cue/worker-10/silence.png`. Pass when `test_silence_auto_stop_uses_abortive_recorder_stop` still passes and the linger is skipped.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time from `Pipeline.start_recording` entry until it returns, at trunk and head. Also the delay from the first appended frame until `play_start`, which trunk does not measure because trunk plays at the recording state. The user-visible end state is the start chime after the first frame, and a stop WAV that includes the Bluetooth tail.
- [ ] Probe. Run the new pipeline return-time test at trunk and head, interleaved, three times, with a fake stream whose first frame is 1 second late.
- [ ] Baseline. Record the trunk `start_recording` return median first.
- [ ] Rule. Head return time stays within 50 ms of the trunk median even when the first frame is 1 second late. The chime delay after the first frame is under 300 ms in the fake. Bluetooth linger is 0.22 seconds, plus or minus 0.05 seconds. A built-in stop adds 0 seconds.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 5 screenshots into `docs/plans/media/yap-cue-review-delayed-frame.png` and `docs/plans/media/yap-cue-review-bluetooth.png`.
- [ ] Record a 30 to 60 second video on the operator Mac with a Bluetooth mic. The start chime comes after speech is possible, and the last word survives release. Save it as `docs/plans/media/yap-cue-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends this PR to the base-branch stack. The operator lands the stack bottom-up.

## Prime from the caret text (yap-context)

**Depends on.** yap-cue.

**Files.**

- [ ] Create `app/press_context.py`.
- [ ] Edit `app/transcriber.py`.
- [ ] Edit `app/pipeline.py`.
- [ ] Edit `app/main.py`.
- [ ] Edit `tests/test_transcriber.py`.
- [ ] Edit `tests/test_pipeline.py`.
- [ ] Edit `tests/test_history.py`.

**Build.**

- [ ] Add a press-time record with the target app from yap-paste, the text before the caret, a secure-field flag, and an in-memory list of recent non-secure dictations, oldest first.
- [ ] Read the focused element through ApplicationServices with the same ctypes load as `_load_ax_is_process_trusted`. Read the string before the selection start. Do not read the selected text, the window title, the field label, or the app name for any provider payload.
- [ ] If the focused element subrole is `AXSecureTextField`, set the secure flag, skip `paste`, skip `YapApp._on_dictation_complete`, and do not append that transcript to the in-memory list or to `history.json`. Set a quiet status `Status: Secure field skipped.` Do not call `play_error`.
- [ ] If the caret read fails, paste with no added space and no prior text. Do not fail the dictation.
- [ ] If the caret text is non-empty, does not end in whitespace, and there is no selection, prefix one space on the transcript after cleanup returns and immediately before `paste`. Groq, Cerebras, and Mistral cleanup run `_unwrap_transcript_output`, which calls `strip`. A space applied before cleanup is removed. `NoopCleanup` does not strip. Apply the space in `Pipeline._process_audio` for every provider so the paste path is one place. If a selection exists, add no space, because Cmd+V replaces the selection.
- [ ] Join the in-memory dictations, oldest first, with the caret text. If the caret text already ends with that joined history, drop the duplicate. Send the result only inside Groq's existing `prompt` field, after the vocabulary terms, inside the 700 character cap in `_vocabulary_prompt`.
- [ ] Leave Mistral `context_bias` and Gemini `custom_vocabulary` as vocabulary only. `context_bias` terms must match a no-space pattern in `Transcriber._normalize_vocab`. Gemini terms are capped by `_GEMINI_VOCAB_LIMIT` at 100.
- [ ] Do not read `history.json` for the prompt. `load_history` stays the Recent menu, limit 15, most recent first.

**You see.**

- [ ] A Groq request whose caret text is `Hello` logs a `prompt` field that still contains the vocabulary line and also contains `Hello`, and the pasted text gains one leading space when the caret text does not end in whitespace.
- [ ] A secure field logs `secure field skipped` and does not call `paste` or `save_history`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_transcriber.py` gains `test_groq_prompt_appends_prior_text_inside_700_chars` and `test_mistral_and_gemini_payloads_stay_vocabulary_only`. `tests/test_pipeline.py` gains `test_secure_field_does_not_paste_or_record_history` and `test_leading_space_is_applied_after_cleanup_strip`. Run `.venv/bin/python -m pytest -q tests/test_transcriber.py tests/test_pipeline.py tests/test_history.py`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `tests/test_transcriber.py` at trunk and head. Trunk sends only `_vocabulary_prompt`. Record that. Gate the added prior text plus a vocabulary term that trunk already sent. Save `/tmp/swarm-yap-context/worker-1/regression.png`. Pass when head still sends `Cerebras` in the Groq prompt, matching `test_groq_transcriber_sends_language_prompt_and_quality_settings`.
- [ ] Lane 2. Caret text `Hello` with no selection and no trailing space, through a cleanup provider that strips. Save `/tmp/swarm-yap-context/worker-2/leading-space.png`. Pass when the string passed to `paste` starts with a space.
- [ ] Lane 3. Caret text that already ends with a space. Save `/tmp/swarm-yap-context/worker-3/no-extra-space.png`. Pass when the pasted string does not start with a second space.
- [ ] Lane 4. A non-empty selection. Save `/tmp/swarm-yap-context/worker-4/selection.png`. Pass when no leading space is added and the selected text is absent from the Groq prompt.
- [ ] Lane 5. Secure field. Save `/tmp/swarm-yap-context/worker-5/secure.png`. Pass when `paste` and `save_history` are not called.
- [ ] Lane 6. AX read raises. Save `/tmp/swarm-yap-context/worker-6/ax-failed.png`. Pass when `paste` still runs and the prompt has no prior text.
- [ ] Lane 7. Two prior dictations, oldest first, and a caret that already ends with them. Save `/tmp/swarm-yap-context/worker-7/dedupe.png`. Pass when the prompt contains the caret text once.
- [ ] Lane 8. Prior text longer than the remaining room under 700 characters. Save `/tmp/swarm-yap-context/worker-8/cap.png`. Pass when the prompt length is at most 700 and the vocabulary prefix is intact.
- [ ] Lane 9. Mistral `context_bias` and Gemini `custom_vocabulary` with the same prior text. Save `/tmp/swarm-yap-context/worker-9/other-providers.png`. Pass when those fields equal the vocabulary list only.
- [ ] Lane 10. `history.json` roundtrip after a normal dictation and after a secure skip. Save `/tmp/swarm-yap-context/worker-10/history-menu.png`. Pass when the normal text is stored and the secure text is absent.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Time spent building the press-time record and the Groq prompt, at trunk and head. Trunk has no press-time record. The diff-added work is the AX read plus the prompt join. The user-visible end state is the pasted string, including the leading-space choice.
- [ ] Probe. Run the new pipeline tests at head and `test_groq_transcriber_sends_language_prompt_and_quality_settings` at trunk and head, interleaved, three times.
- [ ] Baseline. Record the trunk Groq prompt-test median first.
- [ ] Rule. The head Groq prompt test stays within 50 ms of the trunk median. The press-time record test finishes in under 50 ms with a fake AX element. A real AX timeout must not block `start_recording` past 100 ms. On timeout, dictation continues without prior text.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 5 screenshots into `docs/plans/media/yap-context-review-space.png` and `docs/plans/media/yap-context-review-secure.png`.
- [ ] Record a 30 to 60 second video on the operator Mac of a mid-sentence dictation that gains one leading space, then a secure field that is skipped. Save it as `docs/plans/media/yap-context-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends this PR to the base-branch stack. The operator lands the stack bottom-up.

## Stream Gemini audio while the key is held (yap-warmup)

**Depends on.** yap-context.

**Files.**

- [ ] Create `app/gemini_live.py`.
- [ ] Edit `app/transcriber.py`.
- [ ] Edit `app/pipeline.py`.
- [ ] Edit `app/recorder.py`.
- [ ] Create `scripts/e2e_gemini_live.py`. Pytest does not collect it.

**Build.**

- [ ] At `Pipeline.start_recording`, if the transcriber has `open_live_session`, open a Gemini Live session. `start_recording` returns without waiting for the transcript. Groq and Mistral have no live session.
- [ ] Use model `gemini-3.5-transcribe-live` on `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent`. Send the setup message first. Send no audio byte until setup completes. Set `responseModalities` to `TEXT`. Put `gemini_language_codes` and the transcriber mode (`smart` or `verbatim`) on `inputAudioTranscription`. Include `custom_vocabulary` when the user has terms, capped at 100.
- [ ] Disable automatic activity detection. Send activity start when the session opens. `Recorder._callback` sends each 16 kHz mono 16-bit PCM frame into the session and still keeps the frame for the WAV. Send activity end when the user releases.
- [ ] At `stop_recording_and_process`, close the audio and block only for the finalized `inputTranscription`. Do not post `GeminiTranscriber.transcribe` when that text is non-empty. Do not paste interim text. In smart mode the finalized text is already cleaned.
- [ ] Keep the PCM until the live response succeeds. If setup fails before useful audio, or the live text is empty, or the socket drops, fall back to `GeminiTranscriber.transcribe` with the WAV. Do not resume a dropped socket.
- [ ] Leave `skips_llm_cleanup` true only for provider `gemini` and mode `smart`, so that path still uses `NoopCleanup` and does not call a second LLM.
- [ ] Leave Groq and Mistral on the finished-WAV `transcribe` path. Do not add AssemblyAI. Do not add Mistral Realtime.
- [ ] This execution adds no new unit tests. It does not expand `tests/test_transcriber.py` or `tests/test_pipeline.py`. Check each significant change with `scripts/e2e_gemini_live.py` against the real Gemini Live API.

**You see.**

- [ ] During `PipelineState.RECORDING`, Gemini PCM is on the live socket. On release, the pasted text is the finalized `inputTranscription`, and the unary interactions URL is not called when that text is non-empty.
- [ ] A Gemini smart run records cleanup provider `noop` and does not call `GroqCleanup`, `CerebrasCleanup`, or `MistralCleanup`.
- [ ] A Groq or Mistral run never opens a live socket. `transcribe` still runs on the WAV from `Recorder.stop`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] This execution adds no new unit tests. The check for the two significant changes is `scripts/e2e_gemini_live.py`, run with the repo `.venv` and the real API. The first run proves the live session returns one final transcript. The second run proves the pipeline returns that transcript on stop and does not make a second unary call when the live text is non-empty.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `grok-4.6-fast-xhigh` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Trunk posts Gemini audio only inside `transcribe` after stop. Record that. Gate a live upload during the hold plus a WAV fallback when the live text is empty. Save `/tmp/swarm-yap-warmup/worker-1/regression.png`. Pass when head uses the finalized live text and trunk still passes `test_pipeline_emits_privacy_preserving_stage_measurement`.
- [ ] Lane 2. Groq client. Save `/tmp/swarm-yap-warmup/worker-2/groq.png`. Pass when no live socket opens and the audio body is still a WAV file field after stop.
- [ ] Lane 3. Mistral client. Save `/tmp/swarm-yap-warmup/worker-3/mistral.png`. Pass when no live socket opens and `context_bias` is unchanged.
- [ ] Lane 4. Gemini live session. Save `/tmp/swarm-yap-warmup/worker-4/gemini-live.png`. Pass when setup completes before the first audio byte and the finalized transcript is the paste text.
- [ ] Lane 5. Gemini smart cleanup skip. Save `/tmp/swarm-yap-warmup/worker-5/gemini-smart.png`. Pass when `skips_llm_cleanup` is true and the cleanup provider is `noop`.
- [ ] Lane 6. Groq language fallback. Save `/tmp/swarm-yap-warmup/worker-6/fallback.png`. Pass when the second language post happens after the first result, and `test_groq_transcriber_retries_disallowed_language` passes.
- [ ] Lane 7. CJK penalty still applied. Save `/tmp/swarm-yap-warmup/worker-7/cjk.png`. Pass when `test_groq_language_guard_rejects_cjk_even_when_language_is_missing` passes.
- [ ] Lane 8. Live socket drops. Save `/tmp/swarm-yap-warmup/worker-8/live-failed.png`. Pass when the unary WAV path still pastes and the socket is not resumed.
- [ ] Lane 9. `start_recording` while live setup is in flight. Save `/tmp/swarm-yap-warmup/worker-9/start-returns.png`. Pass when `start_recording` returns without the transcript.
- [ ] Lane 10. Metrics file after a run. Save `/tmp/swarm-yap-warmup/worker-10/metrics.png`. Pass when `pipeline_metrics.jsonl` has `transcription_s` and `total_s` and has no transcript text.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `finish()` after the last PCM chunk, from `scripts/e2e_gemini_live.py`, on a short spoken fixture. Also `start_recording` return time. Trunk has no live upload. The diff-added work is the PCM upload during the hold. The user-visible end state is release-to-paste. On Gemini smart that wait is the live finalization, with no second LLM.
- [ ] Probe. Run `scripts/e2e_gemini_live.py` for the session, then again for the pipeline. Repeat the pair three times and record the median `finish()` wait.
- [ ] Baseline. Trunk cannot stream, so record the head `finish()` wait as the new clock. Record trunk `transcribe` latency only as the old full-upload wait.
- [ ] Rule. `start_recording` returns without the transcript. A non-empty live transcript makes zero unary posts. Gemini smart `cleanup_provider` is `noop`. The script prints the `finish()` wait after the last chunk.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2 and lane 5 screenshots into `docs/plans/media/yap-warmup-review-groq.png` and `docs/plans/media/yap-warmup-review-gemini.png`.
- [ ] Record a 30 to 60 second video on the operator Mac of one Groq dictation and one Gemini smart dictation, showing the release-to-paste wait. Save it as `docs/plans/media/yap-warmup-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends this PR to the base-branch stack. The operator lands the stack bottom-up.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the stack root, the stack tip, a one-line verdict per PR, and anything parked, with the reason.

## Appendix A. Prototype evidence

No prototype branch exists. The operator already chose the behavior, and this task forbids implementation. The provider question is a fact in the current code, recorded in Appendix B.

Late read-only passes confirmed the same call sites this plan already used, and one correction. Cleanup strips through `_unwrap_transcript_output`, so the leading-space step in yap-context lands after cleanup. See [Map context and cleanup](d7b1c307-55a8-4579-a45f-422fb86d8a99), [Map paste and audio cues](8ddd5119-700d-41ce-b25e-34eea5a8afe5), [Map dictation pipeline](4d270fb2-add8-4087-b1af-1acb604d439a), and [Map tests and app driver](31a15ab9-4f40-459c-8d22-1e42ee7caa89).

These items stay unproven until the PR lanes and the operator videos.

- Whether `AXStringForRange` returns the text before the caret in the apps the operator actually uses.
- Whether a Bluetooth headset on this Mac delays the first `Recorder._callback` by 1 to 2 seconds, and whether 0.22 seconds of extra open time keeps the last word.
- Whether Gemini Live upload during the hold leaves a short `finish()` wait after the last PCM chunk. Groq and Mistral still upload the WAV after release.
- A cloud VM lane cannot grant Accessibility, focus a real editor, or attach a Bluetooth mic. Those three checks are the operator videos named in the review gates.

## Appendix B. Alternatives rejected

Groq and Mistral still take one finished WAV. `Pipeline.stop_recording_and_process` calls `Recorder.stop`, which writes the WAV after the stream closes. `GroqTranscriber.transcribe` and `Transcriber.transcribe` post that WAV as a multipart file. Those two URLs cannot stream PCM during the hold. A no-audio TLS warm-up on their `httpx.Client` is not this design.

Gemini can stream. `GeminiTranscriber.open_live_session` opens `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent` with model `gemini-3.5-transcribe-live`, which is not the unary model `gemini-3.5-transcribe`. The setup message goes out first. The session sends no audio byte until setup completes. `responseModalities` is `TEXT`. `inputAudioTranscription` carries `gemini_language_codes` and mode `smart` or `verbatim`. `custom_vocabulary` is included when the user has terms, capped at 100. Automatic activity detection is off. The session sends activity start when it opens, raw 16 kHz mono 16-bit PCM as `Recorder._callback` receives frames, and activity end when the user releases. The pasted text is the finalized `inputTranscription`. Interim text is not pasted. In smart mode that finalized text is already cleaned, and `skips_llm_cleanup` still skips the second LLM. The PCM stays in memory until the live response succeeds. A failed live call, including a dropped socket, falls back to `GeminiTranscriber.transcribe` with the WAV. A dropped socket is not resumed. `GeminiTranscriber.transcribe` remains the unary interactions post for that fallback.

AssemblyAI stays out. Mistral Realtime stays out of this change.

Cleanup cannot start before the transcript exists, except on Gemini smart. `skips_llm_cleanup` returns true only for provider `gemini` and mode `smart`. `create_cleanup` then gets `enabled=False` and returns `NoopCleanup`. Groq, Cerebras, and Mistral cleanup run after `result.text` is known. Overlapping those cleanup calls with the audio upload is rejected.

Prior prose does not fit every provider. Groq already puts vocabulary in a `prompt` field capped at 700 characters by `_vocabulary_prompt`, under a 224-token comment. Mistral `context_bias` is split into tokens with no spaces. Gemini `custom_vocabulary` is a list capped at `_GEMINI_VOCAB_LIMIT` of 100. Sending caret sentences on Mistral or Gemini would invent a field. The caret text still decides the leading space for every provider, because that decision is local. The space is applied after cleanup, because `_unwrap_transcript_output` strips the model reply.

Applying the space before cleanup is rejected. The strip would delete it on Groq, Cerebras, and Mistral.

`history.json` is the Recent menu. `load_history` returns at most 15 strings, most recent first, and `YapApp._on_dictation_complete` writes it. Using that file as model context is rejected. The in-memory list in `app/press_context.py` is a separate store.

A second cleanup corpus is rejected. `benchmarks/model_benchmark.py` already builds 50 English and German cases, and `tests/test_model_benchmark.py` scores punctuation, behavior flags, and word preservation. yap-eval freezes `CLEANUP_PROMPT` against that corpus. It does not rewrite the prompt.

Writing this plan in the prose style of `docs/plans/2026-03-08-updater-design.md` is rejected. The file lives in `docs/plans/` because that is the repo directory. The headings follow the multi-PR checklist because that is the required skeleton.

These stay out of the program.

- An AssemblyAI provider.
- Mistral Realtime in this change.
- An English-only cleanup corpus.
- A cleanup rule that forbids punctuation edits.
- Sending the app name, the window title, the field label, the selection, or screen contents.
- Removing the English and German language gate, the German-then-English fallback, or the CJK score penalty in `_score_allowed_transcript`.
- Changing Thai capture behavior, silence auto-stop, or the `PipelineMeasurement` field list. Thai shares the start chime, so it waits for the first frame too. That is the same `play_start`, not a Thai feature change.
- A prompt rewrite of `CLEANUP_PROMPT` in the same change as the baseline.

## Appendix C. Risks

yap-eval can go green while a future prompt edit is still untested against live models. The owner watches that `--check-baseline` does not call the network. A later prompt change is outside this program and must run `python -m benchmarks.model_benchmark` before it updates `evals/cleanup/baseline.json`.

yap-paste can restore the clipboard before the target app reads it, so the user pastes the old clipboard. The owner watches the generation counter and the restore delay. The missing-target path must leave the transcript in place.

yap-cue can block the hotkey thread if `play_start` waits inside `_on_state_change`. The owner watches `test_start_recording_returns_without_waiting_for_a_frame`. A wrong Bluetooth detection would clip the built-in mic or cut a headset. Failed transport queries must take the no-linger path.

yap-context can send caret text to Groq. The owner watches that the prompt contains no window title, field label, selection, or secure-field contents, and that `pipeline_metrics.jsonl` still has no transcript text. An AX hang would delay key down. The 100 ms cap is the guard.

yap-warmup streams PCM only for Gemini. The owner watches that Groq and Mistral still post the WAV after `Recorder.stop`, and that a non-empty Gemini live transcript does not also post the unary request. A dropped live socket falls back to that unary WAV path and is not resumed. The live upload does not remove the cleanup wait on Groq, Cerebras, or Mistral. Gemini smart still uses `NoopCleanup`. `docs/2026-08-09-yap-pipeline-improvements.md` says `pipeline_metrics.jsonl` is the clock for release-to-paste. Use that file in the perf probe. The execution check is `scripts/e2e_gemini_live.py`, which prints the `finish()` wait after the last chunk. This execution adds no new unit tests.

`git show origin/main:pstack/skills/...` fails in this repo. The yap remote has no `pstack/` tree. When that command fails, read the same files from the local pstack plugin cache. Do not vendor those skills into yap.

There is no control skill for this menubar app. Live lanes run pytest and save a screenshot of that run. They do not click the menu bar. The operator videos cover the real mic, the real caret, and the real paste.

## Appendix D. Links and reading list

Read these before editing.

- `app/pipeline.py` `start_recording`, `stop_recording_and_process`, `_process_audio`.
- `app/transcriber.py` `GroqTranscriber`, `Transcriber`, `GeminiTranscriber`, `_vocabulary_prompt`, `skips_llm_cleanup`.
- `app/cleanup.py` `CLEANUP_PROMPT`, `NoopCleanup`.
- `app/paster.py` `paste`.
- `app/recorder.py` `start`, `stop`, `_callback`.
- `app/sounds.py` `SoundFeedback.play_start`.
- `app/main.py` `_on_state_change`, `_on_thai_state_change`, `_on_pipeline_error`, `_on_dictation_complete`, `_on_recent_click`.
- `app/history.py` `load_history`.
- `app/metrics.py` `PipelineMeasurement`.
- `benchmarks/model_benchmark.py` `build_cleanup_samples`.
- `docs/2026-08-09-yap-pipeline-improvements.md`.
- `docs/2026-08-09-yap-pipeline-benchmark.md`.
- `docs/2026-06-24-dictation-market-scan.md`.

yap-context and yap-warmup read `pstack/skills/how/SKILL.md` and `pstack/skills/interrogate/SKILL.md` before editing. yap-eval, yap-paste, and yap-cue are specified in this plan and skip those two skills.

Each owner writes an uncommitted `decisions.tsv` per `pstack/skills/show-me-your-work/SKILL.md` and returns it with the merge-ready report.
