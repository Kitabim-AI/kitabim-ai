# API Code Review — 2026-07-26

**Branch:** poc/voice-to-text
**Verdict:** Request changes

## Issues

### `services/backend/api/endpoints/asr_router.py`

- **[blocking]** Line 27 — `transcribe_audio` has no auth dependency at all (no `Depends(require_reader)` or equivalent), unlike every comparable endpoint (`chat_router.py` gates all its routes with `Depends(require_reader)`). Any unauthenticated caller can hit `/api/asr/transcribe` and consume ONNX inference for free, and it bypasses whatever usage limiting the chat feature has (`user_chat_usage`). Add `current_user: User = Depends(require_reader)` (import from `auth.dependencies`) per the CLAUDE.md non-negotiable rule "All new API endpoints need an auth dependency — never skip it."
- **[blocking]** Lines 44, 55, 61, 67, 74, 89, 96 — all `HTTPException(detail=...)` values are hardcoded English strings ("Could not read uploaded audio file.", "Invalid base64 audio encoding.", "Provide either an audio file or audioBase64 string.", "Audio data is empty or too short.", "Audio file size exceeds 10MB limit.", plus the two exception-derived messages). Use `t("errors.key")` from `app.core.i18n` and add the new keys to both `locales/en.json` and `locales/ug.json`.
- **[blocking]** Line 78-79 — `asr_service.transcribe(audio_bytes)` runs synchronously inside an `async def` endpoint. `transcribe()` does librosa/pydub decoding (which shells out to ffmpeg) plus an ONNX forward pass — all CPU-bound and potentially multi-second work — directly on the event loop, blocking every other concurrent request on the same worker for the duration. Wrap it: `result = await asyncio.to_thread(asr_service.transcribe, audio_bytes)`.
- **[blocking]** Lines 39 & 51 — the full request body is read into memory (`await file.read()`, `base64.b64decode(...)`) *before* the 10MB size check on line 64 runs. There is no upstream limit, so an oversized upload is fully buffered (and, for the file branch, spooled/read entirely) before it can be rejected. Check `file.size` (or a `Content-Length` pre-check) before reading, or use a streaming size guard.
- **[blocking]** Lines 28, 37-45 — no MIME type or extension validation on the uploaded file before it is handed to `AudioSegment.from_file` (ffmpeg) in `asr_service.preprocess_audio`. Per the security checklist, uploads must validate content type, not just accept anything.

### `packages/backend-core/app/services/asr_service.py`

- **[suggestion]** Lines 154-181 — `_ensure_model_downloaded` fetches a ~100MB binary from `https://github.com/gheyret/uyghurasr_python/releases/download/tunji/...` via plain `urllib.request.urlretrieve`, with no checksum/signature verification, and will silently re-download and reload whatever is currently at that URL if the local file is ever missing, corrupt, or too small. The `tunji` tag is not commit-pinned. Pin to an immutable release asset and verify a SHA256 hash before loading into `onnxruntime.InferenceSession`.
- **[suggestion]** Lines 17, 160, 174, 180, 189, 193 — logging uses `logger.info/warning/error(f"...")` instead of this project's `log_json(logger, level, "message", key=value)` convention (used correctly in `main.py`'s own ASR preload code).
- **[suggestion]** Lines 22-24 — `DEFAULT_MODEL_PATH` is computed via `__file__`-relative traversal rather than sourced from `settings.*` (`core/config.py`). Fragile if the package layout changes; consider a `settings.asr_model_path` field instead.
- **[suggestion]** No unit test exercises `UyghurASRService.transcribe` / `_get_session` (e.g. with a mocked `onnxruntime.InferenceSession`) — only the pure-function `transliterate_uly_to_uey` and `UyghurVocab` are tested in `test_asr_service.py`.

### `Dockerfile.backend`

- **[suggestion]** Lines 38-41 — same unpinned, unverified model download as above, baked into the image build. A moved/compromised release asset changes the shipped model with no detection. Pin the tag/commit and verify a checksum after download.

### `services/backend/main.py`

- **[suggestion]** No new issues beyond style — the `run_in_executor` preload pattern and `Permissions-Policy` change to `microphone=(self)` are both correct. Minor: a few stray blank lines were introduced (around lines 163, 176, 258, 499) — cosmetic only.

## Summary

The core gap is security: the new `/api/asr/transcribe` endpoint ships with no auth dependency, no upload-size guard before buffering, and no content-type validation, and it runs blocking CPU work inline on the async event loop. The i18n convention (all user-facing error strings must go through `t()`) is also not followed. The model-download supply chain (unpinned URL, no checksum) is a lower-severity but real concern on both the runtime path and the Dockerfile bake step. Fix the endpoint's auth, blocking-call, and upload-size issues before merging; the i18n and model-integrity items should also be addressed.
