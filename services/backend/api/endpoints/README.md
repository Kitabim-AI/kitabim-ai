# Backend API Endpoints

## Overview
FastAPI `APIRouter` modules implementing the HTTP route handlers for Kitabim.AI across authentication, book management, OCR/pipeline reprocessing, RAG chat, Uyghur spell-checking, dictionaries, knowledge graph administration, social sharing previews, and system telemetry.

## Interface
- `[__init__.py:__all__]`: Exports `ai_router`, `auth_router`, `books_router`, `chat_router`, `users_router`, `system_configs_router`, `stats_router`, `contact_router`, `spell_check_router`, `auto_correct_rules_router`, `dictionary_router`, `words_router`, `synonyms_router`, `history_dictionary_router`, `names_dictionary_router`, `english_uyghur_router`, `share_router`, `cache_router`, `questions_router`, `proverbs_router`, and `quran_router`.
- **AI Proxy (`ai_router.py`)**:
  - `[ai_router.py:router]`, `[ai_router.py:OcrRequest]`, `[ai_router.py:OcrResponse]`
  - `POST /ocr` (`[ai_router.py:ocr_image]`)
- **Authentication (`auth_router.py`)**:
  - `[auth_router.py:router]`, `[auth_router.py:limiter]`, `[auth_router.py:OAUTH_STATE_COOKIE]`, `[auth_router.py:REFRESH_TOKEN_COOKIE]`
  - `GET /me` (`[auth_router.py:get_current_user_profile]`)
  - `GET /{provider}/login` (`[auth_router.py:oauth_login]`)
  - `GET /{provider}/callback` (`[auth_router.py:oauth_callback]`)
  - `POST /refresh` (`[auth_router.py:refresh_access_token]`)
  - `POST /logout` (`[auth_router.py:logout]`)
  - `GET /health` (`[auth_router.py:auth_health]`)
- **Auto-Correct Rules (`auto_correct_rules_router.py`)**:
  - `[auto_correct_rules_router.py:router]`, `[auto_correct_rules_router.py:AutoCorrectRuleOut]`, `[auto_correct_rules_router.py:AutoCorrectRulePaginatedOut]`, `[auto_correct_rules_router.py:AutoCorrectStatsOut]`, `[auto_correct_rules_router.py:ApplyRulesResponse]`, `[auto_correct_rules_router.py:CreateAutoCorrectRuleRequest]`, `[auto_correct_rules_router.py:UpdateAutoCorrectRuleRequest]`
  - `GET /auto-correct-rules` (`[auto_correct_rules_router.py:list_auto_correct_rules]`)
  - `GET /auto-correct-rules/stats` (`[auto_correct_rules_router.py:get_auto_correct_stats_endpoint]`)
  - `GET /auto-correct-rules/{word}` (`[auto_correct_rules_router.py:get_auto_correct_rule]`)
  - `POST /auto-correct-rules` (`[auto_correct_rules_router.py:create_auto_correct_rule]`)
  - `PATCH /auto-correct-rules/{word}` (`[auto_correct_rules_router.py:update_auto_correct_rule]`)
  - `DELETE /auto-correct-rules/{word}` (`[auto_correct_rules_router.py:delete_auto_correct_rule]`)
- **Bookmarks & Reading Progress (`bookmarks_router.py`)**:
  - `[bookmarks_router.py:router]`, `[bookmarks_router.py:UpsertProgressRequest]`, `[bookmarks_router.py:CreateBookmarkRequest]`, `[bookmarks_router.py:RenameBookmarkRequest]`
  - `PUT /progress/{book_id}` (`[bookmarks_router.py:upsert_progress_endpoint]`)
  - `GET /progress/{book_id}` (`[bookmarks_router.py:get_progress_for_book_endpoint]`)
  - `GET /progress` (`[bookmarks_router.py:list_progress_endpoint]`)
  - `POST /{book_id}` (`[bookmarks_router.py:create_bookmark_endpoint]`)
  - `GET ''` and `GET /` (`[bookmarks_router.py:list_bookmarks_endpoint]`)
  - `PATCH /{bookmark_id}` (`[bookmarks_router.py:rename_bookmark_endpoint]`)
  - `DELETE /{bookmark_id}` (`[bookmarks_router.py:delete_bookmark_endpoint]`)
- **Books, Pages, Pipeline & Graph (`books_router.py`)**:
  - `[books_router.py:router]`, `[books_router.py:PUBLIC_BOOK_CACHE_SCOPE]`, `[books_router.py:STAFF_BOOK_CACHE_SCOPE]`, `[books_router.py:camel_to_snake]`, `[books_router.py:convert_dict_keys_to_snake]`, `[books_router.py:can_access_book]`, `[books_router.py:ensure_book_access]`, `[books_router.py:get_book_cache_scope]`, `[books_router.py:get_book_cache_key]`, `[books_router.py:read_limited_upload_bytes]`, `[books_router.py:load_safe_cover_image]`, `[books_router.py:process_cover_upload]`
  - `[books_router.py:MergeEntitiesRequest]`, `[books_router.py:DeleteRelationshipRequest]`, `[books_router.py:RenameEntityRequest]`, `[books_router.py:ReprocessGraphRequest]`
  - `GET /` (`[books_router.py:get_books]`), `POST /` (`[books_router.py:create_book]`), `GET /backfill-candidates` (`[books_router.py:get_backfill_candidates]`)
  - `GET /content-search` (`[books_router.py:search_book_content]`), `GET /random-proverb` (`[books_router.py:get_random_proverb]`), `GET /top-categories` (`[books_router.py:get_top_categories]`), `GET /suggest` (`[books_router.py:suggest_books]`), `GET /stats` (`[books_router.py:get_book_stats]`)
  - `GET /graph` (`[books_router.py:get_global_graph]`), `GET /graph/chunk` (`[books_router.py:get_graph_chunk_detail]`), `POST /graph/merge` (`[books_router.py:merge_graph_entities]`), `POST /graph/relationship/delete` (`[books_router.py:delete_graph_relationship]`), `POST /graph/entity/rename` (`[books_router.py:rename_graph_entity]`)
  - `GET /{book_id}` (`[books_router.py:get_book]`), `PUT /{book_id}` (`[books_router.py:update_book_details]`), `DELETE /{book_id}` (`[books_router.py:delete_book]`), `POST /{book_id}/replace-ocr` (`[books_router.py:replace_book_ocr]`)
  - `GET /{book_id}/pipeline-stats` (`[books_router.py:get_book_pipeline_stats]`), `GET /{book_id}/content` (`[books_router.py:get_book_content]`), `GET /{book_id}/summary` (`[books_router.py:get_book_summary]`)
  - `GET /{book_id}/pages` (`[books_router.py:get_book_pages]`), `GET /{book_id}/pages/{page_num}` (`[books_router.py:get_book_page]`), `POST /{book_id}/pages/{page_num}/reset` (`[books_router.py:reset_page]`), `POST /{book_id}/pages/{page_num}/update` (`[books_router.py:update_page_text]`), `POST /{book_id}/pages/{page_num}/toc` (`[books_router.py:set_page_toc]`), `POST /{book_id}/pages/{page_num}/set-start-page` (`[books_router.py:set_start_page]`)
  - `GET /hash/{content_hash}` (`[books_router.py:get_book_by_hash]`), `POST /upload` (`[books_router.py:upload_pdf]`), `POST /upload-ocrd` (`[books_router.py:upload_pdf_ocrd]`), `POST /{book_id}/cover` (`[books_router.py:update_book_cover]`), `POST /{book_id}/download-ticket` (`[books_router.py:get_download_ticket]`), `GET /{book_id}/download` (`[books_router.py:download_book]`)
  - `POST /{book_id}/reprocess/ocr` (`[books_router.py:reprocess_ocr]`), `POST /{book_id}/reprocess/structure` (`[books_router.py:reprocess_structure]`), `POST /{book_id}/reprocess/chunking` (`[books_router.py:reprocess_chunking]`), `POST /{book_id}/reprocess/embedding` (`[books_router.py:reprocess_embedding]`), `POST /{book_id}/reprocess/spell-check` (`[books_router.py:reprocess_spell_check]`), `POST /{book_id}/reprocess/graph` (`[books_router.py:reprocess_graph]`), `POST /{book_id}/reprocess/summary` (`[books_router.py:reprocess_summary]`), `POST /{book_id}/retry-failed` (`[books_router.py:retry_failed_pages]`), `POST /admin/bulk-reset-incomplete-ocr` (`[books_router.py:bulk_reset_incomplete_ocr]`)
- **Cache (`cache_router.py`)**:
  - `[cache_router.py:router]`, `[cache_router.py:verify_operator_access]`, `POST /invalidate` (`[cache_router.py:invalidate_cache]`)
- **Chat & Conversations (`chat_router.py`)**:
  - `[chat_router.py:router]`, `[chat_router.py:FeedbackRequest]`, `[chat_router.py:CreateConversationRequest]`
  - `GET /usage` (`[chat_router.py:get_chat_usage]`), `POST /` (`[chat_router.py:chat_with_book_api]`), `POST /stream` (`[chat_router.py:chat_with_book_stream]`), `POST /feedback` (`[chat_router.py:submit_chat_feedback]`), `GET /recent-questions` (`[chat_router.py:get_recent_questions]`)
  - `POST /conversations` (`[chat_router.py:create_conversation_endpoint]`), `GET /conversations` (`[chat_router.py:list_conversations_endpoint]`), `GET /conversations/{conversation_id}/messages` (`[chat_router.py:list_conversation_messages_endpoint]`), `DELETE /conversations/{conversation_id}` (`[chat_router.py:delete_conversation_endpoint]`)
- **Contact (`contact_router.py`)**:
  - `[contact_router.py:router]`, `POST /submit` (`[contact_router.py:submit_contact_form]`), `GET /admin/submissions` (`[contact_router.py:get_contact_submissions]`)
- **Dictionaries & Reference Corpora (`dictionary_router.py`, `english_uyghur_router.py`, `history_dictionary_router.py`, `names_dictionary_router.py`, `proverbs_router.py`, `quran_router.py`, `synonyms_router.py`, `words_router.py`)**:
  - `[dictionary_router.py:router]`, `[dictionary_router.py:DictionaryStatsOut]`, `[dictionary_router.py:DictionaryEntryOut]`, `[dictionary_router.py:SpellingSuggestionOut]`, `[dictionary_router.py:SpellingCheckOut]`, `GET /dictionary/check-spelling` (`[dictionary_router.py:check_spelling]`), `GET /dictionary/search` (`[dictionary_router.py:search_dictionary]`), `GET /dictionary/stats` (`[dictionary_router.py:get_dictionary_stats]`), `GET /dictionary/letter-groups` (`[dictionary_router.py:list_letter_groups]`), `GET /dictionary` (`[dictionary_router.py:list_dictionary_entries]`), `DELETE /dictionary/{entry_id}` (`[dictionary_router.py:delete_dictionary_entry]`), `GET /dictionary/words-bundle` (`[dictionary_router.py:get_words_bundle]`)
  - `[english_uyghur_router.py:router]`, `[english_uyghur_router.py:EnglishUyghurEntryOut]`, `[english_uyghur_router.py:EnglishUyghurStatsOut]`, `GET /english-uyghur-dictionary/stats` (`[english_uyghur_router.py:get_english_uyghur_stats]`), `GET /english-uyghur-dictionary/letter-groups` (`[english_uyghur_router.py:list_english_uyghur_letter_groups]`), `GET /english-uyghur-dictionary/search` (`[english_uyghur_router.py:search_english_uyghur_dictionary]`), `GET /english-uyghur-dictionary` (`[english_uyghur_router.py:list_english_uyghur_entries]`), `DELETE /english-uyghur-dictionary/{entry_id}` (`[english_uyghur_router.py:delete_english_uyghur_entry]`)
  - `[history_dictionary_router.py:router]`, `[history_dictionary_router.py:HistoryEntryOut]`, `[history_dictionary_router.py:HistoryStatsOut]`, `[history_dictionary_router.py:HistoryEntryCreate]`, `[history_dictionary_router.py:HistoryEntryUpdate]`, `GET /history-dictionary/stats` (`[history_dictionary_router.py:get_history_stats]`), `GET /history-dictionary/letter-groups` (`[history_dictionary_router.py:list_history_letter_groups]`), `GET /history-dictionary/search` (`[history_dictionary_router.py:search_history_dictionary]`), `GET /history-dictionary` (`[history_dictionary_router.py:list_history_entries]`), `POST /history-dictionary` (`[history_dictionary_router.py:create_history_entry]`), `PATCH /history-dictionary/{entry_id}` (`[history_dictionary_router.py:update_history_entry]`), `DELETE /history-dictionary/{entry_id}` (`[history_dictionary_router.py:delete_history_entry]`)
  - `[names_dictionary_router.py:router]`, `[names_dictionary_router.py:NameEntryOut]`, `[names_dictionary_router.py:NamesStatsOut]`, `GET /names-dictionary/stats` (`[names_dictionary_router.py:get_names_stats]`), `GET /names-dictionary/letter-groups` (`[names_dictionary_router.py:list_names_letter_groups]`), `GET /names-dictionary/search` (`[names_dictionary_router.py:search_names_dictionary]`), `GET /names-dictionary` (`[names_dictionary_router.py:list_names_entries]`), `DELETE /names-dictionary/{entry_id}` (`[names_dictionary_router.py:delete_name_entry]`)
  - `[proverbs_router.py:router]`, `[proverbs_router.py:ProverbsStatsOut]`, `[proverbs_router.py:ProverbEntryOut]`, `[proverbs_router.py:ProverbUpdate]`, `GET /proverbs/search` (`[proverbs_router.py:search_proverbs]`), `GET /proverbs/stats` (`[proverbs_router.py:get_proverbs_stats]`), `GET /proverbs` (`[proverbs_router.py:list_proverbs_entries]`), `PUT /proverbs/{proverb_id}` (`[proverbs_router.py:update_proverb]`), `DELETE /proverbs/{proverb_id}` (`[proverbs_router.py:delete_proverb]`)
  - `[quran_router.py:router]`, `[quran_router.py:QuranStatsOut]`, `[quran_router.py:SurahOut]`, `[quran_router.py:QuranAyahOut]`, `GET /quran/surahs` (`[quran_router.py:list_surahs]`), `GET /quran/search` (`[quran_router.py:search_quran]`), `GET /quran/stats` (`[quran_router.py:get_quran_stats]`), `GET /quran/` (`[quran_router.py:list_quran_entries]`)
  - `[synonyms_router.py:router]`, `[synonyms_router.py:SynonymEntryOut]`, `[synonyms_router.py:SynonymStatsOut]`, `GET /synonyms/search` (`[synonyms_router.py:search_synonyms]`), `GET /synonyms/lookup` (`[synonyms_router.py:lookup_synonym]`), `GET /synonyms/letter-groups` (`[synonyms_router.py:list_letter_groups]`), `GET /synonyms/stats` (`[synonyms_router.py:get_synonym_stats]`), `GET /synonyms` (`[synonyms_router.py:list_synonyms]`), `DELETE /synonyms/{entry_id}` (`[synonyms_router.py:delete_synonym_entry]`)
  - `[words_router.py:router]`, `[words_router.py:WordsStatsOut]`, `[words_router.py:WordOut]`, `GET /spell-check/words/search` (`[words_router.py:search_words]`), `GET /spell-check/words/stats` (`[words_router.py:get_words_stats]`), `GET /spell-check/words/letter-groups` (`[words_router.py:list_letter_groups]`), `GET /spell-check/words` (`[words_router.py:list_words]`), `DELETE /spell-check/words/{word_id}` (`[words_router.py:delete_word]`)
- **Graph Admin (`graph_admin_router.py`)**:
  - `[graph_admin_router.py:router]`, `[graph_admin_router.py:SplitEntityRequest]`
  - `POST /entities/{entity_id}/split` (`[graph_admin_router.py:split_entity]`), `POST /merge-log/{merge_log_id}/unmerge` (`[graph_admin_router.py:unmerge_entity]`), `GET /review-queue` (`[graph_admin_router.py:list_review_queue]`), `POST /review-queue/{review_id}/approve` (`[graph_admin_router.py:approve_review]`), `POST /review-queue/{review_id}/reject` (`[graph_admin_router.py:reject_review]`)
- **Questions (`questions_router.py`)**:
  - `[questions_router.py:router]`, `GET /admin/questions` (`[questions_router.py:get_admin_questions]`), `PATCH /admin/questions/{eval_id}/featured` (`[questions_router.py:toggle_featured_question]`), `GET /featured` (`[questions_router.py:get_featured_questions]`)
- **Share Previews (`share_router.py`)**:
  - `[share_router.py:router]`, `GET /book/{book_id}` (`[share_router.py:share_book]`), `GET /qa` (`[share_router.py:share_qa]`), `GET /page/{book_id}/{page_number}` (`[share_router.py:share_page]`)
- **Spell Check (`spell_check_router.py`)**:
  - `[spell_check_router.py:router]`, `[spell_check_router.py:SpellSuggestionOut]`, `[spell_check_router.py:SpellIssueOut]`, `[spell_check_router.py:PageSpellCheckOut]`, `[spell_check_router.py:PageSpellSummary]`, `[spell_check_router.py:BookSpellSummaryOut]`, `[spell_check_router.py:CorrectionItem]`, `[spell_check_router.py:ApplyCorrectionsRequest]`, `[spell_check_router.py:IgnoreIssuesRequest]`, `[spell_check_router.py:RandomBookOut]`
  - `GET /spell-check/random-book` (`[spell_check_router.py:get_random_book_with_issues]`), `GET /{book_id}/spell-check/summary` (`[spell_check_router.py:get_spell_check_summary]`), `GET /{book_id}/pages/{page_num}/spell-check` (`[spell_check_router.py:get_page_spell_issues]`), `POST /{book_id}/pages/{page_num}/spell-check/apply` (`[spell_check_router.py:apply_spell_corrections]`), `POST /{book_id}/spell-check/trigger` (`[spell_check_router.py:trigger_spell_check]`), `POST /{book_id}/pages/{page_num}/spell-check/trigger` (`[spell_check_router.py:trigger_page_spell_check]`), `POST /{book_id}/pages/{page_num}/spell-check/ignore` (`[spell_check_router.py:ignore_spell_issues]`)
- **Stats (`stats_router.py`)**:
  - `[stats_router.py:router]`, `[stats_router.py:BookStatusCount]`, `[stats_router.py:PageStatusCount]`, `[stats_router.py:PageStats]`, `[stats_router.py:ChunkStats]`, `[stats_router.py:SystemStats]`, `[stats_router.py:RAGQualityStats]`, `[stats_router.py:PipelineStageStats]`, `[stats_router.py:PipelinePerformanceStats]`
  - `GET /` (`[stats_router.py:get_system_stats]`), `GET /rag` (`[stats_router.py:get_rag_quality_stats]`), `GET /pipeline` (`[stats_router.py:get_pipeline_performance_stats]`)
- **System Configs & Circuit Breakers (`system_configs_router.py`)**:
  - `[system_configs_router.py:router]`, `[system_configs_router.py:SystemConfigResponse]`, `[system_configs_router.py:SystemConfigCreate]`, `[system_configs_router.py:SystemConfigUpdate]`
  - `GET /` (`[system_configs_router.py:list_configs]`), `GET /{key}` (`[system_configs_router.py:get_config]`), `POST /` (`[system_configs_router.py:create_config]`), `PUT /{key}` (`[system_configs_router.py:update_config]`), `GET /circuit-breaker/status` (`[system_configs_router.py:get_circuit_breaker_status_endpoint]`), `POST /circuit-breaker/reset` (`[system_configs_router.py:reset_circuit_breaker_endpoint]`), `POST /circuit-breaker/open` (`[system_configs_router.py:force_open_circuit_breaker_endpoint]`)
- **Users (`users_router.py`)**:
  - `[users_router.py:router]`, `[users_router.py:UserRoleUpdate]`, `[users_router.py:UserStatusUpdate]`, `[users_router.py:PaginatedUsers]`
  - `GET /` (`[users_router.py:list_all_users]`), `GET /{user_id}` (`[users_router.py:get_user]`), `PATCH /{user_id}/role` (`[users_router.py:change_user_role]`), `PATCH /{user_id}/status` (`[users_router.py:change_user_status]`)

## Invariants
- **Access Control & Book Visibility**:
  - A book is considered public only when `status == 'ready'` and `visibility in {'public', None}` (`[books_router.py:_is_public_book]`). Staff access requires role in `{'admin', 'editor'}` (`[books_router.py:_can_staff_access_book]`). `ensure_book_access` raises HTTP 403 if `can_access_book` returns `False` (`[books_router.py:ensure_book_access]`).
  - Unauthenticated guest requests to `get_book_page` are restricted to `page_num <= 20` (`[books_router.py:get_book_page]`), and `get_book_pages` restricts guests to `skip < 20` with `limit` clamped to `20 - skip` (`[books_router.py:get_book_pages]`).
  - `download_book` requires either a valid download JWT ticket (`expected_type='download'`, matching `book_id`, role in `ADMIN`/`EDITOR`) or an `ADMIN`/`EDITOR` Bearer token (`[books_router.py:download_book]`).
  - `verify_operator_access` requires either `X-Operator-Token` matching non-empty `settings.operator_token` or an authenticated `admin` user (`[cache_router.py:verify_operator_access]`).
  - Admins cannot change their own role (`[users_router.py:change_user_role]`) or disable their own account (`[users_router.py:change_user_status]`).
- **Uploads & Media Safety**:
  - `read_limited_upload_bytes` reads in 1 MB chunks and raises HTTP 413 if total bytes exceed `max_bytes` (`[books_router.py:read_limited_upload_bytes]`).
  - `load_safe_cover_image` treats PIL `DecompressionBombWarning` as an error, enforces `settings.max_cover_image_pixels`, and converts `RGBA`/`P`/`LA` modes to `RGB` (`[books_router.py:load_safe_cover_image]`).
  - `upload_pdf` and `upload_pdf_ocrd` deduplicate by SHA-256 `content_hash` and strip NUL (`\x00`) bytes from extracted page text (`[books_router.py:upload_pdf]`, `[books_router.py:upload_pdf_ocrd]`).
- **OAuth & Session Security**:
  - `_is_allowed_redirect_uri` permits `http` only on literal loopback (`127.0.0.1` or `::1`, never `localhost`) or origins in `settings.cors_origins` (`[auth_router.py:_is_allowed_redirect_uri]`).
  - `oauth_login` (10/min), `oauth_callback` (20/min), and `refresh_access_token` (30/min) are rate-limited per IP; `oauth_callback` requires a verified email unless `is_placeholder_email(normalized_email, provider=provider)` is true, blocks cross-provider email linking on `@*.placeholder` addresses (`not is_placeholder_email(normalized_email)`), releases the SQLAlchemy transaction via `session.rollback()` before running `evaluate_signup_email_domain` on new-user signups, and emits closed `AuthErrorCode` identifiers over `BroadcastChannel('kitabim_auth')`, `window.opener.postMessage`, and validated Mobile Safari `?auth_error=` redirects (`[auth_router.py:oauth_login]`, `[auth_router.py:oauth_callback]`, `[auth_router.py:_error_response]`, `[auth_router.py:refresh_access_token]`).
- **Chat, Spell-Check & Pipeline Rules**:
  - `chat_with_book_api` and `chat_with_book_stream` enforce role-based daily chat limits before running `ChatOrchestrator` and only increment usage after completion (`[chat_router.py:chat_with_book_api]`, `[chat_router.py:chat_with_book_stream]`).
  - `apply_spell_corrections` sorts replacements by start offset descending (`reverse=True`) so applying edits from end to start preserves earlier character offsets, and skips any replacement whose `issue.word` does not match `page_text[start:end]` (`[spell_check_router.py:apply_spell_corrections]`).
  - `CreateAutoCorrectRuleRequest` requires non-empty `misspelled_word` and `corrected_word` that differ from each other (`[auto_correct_rules_router.py:CreateAutoCorrectRuleRequest]`).
  - Non-scraper user agents hitting `share_router` endpoints always receive a 302 `RedirectResponse` to the frontend deep link; private or non-ready books also redirect even for scraper user agents (`[share_router.py:share_book]`, `[share_router.py:share_page]`).

## Side Effects
- **Database Mutations (PostgreSQL & Neo4j)**:
  - Creates, updates, and deletes books, pages, chunks, bookmarks, reading progress, conversations, RAG evaluations, spell-check issues, auto-correct rules, dictionary entries, staging terms, system configs, and users in PostgreSQL (`[books_router.py:upload_pdf]`, `[bookmarks_router.py:create_bookmark_endpoint]`, `[chat_router.py:chat_with_book_api]`, `[spell_check_router.py:apply_spell_corrections]`, `[users_router.py:change_user_role]`).
  - Schedules background task `_increment_read_count` on every `get_book` request to atomically increment `BookDB.read_count` (`[books_router.py:get_book]`, `[books_router.py:_increment_read_count]`).
  - Proactively runs `apply_auto_corrections_to_page` on `GET /{book_id}/pages/{page_num}/spell-check` and commits if corrections were applied (`[spell_check_router.py:get_page_spell_issues]`).
  - Queries and mutates Neo4j entities and relationships in `books_router` and `graph_admin_router` (`[books_router.py:get_global_graph]`, `[books_router.py:merge_graph_entities]`, `[graph_admin_router.py:split_entity]`, `[graph_admin_router.py:unmerge_entity]`, `[graph_admin_router.py:approve_review]`).
- **Redis Cache & ARQ Task Queue**:
  - Reads, writes, and invalidates Redis cache keys and namespaces across `books_router`, `cache_router`, `proverbs_router`, `auto_correct_rules_router`, and `users_router` (`[cache_router.py:invalidate_cache]`, `[books_router.py:get_books]`, `[proverbs_router.py:update_proverb]`).
  - Enqueues background jobs (`knowledge_graph_job`, `summary_job`) into Redis via ARQ (`[books_router.py:reprocess_graph]`, `[books_router.py:reprocess_summary]`).
- **External APIs, Storage & Cookies**:
  - Calls Google Gemini APIs for OCR (`[ai_router.py:ocr_image]`), synchronous page re-embedding (`[books_router.py:update_page_text]`), and RAG chat (`[chat_router.py:chat_with_book_api]`).
  - Writes temporary upload/cover files to `settings.uploads_dir` and uploads/deletes objects in Google Cloud Storage or local storage (`[books_router.py:process_cover_upload]`, `[books_router.py:upload_pdf]`, `[books_router.py:delete_book]`).
  - Exchanges OAuth codes over HTTP with OAuth providers, verifies new-signup email domains via `evaluate_signup_email_domain` (`api.usercheck.com` + Redis cache), and sets/deletes `kitabim_refresh_token` and `kitabim_oauth_state` cookies (`[auth_router.py:oauth_callback]`, `[auth_router.py:logout]`).

## Verification
- Run: `pytest services/backend/tests`
