# Kitabim.AI — Business Requirements Document

> **Generated:** 2026-02-11  
> **Method:** Reverse-engineered from the implemented system

---

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
4. [Scalability & Performance](#4-scalability--performance)

---

## 1. Product Overview

**Kitabim.AI** is an intelligent Uyghur Digital Library platform. Its purpose is to digitize Uyghur-language books from PDF format, provide AI-powered reading assistance, and serve as a curated online library for Uyghur literature.

The platform supports three core workflows:

- **Digitization** — Upload PDF books and extract Uyghur text using AI-based Optical Character Recognition (OCR).
- **Curation** — Editors review, correct, categorize, and manage the digitized book collection.
- **Reading & AI Assistance** — Readers browse the library, read books, and ask an AI assistant questions about book content.

---

## 2. User Roles & Permissions

The system supports four levels of access:

### 2.1 Guest (Unauthenticated)

A guest is any visitor who has not signed in. Guests have limited, read-only access.

- Can browse and view books that are both **publicly visible** and **fully processed**.
- Cannot use the AI chat assistant.
- Cannot upload, edit, or manage any content.

### 2.2 Reader

A reader is a signed-in user with basic access.

- All guest permissions.
- Can use the **per-book AI chat assistant** to ask questions about a specific book.
- Can use the **global AI chat assistant** to ask questions across the entire library.

### 2.3 Editor

An editor is a signed-in user responsible for content management.

- All reader permissions.
- Can **upload** new PDF books to the library.
- Can **start, retry, and monitor OCR processing** for uploaded books.
- Can **edit page content** directly within the reader.
- Can **reprocess specific steps** (OCR, Chunking, Embedding, Word Index, or Spell Check) or **reindex** existing books.
- Can **run spell check** and **apply corrections**.
- Can **edit book metadata** (title, author, volume, categories).
- Can **upload custom cover images**.
- Can **toggle book visibility** between public and private.

### 2.4 System Administrator

An administrator has full control over the system.

- All editor permissions.
- Can **delete books** permanently.
- Can **view and manage all user accounts**.
- Can **change user roles** (promote/demote between reader, editor, and admin).
- Can **enable or disable user accounts**.

### Permission Summary

| Action | Guest | Reader | Editor | Admin |
|--------|:-----:|:------:|:------:|:-----:|
| Browse public, ready books | ✅ | ✅ | ✅ | ✅ |
| Use AI Chat (per-book) | ❌ | ✅ | ✅ | ✅ |
| Use AI Chat (global) | ❌ | ✅ | ✅ | ✅ |
| Upload books | ❌ | ❌ | ✅ | ✅ |
| Start / Retry OCR | ❌ | ❌ | ✅ | ✅ |
| Edit page content | ❌ | ❌ | ✅ | ✅ |
| Reprocess / Reindex books | ❌ | ❌ | ✅ | ✅ |
| Run spell check & apply corrections | ❌ | ❌ | ✅ | ✅ |
| Edit book metadata | ❌ | ❌ | ✅ | ✅ |
| Upload cover images | ❌ | ❌ | ✅ | ✅ |
| Toggle book visibility | ❌ | ❌ | ✅ | ✅ |
| Delete books | ❌ | ❌ | ❌ | ✅ |
| Manage users & roles | ❌ | ❌ | ❌ | ✅ |
| Enable / Disable user accounts | ❌ | ❌ | ❌ | ✅ |

---

## 3. Feature Requirements

### 3.1 User Authentication

**REQ-AUTH-001: Sign Up with Google**  
New users create an account by signing in with their Google account for the first time. There is no separate registration step — the account is created automatically upon first sign-in. The user's display name, email, and profile picture are imported from their Google profile. New users are assigned the **Reader** role by default.

**REQ-AUTH-002: Sign In with Google**  
Returning users sign in using their Google account. No manual sign-in (username/password) is supported — authentication is exclusively through Google.

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
- Delete actions are only visible to admins.
- Guests see the library in a read-only mode.

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

**REQ-UPLOAD-001: PDF Upload**  
Editors can upload PDF files to the library. The system accepts PDF format only.

**REQ-UPLOAD-002: Duplicate Detection**  
When a PDF is uploaded, the system checks whether an identical file has already been uploaded (based on file content, not filename). If a duplicate is detected, the upload is rejected and the user is informed which existing book matches.

**REQ-UPLOAD-003: Pending State After Upload**  
Uploaded books are stored in a "pending" state. The OCR process is **not** started automatically — an editor must explicitly choose to start processing. This allows editors to review uploads before committing to costly OCR processing.

**REQ-UPLOAD-004: Initial Metadata Extraction**  
Upon upload, the system automatically extracts:
- The book title (derived from the file name).
- The total page count.
The author field is left empty for the editor to fill in manually.

**REQ-UPLOAD-005: Upload Tracking**  
The system records who uploaded each book (the uploader's email) and when.

---

### 3.4 OCR Processing

**REQ-OCR-001: Manual OCR Start**  
Editors trigger OCR processing for a pending book from the management dashboard. A confirmation prompt is shown before starting.

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
The first page of the PDF is automatically saved as the book's cover image during processing.

**REQ-OCR-007: Automatic Category Classification**  
After OCR is complete, the system uses AI to automatically suggest categories for the book based on its content.

**REQ-OCR-008: Search Index Generation**  
After OCR, the system generates a search index for each page to enable AI-powered question answering and semantic search. Pages are split into smaller overlapping segments to improve search precision.

**REQ-OCR-009: Resumable Processing**  
If OCR processing is interrupted (e.g., due to a system restart or timeout), it can be resumed from where it left off. Already-completed pages are not re-processed.

**REQ-OCR-010: Retry Failed Pages**  
Editors can retry OCR for books that encountered errors. Only the failed pages are re-processed; successfully completed pages are preserved.

**REQ-OCR-011: Granular Reprocessing**  
Editors can trigger a reprocessing of specific pipeline steps (e.g., re-running only chunking or re-running OCR). By default, the system protects human effort by skipping pages that have been manually verified or corrected (see REQ-READER-006), unless the editor explicitly chooses to override this protection.

**REQ-OCR-012: Reindex Without Re-OCR**  
Editors can regenerate the search index for a book without re-running OCR. This is useful when the indexing algorithm improves or when corrections have been made to page text.

**REQ-OCR-013: Processing Progress Visibility**  
While a book is being processed, the management dashboard shows:
- The current processing stage (OCR or indexing).
- A progress indicator (completed page count vs. total).
- The interface automatically refreshes to show updated status.

**REQ-OCR-014: Image-to-Text Tool**  
Editors have access to a standalone OCR tool that extracts Uyghur text from an individual image. This is separate from the full-book processing pipeline and can be used for quick text extraction tasks.

---

### 3.5 Book Library & Browsing

**REQ-LIB-001: Home Page**  
The home page serves as the primary entry point and includes:
- A prominent search bar at the top.
- A random Uyghur proverb displayed for cultural engagement.
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
When books are being processed, the interface automatically polls for status updates every 10 seconds so users can see progress without manually refreshing.

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
The home page displays a contextually relevant Uyghur proverb each time it loads. The system prioritizes proverbs related to educational themes such as "Books," "Knowledge," and "Wisdom." Each proverb includes its source reference (volume and page number).

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
Pages that have been manually verified (through direct editing or applying spell-check corrections) are marked with a "Verified" status. This status acts as a permanent lock that protects human-reviewed content from being accidentally overwritten by subsequent automated book-level re-processing tasks.

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

**REQ-CHAT-002: Intelligent Global Library Chat**  
Authenticated users can access a "Global Assistant" that answers questions across the entire library. The system employs an intelligent routing mechanism where an AI "Librarian" first analyzes the question to identify relevant sections (categories) of the library. This scoping ensures high accuracy and reduces noise from unrelated book content.

**REQ-CHAT-003: Uyghur Language Responses**  
The AI assistant always responds in the Uyghur language, regardless of the language of the question.

**REQ-CHAT-004: Context-Aware Answers**  
When chatting within a book reader:
- If the user asks about "the current page," the assistant focuses its answer on the content of the page currently being viewed.
- If the user asks about "this volume," the assistant limits its search to the current volume in a multi-volume work.

**REQ-CHAT-005: Conversation History**  
The chat maintains a history of previous messages within the session. The AI uses conversation history to understand follow-up questions and provide contextually relevant answers.

**REQ-CHAT-006: Semantic Search**  
The assistant uses AI-powered semantic search to find relevant content, combining:
- Meaning-based search (understanding the intent of the question).
- Keyword-based search (matching specific terms).
This hybrid approach ensures both conceptually relevant and terminologically precise results.

---

### 3.9 Spell Check & Correction

**REQ-SPELL-001: AI-Powered Spell Check**  
Editors can run spell check on an entire book or on individual pages. The system uses AI to detect:
- Spelling errors.
- OCR recognition errors (characters misread during digitization).
- Character confusion (similar-looking Uyghur/Arabic characters swapped).
- Grammar issues likely caused by OCR errors.

**REQ-SPELL-002: Correction Suggestions**  
For each detected issue, the system provides:
- The original (incorrect) text.
- A suggested correction.
- A confidence score indicating how certain the system is about the correction.
- A brief explanation of why the correction is suggested.
- Surrounding text context for reference.
Only suggestions with a confidence of 60% or higher are shown.

**REQ-SPELL-003: Apply Corrections**  
Editors can review the suggested corrections and apply them. Applying corrections:
- Replaces the incorrect text with the corrected version.
- Marks the page as "verified" to protect it from being overwritten by future reprocessing.
- Triggers regeneration of the search index for that page.

**REQ-SPELL-004: Visual Highlighting**  
Detected spelling issues are visually highlighted within the reader text, allowing editors to see problems in context before deciding whether to apply corrections.

---

### 3.10 Book Metadata Management

**REQ-META-001: Title Editing**  
Editors can edit a book's title directly in the management table via inline editing.

**REQ-META-002: Author Editing**  
Editors can edit a book's author name directly in the management table via inline editing. The author field defaults to empty (not "Unknown Author").

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
When a book is processed, the system automatically generates a cover image from the first page of the PDF.

**REQ-COVER-002: Manual Cover Upload**  
Editors can upload a custom cover image for a book, overriding the automatically generated cover. The uploaded image is validated and converted to a standard format.

**REQ-COVER-003: Cover Display**  
Cover images are displayed on book cards throughout the library and in the reader view.

**REQ-COVER-004: Missing Cover Recovery**  
If a book is missing its cover image (e.g., due to file loss), the system automatically detects this and regenerates the cover on next startup.

---

### 3.12 Book Visibility & Access Control

**REQ-VIS-001: Public and Private Books**  
Each book has a visibility setting: **public** or **private**.
- **Public** books that are fully processed are visible to everyone, including unauthenticated guests.
- **Private** books are only visible to authenticated editors and administrators.
- Newly uploaded books default to **private**.
- **Legacy Rule**: To ensure continuity, existing books that were created before the visibility system was implemented are treated as **public** by default.

**REQ-VIS-002: Visibility Toggle**  
Editors can toggle a book between public and private visibility from the management dashboard. The visibility status is indicated by an icon (globe for public, shield for private).

**REQ-VIS-003: Guest Access Restrictions**  
Unauthenticated guests can only see books that meet **both** conditions:
1. The book is marked as **public**.
2. The book's processing is **complete** (status = ready).

Books that are private, pending, processing, or in an error state are hidden from guests.

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
- Start OCR (for pending books)
- Retry OCR (for books with errors)
- Reprocess Step (OCR, Chunking, Embedding, Word Index, or Spell Check)
- Reindex (regenerate search index)
- Toggle Visibility (public ↔ private)
- Delete (admin only)

Available actions adapt based on the book's current status and the user's role.

**REQ-ADMIN-004: Confirmation Dialogs**  
Destructive or costly actions (Start OCR, Reprocess, Delete) require confirmation before execution.

**REQ-ADMIN-005: Tabbed Interface**  
The management page is organized into tabs:
- **Books**: Book Management table (available to all editors).
- **Users**: User management panel (available to admins only).

**REQ-ADMIN-006: Action Feedback**  
All management actions provide immediate feedback via toast notifications indicating success or failure.

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
Processing jobs have a maximum time limit. If processing exceeds this limit, the job is marked as failed and the book can be retried or resumed by an editor.

---

## 4. Scalability & Performance

**REQ-SCALE-001: Target Corpus Size**  
The system must be designed and optimized to handle a digital library of at least **2,000 books**. Based on an average of 300 pages per book and semantic chunking, the system must effectively manage and search a database of approximately **3,000,000 unique text segments**.

**REQ-SCALE-002: Database-Level Vector Indexing**  
To maintain performance at scale, the system must utilize database-level vector indexing (PostgreSQL with pgvector). Similarity calculations for AI chat and semantic search must be performed by the database engine rather than the application tier to ensure sub-second retrieval times across millions of records.

**REQ-SCALE-003: Mandatory Intelligent Routing**  
The Global Chat Assistant must employ an intelligent "Routing" or "Librarian" phase for every query. The system must first narrow the search space to relevant categories or metadata filters before performing vector similarity searches, preventing performance degradation and "noise" from unrelated sections of the library.

**REQ-SCALE-004: Chat Response Latency Targets**  
The system should target a total response latency of under **5 seconds** for typical AI chat questions, even with a library of 2,000 books. This includes time for routing, retrieval, and final answer generation.

**REQ-SCALE-005: Bulk Processing Efficiency**  
The backend processing pipeline (OCR and Indexing) must support horizontally scalable workers. The system must be capable of processing a batch of 100 new books simultaneously without degrading the performance of the front-facing reading and chat applications.

**REQ-SCALE-006: Semantic Caching** (Implemented)  
The system includes a Redis-backed caching layer that caches answers to frequently asked or semantically similar questions, as well as intermediate query embeddings and similarity search results. This reduces operational costs and provides near-instantaneous responses for common queries.


---

*End of Business Requirements Document*
