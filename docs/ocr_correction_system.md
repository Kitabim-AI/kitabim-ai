# Corpus-Based Vocabulary Registry & OCR Correction System

## 1. Overview
The Kitabim AI project processes tens of thousands of pages of historic and modern Uyghur texts via OCR. While the OCR accuracy is high, the "long tail" of character-level errors (typos) impacts search quality, RAG retrieval accuracy, and the overall professional feel of the reader.

This system establishes a **dynamic vocabulary registry** that learns from the entire corpus (currently 74 books / 36,000 pages) to identify, group, and correct OCR errors at scale.

## 2. The Problem
Traditional spell-checking (using a static dictionary file) is insufficient for this project because:
1. **Agglutination**: Uyghur has millions of valid word forms; a static file cannot cover them all.
2. **Contextual Terms**: Books contain specific historical, religious, or technical terms missing from standard dictionaries.
3. **OCR Bias**: OCR engines often have predictable "visual slips" (e.g., confusing `ۆ` and `ۇ`).
4. **Scale**: Manually checking 36,000 pages is impossible.

## 3. The Solution: "The Kitabim Registry"
Instead of a pre-defined dictionary, the system uses the library itself as the "source of truth." It operates on the principle of **Statistical Consensus**: If a word appears in multiple books by different authors, it is "Verified." If it appears once and is nearly identical to a "Verified" word, it is a "Suspect."

### Key Components:
- **Registry Engine**: Tokenizes all text into a `vocabulary` collection storing `{word, frequency, book_span}`.
- **Candidate Generator**: Runs high-speed fuzzy matching (Levenshtein distance) to find suspect-correction pairs.
- **Bulk Rectifier**: Allows an administrator to fix hundreds of identical typos across the entire library with a single click.
- **Incremental Learner**: Updates the registry in real-time as new books are uploaded.

## 4. Architecture

### Data Model (`vocabulary` collection)
```typescript
{
  word: string,         // Unique token
  frequency: number,    // Global count
  bookSpan: number,     // Number of distinct books containing this word
  status: "verified" | "suspect" | "ignored",
  lastSeen: Date
}
```

### The Correction Workflow
1. **Automatic Detection**: Identify words with `frequency: 1` that match a word with `frequency > 50` at a distance of 1 character.
2. **Bulk Proposal**: Group identical transformations (e.g., all 400 instances of `كىتاپ` across 12 books).
3. **Admin Verification**: Admin reviews the group and clicks "Apply All."
4. **Distributed Update**: System performs a background update on the `pages` collection and triggers a re-index for affected RAG chunks.

## 5. Implementation Plan

### Phase 1: Analytics & Registry (Week 1)
- Create the `vocabulary` collection in MongoDB.
- Run a "Full Corpus Scan" to populate initial frequencies.
- Implement the `Incremental Hook` in `pdf_service.py` to update word counts during new OCR jobs.

### Phase 2: The Identification Engine (Week 1)
- Develop the `Candidate Generator` using the Fast Levenshtein algorithm.
- Build a prototype API `GET /api/registry/candidates` that returns the most common suspected typos.

### Phase 3: Admin UI & Correction (Week 2)
- Create the "Registry Manager" dashboard in `AdminView.tsx`.
- Implement `POST /api/registry/bulk-rectify` to perform atomic updates across the library.
- Add "Confidence Scoring" (Auto-fix entries with >95% confidence).

### Phase 4: Reader Integration (Week 2)
- Highlight suspected typos in `ReaderView.tsx`.
- Add "Correction Tooltips" to allow readers to fix single errors instantly while reading.

## 6. Success Metrics
- **Reduction in "Single-Use" Word Count**: Goal is a 20% reduction in unique vocab through normalization.
- **Search Precision**: Higher overlap between user queries and book content.
- **RAG Latency**: Faster retrieval due to fewer "noisy" embedding vectors.
