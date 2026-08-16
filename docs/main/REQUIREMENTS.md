# Kitabim.AI — Business Requirements Document

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [User Roles & Permissions](#2-user-roles--permissions)
3. [Feature Requirements](#3-feature-requirements)
   - 3.1 [User Authentication](#31-user-authentication)
   - 3.2 [User Management](#32-user-management)
   - 3.3 [Book Upload & Ingestion](#33-book-upload--ingestion)
   - 3.4 [OCR Processing](#34-ocr-processing)
   - 3.5 [Book Library & Browsing](#35-book-library--browsing)
   - 3.6 [Search & Discovery](#36-search--discovery)
   - 3.7 [Book Reader](#37-book-reader)
   - 3.8 [AI-Powered Chat Assistant](#38-ai-powered-chat-assistant)
   - 3.9 [Spell Check & Correction](#39-spell-check--correction)
   - 3.10 [Book Metadata Management](#310-book-metadata-management)
   - 3.11 [Cover Image Management](#311-cover-image-management)
   - 3.12 [Book Visibility & Access Control](#312-book-visibility--access-control)
   - 3.13 [Administration Dashboard](#313-administration-dashboard)
   - 3.14 [Auditing & Change Tracking](#314-auditing--change-tracking)
   - 3.15 [Error Handling & Recovery](#315-error-handling--recovery)
   - 3.16 [Reference Library & Language Tools](#316-reference-library--language-tools)
   - 3.17 [Knowledge Graph](#317-knowledge-graph)
   - 3.18 [AI Book Summaries](#318-ai-book-summaries)
   - 3.19 [Contact & Community Engagement](#319-contact--community-engagement)
   - 3.20 [Content Sharing](#320-content-sharing)
   - 3.21 [AI History Dictionary Extraction](#321-ai-history-dictionary-extraction)
4. [Scalability & Performance](#4-scalability--performance)

---

## 1. Product Overview

**Kitabim.AI** is an intelligent Uyghur Digital Library platform. Its purpose is to digitize Uyghur-language books, provide AI-powered reading assistance, and serve as a curated online library for Uyghur literature.

The platform supports four core workflows:

- **Digitization** — Upload PDF or DOCX books. PDFs are extracted using AI-based Optical Character Recognition (OCR); DOCX files already contain digital text and skip OCR entirely.
- **Curation** — Editors and administrators review, correct, categorize, and manage the digitized book collection.
- **Reading & AI Assistance** — Readers browse the library, read books, and ask an AI assistant questions about book content, using either a specific book's context or the entire library.
- **Language Reference** — Any visitor, signed in or not, can browse a set of Uyghur-language reference tools (dictionary, proverbs, synonyms, historical terms, names, English–Uyghur translation, Quran search) independently of the book library, and the AI assistant draws on the same reference data when answering questions.

---

## 2. User Roles & Permissions

The system supports four levels of access. Three roles (`reader`, `editor`, `admin`) are stored on the user record in the database; "Guest" is simply the absence of a signed-in session.

### 2.1 Guest (Unauthenticated)

A guest is any visitor who has not signed in. Guests have broad but read-only access.

- Can browse and view books that are both **publicly visible** and **fully processed**.
- Can browse the reference library (dictionary, proverbs, synonyms, history, names, English–Uyghur, Quran) and the public knowledge graph visualization.
- Cannot use the AI chat assistant.
- Cannot upload, edit, or manage any content.

### 2.2 Reader

A reader is a signed-in user with basic access. This is the default role assigned to new accounts.

- All guest permissions.
- Can use the **per-book AI chat assistant** to ask questions about a specific book.
- Can use the **global AI chat assistant** to ask questions across the entire library.

### 2.3 Editor

An editor is a signed-in user responsible for content management.

- All reader permissions.
- Can **upload** new PDF or DOCX books to the library.
- Can **retry failed OCR pages** and **reprocess** the Chunking, Embedding, or Spell Check pipeline steps for a book.
- Can **edit page content** directly within the reader.
- Can **run spell check** and **apply corrections**, and manage the shared library of **auto-correction rules**.
- Can **edit book metadata** (title, author, volume, categories).
- Can **upload or replace cover images**.
- Can **toggle book visibility** between public and private.
- Can **download** a book's original source file.
- Can **view** system configuration values and processing circuit-breaker status (read-only).

A full re-run of OCR on an already-processed book, Knowledge Graph extraction, and AI summary regeneration are **not** available to editors — those require the Administrator role, since they are the most costly or highest-blast-radius operations.

### 2.4 System Administrator

An administrator has full control over the system.

- All editor permissions.
- Can trigger a **full OCR reprocess** for a book (re-extracting all page text).
- Can trigger **Knowledge Graph extraction/reprocessing** and curate the graph (merge duplicate entities, rename entities, delete incorrect relationships).
- Can trigger **AI book summary regeneration**.
- Can **bulk-reset** books stuck in an incomplete OCR state.
- Can **delete books** permanently.
- Can **view and manage all user accounts**.
- Can **change user roles** (promote/demote between reader, editor, and admin).
- Can **enable or disable user accounts**.
- Can **create and update system configuration** values and control the processing **circuit breaker** (reset or force-open).
- Can **review submissions** made through the public contact form.

### Permission Summary

| Action | Guest | Reader | Editor | Admin |
|--------|:-----:|:------:|:------:|:-----:|
| Browse public, ready books | ✅ | ✅ | ✅ | ✅ |
| Browse reference library, Quran search, knowledge graph view | ✅ | ✅ | ✅ | ✅ |
| Use AI Chat (per-book & global) | ❌ | ✅ | ✅ | ✅ |
| Upload books (PDF/DOCX) | ❌ | ❌ | ✅ | ✅ |
| Retry failed OCR pages | ❌ | ❌ | ✅ | ✅ |
| Reprocess Chunking / Embedding / Spell Check | ❌ | ❌ | ✅ | ✅ |
| Full OCR reprocess | ❌ | ❌ | ❌ | ✅ |
| Reprocess Knowledge Graph / Book Summary | ❌ | ❌ | ❌ | ✅ |
| Edit page content | ❌ | ❌ | ✅ | ✅ |
| Run spell check & apply corrections | ❌ | ❌ | ✅ | ✅ |
| Manage auto-correction rules | ❌ | ❌ | ✅ | ✅ |
| Edit book metadata | ❌ | ❌ | ✅ | ✅ |
| Upload / replace cover images | ❌ | ❌ | ✅ | ✅ |
| Download original book file | ❌ | ❌ | ✅ | ✅ |
| Toggle book visibility | ❌ | ❌ | ✅ | ✅ |
| View system configuration & circuit breaker status | ❌ | ❌ | ✅ | ✅ |
| Manage system configuration & circuit breaker control | ❌ | ❌ | ❌ | ✅ |
| Curate knowledge graph entities (merge/rename/delete/split/unmerge, review queue) | ❌ | ❌ | ❌ | ✅ |
| Trigger AI history-dictionary extraction & review staged terms | ❌ | ❌ | ❌ | ✅ |
| Bulk-reset incomplete OCR | ❌ | ❌ | ❌ | ✅ |
| Delete books | ❌ | ❌ | ❌ | ✅ |
| Manage users & roles | ❌ | ❌ | ❌ | ✅ |
| Enable / Disable user accounts | ❌ | ❌ | ❌ | ✅ |
| Review contact form submissions | ❌ | ❌ | ❌ | ✅ |

---

## 3. Feature Requirements

### 3.1 User Authentication

**REQ-AUTH-001: Sign Up via OAuth**
New users create an account by signing in with their Google, Facebook, Twitter (X), or Instagram account for the first time. There is no separate registration step — the account is created automatically upon first sign-in. The user's display name, email, and profile picture are imported from the OAuth provider. New users are assigned the **Reader** role by default.

**REQ-AUTH-002: Sign In via OAuth**
Returning users sign in using their Google, Facebook, Twitter, or Instagram account. No manual sign-in (username/password) is supported — authentication is exclusively through OAuth providers.

**REQ-AUTH-003: Automatic Session Management**
After sign-in, the user's session is maintained automatically. Short-lived access credentials are refreshed transparently so the user does not need to re-authenticate frequently. Sessions last up to 7 days before requiring a new sign-in.

**REQ-AUTH-004: Sign Out**
Users can sign out at any time. Signing out ends the current session on the current device.

**REQ-AUTH-005: First Administrator Bootstrap**
The system allows designating initial administrator accounts by configuring a list of email addresses. Users who sign up with one of these emails are automatically assigned the administrator role instead of the default Reader role.

**REQ-AUTH-006: Role-Based UI Adaptation**
The user interface adapts based on the signed-in user's role:
- Navigation items for management and upload are only visible to editors and admins.
- The global chat assistant is only visible to authenticated users.
- Delete and admin-only reprocessing actions are only visible to admins.
- Guests see the library and reference tools in a read-only mode.

---

### 3.2 User Management

**REQ-USER-001: View All Users**
Administrators can view a list of all registered users, including their email, display name, profile picture, role, account status (active/disabled), and registration date.

**REQ-USER-002: Filter Users by Role**
The user list can be filtered by role (admin, editor, or reader) to find specific groups of users.

**REQ-USER-003: Change User Role**
Administrators can promote or demote users between the reader, editor, and admin roles. An administrator cannot change their own role (to prevent accidental lockout).

**REQ-USER-004: Enable / Disable User Accounts**
Administrators can disable a user account, preventing that user from signing in or accessing the system. Disabled accounts can be re-enabled. An administrator cannot disable their own account.

**REQ-USER-005: View Own Profile**
Any authenticated user can view their own profile information (email, display name, role).

---

### 3.3 Book Upload & Ingestion

**REQ-UPLOAD-001: PDF and DOCX Upload**
Editors can upload PDF or DOCX files to the library through the management dashboard.

**REQ-UPLOAD-002: Duplicate Detection**
When a file is uploaded, the system checks whether an identical file has already been uploaded (based on file content hash, not filename). If a duplicate is detected, the upload is rejected and the existing matching book is returned instead of creating a new one.

**REQ-UPLOAD-003: Automatic Pipeline Pickup**
Uploaded PDF books are stored in a **pending** state. A background scanner automatically detects pending pages and begins OCR within roughly a minute of upload — no manual "start" action is required from an editor. DOCX uploads skip this state entirely: their text is already digital, so the book is marked OCR-complete immediately and enters the pipeline directly at the chunking step.

**REQ-UPLOAD-004: Initial Metadata Extraction**
Upon upload, the system automatically extracts:
- The book title (derived from the file name).
- The total page count.
The author field is left empty for the editor to fill in manually.

**REQ-UPLOAD-005: Upload Tracking**
The system records who uploaded each book (the uploader's email) and when.

**REQ-UPLOAD-006: Automated Cloud Storage Ingestion**
As an alternative to the manual upload UI, PDF files placed directly into the platform's cloud storage uploads location are automatically discovered and registered as new books by a background scanner (default cadence: every 5 minutes). Books ingested this way follow the same pending → automatic-OCR flow as UI uploads, but the author field may be auto-populated from the PDF's embedded metadata when available.

---

### 3.4 OCR Processing

**REQ-OCR-001: Automatic OCR Pipeline**
Once a PDF book is uploaded (or discovered via cloud storage ingestion), a background scanner claims its pages and dispatches OCR jobs automatically, without requiring an editor to explicitly start processing.

**REQ-OCR-002: AI-Powered Uyghur Text Extraction**
The system uses AI (Google Gemini) to extract Uyghur text from each page image of the PDF. The extraction is specifically tuned for the Uyghur language and Arabic script.

**REQ-OCR-003: Text Structure Preservation**
The OCR process preserves the structure of the original text:
- Paragraphs are maintained as separate blocks.
- Titles and chapter headings are identified and marked.
- Tables of contents are preserved as lists.
- Poems retain their original line breaks.
- Headers and footers are identified and labeled.
- Punctuation, Uyghur symbols, and Arabic script are preserved exactly.

**REQ-OCR-004: Parallel Page Processing**
Multiple pages are processed simultaneously to reduce total processing time. The level of parallelism is configurable.

**REQ-OCR-005: Per-Page Status Tracking**
Each page has its own processing status (pending, processing, completed, or error). Users can see which pages have been successfully processed and which have failed.

**REQ-OCR-006: Automatic Cover Image Extraction**
The first page of a PDF (or the equivalent for a DOCX file) is automatically extracted and saved as the book's cover image at upload time.

**REQ-OCR-007: Search Index Generation**
After OCR, the system generates a search index for each page to enable AI-powered question answering and semantic search. Pages are split into smaller overlapping chunks using recursive character splitting (split on paragraph breaks, then newlines, then word boundaries, with a hard character-length fallback) to improve search precision.

**REQ-OCR-008: Resumable Processing**
If OCR processing is interrupted (e.g., due to a system restart or timeout), it can be resumed from where it left off. Already-completed pages are not re-processed.

**REQ-OCR-009: Retry Failed Pages**
Editors can retry OCR for books that encountered errors. Only the failed pages are re-processed; successfully completed pages are preserved.

**REQ-OCR-010: Granular Reprocessing**
Editors can trigger reprocessing of the Chunking, Embedding, or Spell Check pipeline steps for a book. Administrators can additionally trigger a full OCR reprocess, Knowledge Graph reprocess, or AI summary reprocess. By default, the system protects human effort by skipping pages that have been manually verified or corrected (see REQ-READER-006), unless the reprocessing is explicitly targeted at those pages.

**REQ-OCR-011: Reindexing via Reprocessing**
There is no separate "reindex" action. Editors regenerate a book's search index by reprocessing its Chunking or Embedding step, which is useful when the indexing algorithm improves or when corrections have been made to page text.

**REQ-OCR-012: Processing Progress Visibility**
While a book is being processed, the management dashboard shows:
- The current processing stage (OCR, chunking, embedding, spell check, graph, or summary).
- A progress indicator (completed page count vs. total).
- The interface automatically refreshes to show updated status.

**REQ-OCR-013: Image-to-Text Tool**
Editors have access to a standalone OCR tool that extracts Uyghur text from an individual image. This is separate from the full-book processing pipeline and can be used for quick text extraction tasks.

**REQ-OCR-014: Bulk Incomplete-OCR Recovery**
Administrators can bulk-reset all books currently stuck in an incomplete OCR state from the management dashboard, re-queuing them for processing in one action.

---

### 3.5 Book Library & Browsing

**REQ-LIB-001: Home Page**
The home page serves as the primary entry point and includes:
- A prominent search bar at the top.
- A Uyghur proverb, weighted toward book- and knowledge-related themes, displayed for cultural engagement.
- Category filter buttons showing the most popular book categories.
- A grid of book cards with infinite scrolling.

**REQ-LIB-002: Book Cards**
Each book in the library is displayed as a card showing:
- Cover image (if available).
- Book title.
- Author name.
- A status badge (for editors/admins: pending, processing, ready, or error).

**REQ-LIB-003: Library View**
A dedicated "Global Library" view shows all available books in a card grid with infinite scrolling, allowing users to browse the full collection.

**REQ-LIB-004: Book Sorting**
In the management view, books can be sorted by:
- Title
- Author
- Upload date
- Status
- Any other metadata field
Sorting supports both ascending and descending order. The user's sort preference is remembered within the session.

**REQ-LIB-005: Pagination (Management)**
The management dashboard uses traditional pagination with configurable page size, whereas the home and library views use infinite scroll.

**REQ-LIB-006: Multi-Volume Grouping**
Books can optionally be grouped by "work" (title + author combination) so that multi-volume books appear as a single entry rather than multiple separate books.

**REQ-LIB-007: Automatic Status Polling**
When books are being processed, the interface automatically polls for status updates every 30 seconds so users can see progress without manually refreshing.

---

### 3.6 Search & Discovery

**REQ-SEARCH-001: Integrated Library Search**
Users can search for books by typing in a search query. The system performs an integrated search across book titles, author names, and category tags, with full support for Uyghur script variations and encodings.

**REQ-SEARCH-002: Category Filtering**
The home page displays the most popular book categories as clickable buttons. Clicking a category shows only books that belong to that category.

**REQ-SEARCH-003: Autocomplete Suggestions**
As the user types in the search bar, the system provides real-time suggestions including:
- Matching book titles.
- Matching author names.
- Matching categories.
Each suggestion is labeled with its type (title, author, or category) so the user can distinguish between them.

**REQ-SEARCH-004: Theme-Relevant Proverb**
Several views (home, library, management dashboard, chat, join-us) each display a randomly selected Uyghur proverb weighted toward a context-appropriate theme (e.g. books/knowledge on the home and library pages) each time they load. Each proverb includes its source reference (volume and page number).

**REQ-SEARCH-005: Tabbed Home Search**
The home page search bar is paired with a row of tabs that scope what a typed query searches: an **Ask** tab (the AI chat fallback), a **Books** tab (title/author/category search, see REQ-SEARCH-001), a **Content** tab that searches page-level text across the entire library and opens the reader directly to the matching page, and one tab each for the dictionary, proverbs, synonyms, history/terminology, names, English–Uyghur, Quran, and spell-check reference tools (see Section 3.16), each running the same lookup as its reference-library counterpart without leaving the home page. When the tabs do not fit in a single row, they are paginated into fixed-size pages with a "More" / "Back" toggle to page between them.

---

### 3.7 Book Reader

**REQ-READER-001: Right-to-Left Text Display**
The book reader displays text with proper right-to-left (RTL) direction as required by the Uyghur language.

**REQ-READER-002: Formatted Content Rendering**
The reader renders OCR-extracted text with formatting support: headings, bold/italic emphasis, lists, and other structural elements are displayed visually rather than as raw markup.

**REQ-READER-003: Page Navigation**
Users can navigate between pages using:
- Previous / Next page buttons.
- Direct page number input.
The current page number is displayed at all times.

**REQ-READER-004: Font Size Adjustment**
Users can increase or decrease the text font size to their preference.

**REQ-READER-005: Inline Page Editing**
Editors can switch any page into edit mode and directly modify the OCR text. After saving, the search index for that page is automatically regenerated.

**REQ-READER-006: Verified Content Protection**
Pages that have been manually verified (through direct editing or applying spell-check corrections) are marked with a "Verified" status. This status acts as a protective flag intended to keep human-reviewed content from being casually overwritten by subsequent automated reprocessing.

**REQ-READER-007: Page-Level Reprocessing**
Editors can trigger OCR re-processing for a single page from within the reader. This resets the page and runs OCR again, useful when the initial extraction was poor quality.

**REQ-READER-008: Integrated Chat**
The reader includes a collapsible chat panel allowing users to ask the AI assistant questions about the book while reading.

**REQ-READER-009: Integrated Spell Check**
The reader includes a spell check panel that can be triggered per-page, showing detected issues and correction suggestions inline with the text.

---

### 3.8 AI-Powered Chat Assistant

**REQ-CHAT-001: Per-Book Chat**
Authenticated users can ask questions about a specific book. The AI assistant answers based on the book's content, citing relevant pages.

**REQ-CHAT-002: Agentic Retrieval Pipeline**
Every chat request is answered by one retrieval pipeline (`ChatOrchestrator`) — there is no administrator-selectable strategy. A single-shot signal-extraction pass first classifies the question's intent and detects exact-phrase/quoted questions, which are answered directly from a keyword-only match without invoking the agent. Otherwise, a free-form, LLM-driven retrieval agent autonomously selects from a shared library of tools (chunk search, catalog and author lookup, book summaries, dictionary/proverb/synonym/history/name lookups, Quran search, spelling checks) to gather evidence, which is then graded and handed to a separate answer-synthesis step. The assistant presents a consistent "librarian" persona throughout.

**REQ-CHAT-003: Uyghur Language Responses**
The AI assistant always responds in the Uyghur language, regardless of the language of the question.

**REQ-CHAT-004: Context-Aware Answers**
When chatting within a book reader:
- If the user asks about "the current page," the assistant focuses its answer on the content of the page currently being viewed.
- If the user asks about "this volume," the assistant limits its search to the current volume in a multi-volume work.

**REQ-CHAT-005: Conversation History**
For signed-in users, the chat persists conversations server-side rather than only within the current browser session: each conversation is saved with an auto-generated title (from the book being discussed, or the first question asked), can be resumed, browsed in a history list, and deleted. The AI uses the conversation's message history to understand follow-up questions and provide contextually relevant answers.

**REQ-CHAT-006: Semantic Search**
The assistant uses AI-powered semantic search to find relevant content, combining meaning-based (embedding) search with keyword-based matching, for both conceptually relevant and terminologically precise results.

**REQ-CHAT-007: Multi-Part and Comparative Questions**
The assistant detects when a message contains multiple distinct questions and decomposes it into sub-questions, each addressed with its own tool calls within the same retrieval pass. It also detects comparison/contrast questions spanning multiple books or entities and answers across the relevant sources.

---

### 3.9 Spell Check & Correction

**REQ-SPELL-001: AI-Powered Spell Check**
The system detects spelling errors, OCR recognition errors, character confusion (similar-looking Uyghur/Arabic characters swapped), and grammar issues likely caused by OCR errors — both automatically, via a background pass that runs once a page finishes OCR (independently of, and in parallel with, chunking/embedding — when enabled system-wide), and on demand, when an editor runs spell check for a whole book or an individual page.

**REQ-SPELL-002: Correction Suggestions**
For each detected issue, the system provides:
- The original (incorrect) text.
- A suggested correction.
- A confidence score indicating how certain the system is about the correction, shown as a color-coded badge (high confidence in one color, lower confidence in another).
- Surrounding text context for reference.
All detected suggestions are shown; confidence coloring helps editors prioritize which ones to review first.

**REQ-SPELL-003: Apply Corrections**
Editors can review the suggested corrections and apply them. Applying corrections:
- Replaces the incorrect text with the corrected version.
- Marks the page as "verified" to protect it from being overwritten by future reprocessing.
- Triggers regeneration of the search index for that page.

**REQ-SPELL-004: Visual Highlighting**
Detected spelling issues are visually highlighted within the reader text, allowing editors to see problems in context before deciding whether to apply corrections.

**REQ-SPELL-005: Global Auto-Correction Rules**
Editors can maintain a shared library of word-level auto-correction rules (incorrect form → corrected form) through a dedicated admin panel. Rules that are applied frequently are automatically fed back into the OCR prompt, helping the system avoid repeating the same recognition errors on future pages and books.

---

### 3.10 Book Metadata Management

**REQ-META-001: Title Editing**
Editors can edit a book's title directly in the management table via inline editing.

**REQ-META-002: Author Editing**
Editors can edit a book's author name directly in the management table via inline editing. The author field defaults to empty (not "Unknown Author") unless it was auto-populated from PDF metadata during cloud storage ingestion (see REQ-UPLOAD-006).

**REQ-META-003: Volume Number**
Editors can assign a volume number to a book for organizing multi-volume works. The volume number is an optional integer that can be set or cleared.

**REQ-META-004: Category Management**
Editors can add or remove categories for a book using a tag editor interface. The editor provides:
- A text input for adding new categories.
- Autocomplete suggestions from categories already used in the library.
- Ability to remove individual categories.

**REQ-META-005: Protected Fields**
Certain fields cannot be directly edited by users: content hash, processing status, upload date, and page count. These are managed automatically by the system.

---

### 3.11 Cover Image Management

**REQ-COVER-001: Automatic Cover Generation**
When a book is uploaded, the system automatically generates a cover image from its first page.

**REQ-COVER-002: Manual Cover Upload**
Editors can upload a custom cover image for a book, overriding the automatically generated cover. The uploaded image is validated and converted to a standard format.

**REQ-COVER-003: Cover Display**
Cover images are displayed on book cards throughout the library and in the reader view.

---

### 3.12 Book Visibility & Access Control

**REQ-VIS-001: Public and Private Books**
Each book has a visibility setting: **public** or **private**.
- **Public** books that are fully processed are visible to everyone, including unauthenticated guests.
- **Private** books are only visible to authenticated editors and administrators.
- Newly uploaded books default to **private**.

**REQ-VIS-002: Visibility Toggle**
Editors can toggle a book between public and private visibility from the management dashboard. The visibility status is indicated by an icon (globe for public, shield for private).

**REQ-VIS-003: Guest Access Restrictions**
Unauthenticated guests can only see books that meet **both** conditions:
1. The book is marked as **public**.
2. The book's processing is **complete** (status = ready).

Books that are private, pending, processing, or in an error state are hidden from guests.

**REQ-VIS-004: Error Status Override on Publish**
If an editor sets a book's visibility to **public** while its processing status is **error**, the system clears the error state (status is set to `ready`) instead of leaving the book stuck hidden from guests despite the visibility change. This is unconditional — it does not re-verify that every page actually completed OCR/chunking/embedding — so editors should only publish an errored book after confirming its content is usable.

---

### 3.13 Administration Dashboard

**REQ-ADMIN-001: Book Management Table**
The management dashboard displays all books in a sortable, paginated table regardless of their status or visibility. The table shows:
- Book title
- Author
- Volume number
- Processing status (with color-coded badges)
- Number of pages (completed / total)
- Upload date
- Current processing step
- Categories

**REQ-ADMIN-002: Inline Editing**
Title, author, and volume number can be edited directly within the table without navigating to a separate edit page.

**REQ-ADMIN-003: Action Menu**
Each book in the table has a context menu with available actions:
- Open in Reader
- Replace Cover
- Retry Failed Pages
- Reprocess OCR (admin only)
- Reprocess Chunking
- Reprocess Embedding
- Reprocess Spell Check
- Reprocess Knowledge Graph (admin only)
- Reprocess Book Summary (admin only)
- Delete (admin only)

Toggling visibility is available as a quick-access control on each table row. Available actions adapt based on the book's current status and the user's role.

**REQ-ADMIN-004: Confirmation Dialogs**
Destructive or costly actions (Reprocess, Delete) require confirmation before execution.

**REQ-ADMIN-005: Tabbed Interface**
The management page is organized into tabs:
- **Books**: Book Management table (available to all editors).
- **Users**: User management panel (available to admins only).

**REQ-ADMIN-006: Action Feedback**
All management actions provide immediate feedback via toast notifications indicating success or failure.

**REQ-ADMIN-007: System Configuration Management**
Editors can view system configuration values and processing circuit-breaker status. Administrators can additionally create and update configuration values, and reset or force-open the circuit breaker to control automated processing.

**REQ-ADMIN-008: Contact Submissions Review**
Administrators can view and filter messages submitted through the public contact form (see REQ-CONTACT-001).

---

### 3.14 Auditing & Change Tracking

**REQ-AUDIT-001: Upload Tracking**
The system records who uploaded each book (by email) and when the upload occurred.

**REQ-AUDIT-002: Modification Tracking**
When any book metadata or page content is modified, the system records:
- **When** the change was made (timestamp).
- **Who** made the change (the editor's email).
This applies to both book-level changes (title, author, categories, visibility) and page-level changes (text edits, spell check corrections).

---

### 3.15 Error Handling & Recovery

**REQ-ERR-001: Per-Page Error Reporting**
If OCR fails on a specific page, the error is recorded for that page without stopping processing of other pages. The error message is stored for diagnostic purposes.

**REQ-ERR-002: Book-Level Error Summary**
Books display a summary of errors including the count of errored pages and the most recent error message.

**REQ-ERR-003: Error History**
The system maintains a history of all errors that occurred during processing, including timestamps, error types, and messages.

**REQ-ERR-004: Automatic Recovery on Restart**
If the system is restarted while books are being processed, those books are automatically detected and their processing is resumed without manual intervention.

**REQ-ERR-005: Duplicate Processing Prevention**
The system prevents the same book from being processed by multiple workers simultaneously. If a processing job is already running for a book, additional requests are silently ignored.

**REQ-ERR-006: Timeout Handling**
Processing jobs have a maximum time limit. If processing exceeds this limit, the job is marked as failed and the book can be retried or resumed by an editor or administrator.

---

### 3.16 Reference Library & Language Tools

**REQ-REF-001: Multi-Dictionary Reference Hub**
A public "Dictionary" page presents a set of Uyghur-language reference tools as tabs: a general word list, a Uyghur dictionary, proverbs, a history/terminology dictionary, a names dictionary, an English–Uyghur dictionary, and a synonyms dictionary. Each tool supports keyword search, browsing entries by starting letter, and viewing entry-count statistics. No authentication is required.

**REQ-REF-002: Quran Search**
A separate public view lets users search and browse Quran verses (surah and ayah) by keyword.

**REQ-REF-003: AI Assistant Tool Integration**
The chat assistant (Section 3.8) can call the same dictionary, proverb, synonym, history, names, English–Uyghur translation, spelling, and Quran lookups as tools when answering user questions, in addition to searching book content.

---

### 3.17 Knowledge Graph

**REQ-GRAPH-001: Public Knowledge Graph Visualization**
A public graph view presents entities (e.g. people, places) and their relationships, extracted from book content, as an interactive visualization that any visitor — including guests — can explore and filter.

**REQ-GRAPH-002: Per-Book Graph Extraction**
Administrators can trigger knowledge-graph extraction for a specific book, which analyzes its content in batches to identify entities and relationships. This feature is gated by a system-wide "knowledge graph enabled" configuration flag. Books that have completed extraction are flagged so the UI can indicate graph availability.

**REQ-GRAPH-003: Entity Curation**
Administrators can merge duplicate entities, rename entities, and delete incorrect relationships in the knowledge graph to keep it accurate over time.

**REQ-GRAPH-004: Automated Resolution Review, Split, and Unmerge**
Entity resolution (deduplication) runs automatically as part of graph extraction. Ambiguous merge decisions the algorithm can't resolve with confidence are parked in a review queue for an administrator to approve or reject. Every automatic or admin-approved merge is logged with a pre-merge snapshot, so an administrator can undo (unmerge) any individual merge afterward. Administrators can also split an entity that was incorrectly merged into another.

---

### 3.18 AI Book Summaries

**REQ-SUMMARY-001: Automatic Summary Generation**
A background job generates an AI-written semantic summary for each processed book.

**REQ-SUMMARY-002: Summary Access**
Any user can view a book's summary for public, ready books; editors and administrators can view summaries regardless of a book's visibility or status.

**REQ-SUMMARY-003: Admin Regeneration**
Administrators can manually trigger regeneration of a book's summary, discarding the previous one.

**REQ-SUMMARY-004: Summary-Based Catalog Search**
The chat assistant can search book summaries — not just page-level content — to answer catalog-style questions such as "what books are about X," and to identify sister volumes of a multi-volume work.

---

### 3.19 Contact & Community Engagement

**REQ-CONTACT-001: Public Contact Form**
Any visitor, including guests, can submit a message through the public "Join Us" page (name, email, area of interest, and message). No authentication is required.

**REQ-CONTACT-002: Admin Submission Review**
Administrators can view and filter submitted contact messages from the management dashboard (see REQ-ADMIN-008).

---

### 3.20 Content Sharing

**REQ-SHARE-001: Social Share Previews**
Links to a specific book or a shared chat Q&A conversation render Open Graph preview cards (title, description, image) when unfurled by social platforms and messaging apps.

---

### 3.21 AI History Dictionary Extraction

**REQ-HIST-001: Admin-Triggered Extraction**
Administrators can trigger AI-based extraction of historical terms and entities (people, places, events, terminology) from a specific book's pages. Extraction is a distinct action from Knowledge Graph extraction and does not write directly to the public history dictionary.

**REQ-HIST-002: Staging & Review**
Extracted terms are held in a staging area pending admin review before publication. Administrators can approve or bulk-approve staged terms, reject individual terms, resolve/merge the individual facts collected for a term, and trigger AI synthesis of a candidate definition from those facts.

**REQ-HIST-003: Batch Extraction Mode**
For lower-cost, higher-volume extraction, the system can submit the extraction task through the AI provider's asynchronous batch API instead of processing in real time, trading latency for cost. This mode is independently toggleable via system configuration and defaults to off.

**REQ-HIST-004: Feature Flag**
The history-extraction feature as a whole is toggleable via a system-wide configuration flag (defaulting to enabled), independent of the Knowledge Graph feature flag.

---

## 4. Scalability & Performance

**REQ-SCALE-001: Target Corpus Size**
The system must be designed and optimized to handle a digital library of at least **2,000 books**. Based on an average of 300 pages per book and semantic chunking, the system must effectively manage and search a database of approximately **3,000,000 unique text segments**.

**REQ-SCALE-002: Database-Level Vector Indexing**
To maintain performance at scale, the system must utilize database-level vector indexing (PostgreSQL with pgvector). Similarity calculations for AI chat and semantic search must be performed by the database engine rather than the application tier to ensure sub-second retrieval times across millions of records.

**REQ-SCALE-003: Scoped Retrieval**
The Global Chat Assistant must narrow the search space to relevant books, categories, or metadata filters before performing vector similarity searches, preventing performance degradation and "noise" from unrelated sections of the library. The retrieval agent does this by selecting scoping tools (catalog search, author/title lookup, book-summary search) as part of its tool-calling loop, informed by signals (title/author matches, intent classification) extracted from the question up front.

**REQ-SCALE-004: Chat Response Latency Targets**
The system should target a total response latency of under **5 seconds** for typical AI chat questions, even with a library of 2,000 books. This includes time for routing, retrieval, and final answer generation.

**REQ-SCALE-005: Bulk Processing Efficiency**
The backend processing pipeline (OCR and Indexing) must support horizontally scalable workers. The system must be capable of processing a batch of 100 new books simultaneously without degrading the performance of the front-facing reading and chat applications. For very high ingestion volumes, OCR and embedding generation can each be switched to an asynchronous batch-processing mode (submit-then-poll against the AI provider's batch API) as a lower-cost alternative to real-time processing, at the cost of added latency per page.

**REQ-SCALE-006: Semantic Caching**
The system includes a Redis-backed caching layer that caches answers to frequently asked or semantically similar questions, as well as intermediate query embeddings and similarity search results. This reduces operational costs and provides near-instantaneous responses for common queries.
