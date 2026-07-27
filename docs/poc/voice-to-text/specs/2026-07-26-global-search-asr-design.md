# Design Document: Global Search Modal ASR (Voice Input) Integration

**Date**: 2026-07-26  
**Feature**: Voice Input (ASR) in Global Search Modal Window (`SearchOverlay.tsx`)  
**Status**: Approved  

---

## 1. Overview
This feature adds ASR (voice input recognition) to the global search modal window (`SearchOverlay.tsx`). It matches the existing ASR UX on the home page search bar, allowing users to speak their search query in Uyghur to populate the global search input.

---

## 2. Requirements & UX Behavior

### 2.1 Interface & Placement
- In `SearchOverlay.tsx`, include `VoiceInputButton` inside the input group container alongside a clear button (`X`).
- When a user speaks, `onTranscribed(text)` appends or sets the transcribed text into `globalSearchQuery`.

### 2.2 Shared ASR Capabilities
- Uses `VoiceInputButton` component (`size="md"`).
- Integrates `useAudioRecorder` for browser microphone access.
- Sends audio blob to backend ASR endpoint (`transcribeAudioBlob`), displaying loading spinner while processing and pulse animation during recording.

---

## 3. Implementation Details

```tsx
<div className="flex-grow relative group min-w-0 flex items-center gap-2">
  <input
    ref={inputRef}
    type="text"
    autoFocus
    value={globalSearchQuery}
    onChange={(e) => setGlobalSearchQuery(e.target.value)}
    placeholder={t('home.searchPlaceholder')}
    className="w-full bg-transparent text-lg md:text-2xl font-normal text-[#1a1a1a] dark:text-slate-100 outline-none placeholder:text-slate-300 dark:placeholder:text-slate-600 uyghur-text truncate"
  />
  {globalSearchQuery && (
    <button
      type="button"
      onClick={() => setGlobalSearchQuery('')}
      className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors flex-shrink-0"
    >
      <X size={20} />
    </button>
  )}
  <VoiceInputButton
    onTranscribed={(text) => {
      setGlobalSearchQuery((prev) => (prev ? `${prev} ${text}` : text));
    }}
    size="md"
    className="flex-shrink-0"
  />
  <div className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 group-focus-within:bg-[#0369a1] dark:group-focus-within:bg-[#38bdf8] transition-all rounded-full" />
</div>
```

---

## 4. Verification & Testing Strategy
1. **Visual UI Check**:
   - Open global search modal (`Cmd/Ctrl+K` or search button).
   - Confirm microphone button renders inside the input field.
2. **ASR Integration Check**:
   - Click microphone icon, speak query, stop recording.
   - Confirm transcribed Uyghur text is populated into the search input and results update automatically.
3. **Deployment**:
   - Run `./deploy/local/rebuild-and-restart.sh frontend`.
