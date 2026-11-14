import { components } from './api-types';

export type ErrorEventSchema = components['schemas']['ErrorEvent'];
export interface ErrorEvent extends Omit<ErrorEventSchema, 'ts' | 'context'> {
  ts: string | Date;
  context?: Record<string, unknown>;
}

export type ExtractionResultSchema = components['schemas']['ExtractionResult'];
export interface ExtractionResult extends Omit<ExtractionResultSchema, 'status' | 'pipelineStep' | 'milestone' | 'contentPageNumber'> {
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | null;
  milestone?: 'idle' | 'running' | 'succeeded' | 'failed' | null;
  detectedPageNumber?: number | null;
  detected_page_number?: number | null;
  contentPageNumber?: string | number | null;
  content_page_number?: string | number | null;
  contentPageNumberManual?: boolean;
  content_page_number_manual?: boolean;
  displayPageNumber?: string | null;
  display_page_number?: string | null;
}

export type BookSchema = components['schemas']['Book'];
export interface Book extends Omit<
  BookSchema,
  | 'uploadDate'
  | 'lastUpdated'
  | 'lastError'
  | 'pages'
  | 'status'
  | 'visibility'
  | 'pipelineStep'
  | 'ocrMilestone'
  | 'structureMilestone'
  | 'chunkingMilestone'
  | 'embeddingMilestone'
  | 'spellCheckMilestone'
> {
  uploadDate: Date;
  lastUpdated: Date | null;
  lastError?: ErrorEvent | null;
  pages: ExtractionResult[];
  ocrVersion?: number;
  ocr_version?: number;
  contentPageOffset?: number;
  content_page_offset?: number;
  contentPageMap?: Record<string, number> | null;
  content_page_map?: Record<string, number> | null;
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'ready' | 'error';
  visibility?: 'public' | 'private';
  pipelineStep?: 'ocr' | 'structure' | 'chunking' | 'embedding' | 'spell_check' | 'ready' | null;
  ocrMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  structureMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  chunkingMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  embeddingMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  spellCheckMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
}

export type PaginatedBooksSchema = components['schemas']['PaginatedBooks'];
export interface PaginatedBooks extends Omit<PaginatedBooksSchema, 'books'> {
  books: Book[];
}

export interface Message {
  role: 'user' | 'model';
  text: string;
  characterId?: string;
  /** The RAGEvaluation DB id returned in the SSE done event. Used for feedback. */
  evalId?: number;
  /** User thumbs rating once submitted ('positive' | 'negative'). */
  feedback?: 'positive' | 'negative';
  /** Whether the message is a degraded/partial response due to a tool failure */
  partialResult?: boolean;
  /** Estimated LLM token usage/cost for this turn, from the SSE done event. */
  cost?: {
    inputTokens: number;
    outputTokens: number;
    costUsd: number;
  };
}

export interface Conversation {
  id: string;
  userId: string;
  bookId?: string | null;
  bookTitle?: string | null;
  isGlobal: boolean;
  title?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationMessage {
  id: string;
  conversationId: string;
  role: 'user' | 'model';
  content: string;
  agentSteps?: Record<string, unknown> | null;
  usedBookIds?: string[] | Record<string, unknown> | null;
  currentPage?: number | null;
  evalId?: number | null;
  cost?: {
    inputTokens: number;
    outputTokens: number;
    costUsd: number;
  } | null;
  feedback?: 'positive' | 'negative' | null;
  createdAt: string;
}

export interface ChatRequest {
  question: string;
  bookId?: string;
  isGlobal?: boolean;
  history?: Message[];
  currentPage?: number;
  characterId?: string;
  conversationId?: string;
}

export interface Bookmark {
  id: string;
  bookId: string;
  bookTitle: string | null;
  pageNumber: number;
  name: string;
  quoteText: string | null;
  createdAt: string;
}

export interface ReadingProgressEntry {
  bookId: string;
  bookTitle: string | null;
  bookCoverUrl: string | null;
  pageNumber: number;
  updatedAt: string;
}

