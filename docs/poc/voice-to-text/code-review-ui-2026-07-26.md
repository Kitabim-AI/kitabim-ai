# UI Code Review — 2026-07-26

**Branch:** poc/voice-to-text
**Verdict:** Request changes

## Issues

### `apps/frontend/src/hooks/useAudioRecorder.ts`

- **[blocking]** No `useEffect` cleanup exists anywhere in this hook. If the owning component unmounts while `isRecording` is `true` (user navigates away, closes the chat, or the modal it's in is dismissed mid-recording), the `MediaRecorder`, its `setInterval` timer (line 67-69), and the open microphone `stream` are never stopped or released — the mic stays active indefinitely (visible mic indicator stays on) and `setRecordingTime`/`setIsRecording` keep firing on an unmounted component. Add a `useEffect` that returns a cleanup stopping the recorder, its tracks, and clearing `timerRef` on unmount, mirroring the `LibraryView.tsx` observer-cleanup pattern.
- **[suggestion]** Line 21 — `useRef<NodeJS.Timeout | null>(null)` uses the Node type in a browser-only hook; `setInterval` in the browser returns `number`. Use `ReturnType<typeof setInterval>` instead.

### `apps/frontend/src/components/common/VoiceInputButton.tsx`

- **[blocking]** Lines 19, 60, 67, 105, 114, 128 — every user-visible string is hardcoded (the default `title` prop, both error messages, the "Cancel"/"Stop & Transcribe" button titles, and the "تونۇۋاتىدۇ..." transcribing label). None go through `t()` from `useI18n()`, and no keys were added to `locales/en.json` / `locales/ug.json`. This is a new reusable component with zero i18n coverage.
- **[blocking]** No test file exists for this component (mic idle/recording/transcribing/error states are all untested).
- **[suggestion]** Line 65 — `catch (err: any)` is untyped; narrow with `err instanceof Error` per the TypeScript checklist.
- **[suggestion]** Line 160 — the error label uses `mr-1.5`, which only reads correctly because both current call sites happen to wrap this component in an explicit `dir="ltr"` container. If it's ever dropped into a plain RTL context, the margin will land on the wrong side. Prefer `gap-*`/logical spacing on the parent instead of `mr-*` inside the component.

### `apps/frontend/src/services/asrService.ts`

- **[blocking]** No test file exists for this service (verified the `authFetch` multipart path is otherwise correct — no `Content-Type` override, so the browser sets the form-data boundary properly).
- **[suggestion]** Line 11 — the upload filename is hardcoded to `voice_recording.webm` regardless of the actual recorded MIME type (`useAudioRecorder` can pick `audio/ogg`, `audio/mp4`, or `audio/wav`). Harmless since the backend sniffs the container via `pydub`/ffmpeg, but a mismatched extension is confusing if ever inspected/logged.

### `apps/frontend/src/components/chat/ChatInterface.tsx` / `apps/frontend/src/components/library/HomeView.tsx`

- No functional issues found. `onTranscribed` closures correctly append to the latest `chatInput`/`localSearch` state on each render; `authFetch` usage and layout padding adjustments for the new button are consistent with the existing send-button pattern.

## Summary

The two blocking issues that matter most: `useAudioRecorder` never releases the microphone/stops the timer on unmount, which is a real resource/privacy leak, and the entire new `VoiceInputButton` component bypasses i18n despite being full of user-facing Uyghur/English strings. Test coverage is also completely absent for all three new frontend files. `ChatInterface.tsx` and `HomeView.tsx` integration itself is clean.
