
export interface ExtractionResult {
  pageNumber: number;
  text?: string;
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | null;
  milestone?: 'idle' | 'running' | 'succeeded' | 'failed' | null;
  error?: string;
}

export interface ErrorEvent {
  ts: string | Date;
  kind: string;
  message: string;
  context?: Record<string, unknown>;
}

export interface Book {
  id: string;
  contentHash: string;
  title: string;
  author: string;
  volume?: number | null;
  totalPages: number;
  pages: ExtractionResult[];
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'ready' | 'error';
  uploadDate: Date;
  lastUpdated: Date | null;
  coverUrl?: string;
  visibility?: 'public' | 'private';
  categories?: string[];
  tags?: string[];
  lastError?: ErrorEvent | null;
  readCount?: number;
  fileType?: string;
  fileName?: string;
  source?: string;
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | 'spell_check' | 'ready' | null;
  pipelineStats?: Record<string, number>;
  hasSummary?: boolean;
  // Book-level milestones (denormalized from pages for performance)
  ocrMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  chunkingMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  embeddingMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
  spellCheckMilestone?: 'idle' | 'in_progress' | 'complete' | 'partial_failure' | 'failed';
}

export interface PaginatedBooks {
  books: Book[];
  total: number;
  totalReady: number;
  page: number;
  pageSize: number;
}

export interface Message {
  role: 'user' | 'model';
  text: string;
  characterId?: string;
}
