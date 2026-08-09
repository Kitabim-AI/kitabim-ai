import { components } from './api-types';

export type ErrorEventSchema = components['schemas']['ErrorEvent'];
export interface ErrorEvent extends Omit<ErrorEventSchema, 'ts' | 'context'> {
  ts: string | Date;
  context?: Record<string, unknown>;
}

export type ExtractionResultSchema = components['schemas']['ExtractionResult'];
export interface ExtractionResult extends Omit<ExtractionResultSchema, 'status' | 'pipelineStep' | 'milestone'> {
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | null;
  milestone?: 'idle' | 'running' | 'succeeded' | 'failed' | null;
  contentPageNumber?: string | null;
  content_page_number?: string | null;
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
  | 'chunkingMilestone'
  | 'embeddingMilestone'
  | 'spellCheckMilestone'
> {
  uploadDate: Date;
  lastUpdated: Date | null;
  lastError?: ErrorEvent | null;
  pages: ExtractionResult[];
  contentPageOffset?: number;
  content_page_offset?: number;
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'ready' | 'error';
  visibility?: 'public' | 'private';
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | 'spell_check' | 'ready' | null;
  ocrMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
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

