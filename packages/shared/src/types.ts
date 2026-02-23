
export interface ExtractionResult {
  pageNumber: number;
  text?: string;
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
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
  status: 'uploading' | 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'ready' | 'error';
  uploadDate: Date;
  lastUpdated: Date | null;
  coverUrl?: string;
  visibility?: 'public' | 'private';
  processingStep?: 'ocr' | 'rag';
  categories?: string[];
  lastError?: ErrorEvent | null;
  ocrDoneCount?: number;
  errorCount?: number;
  processingLockExpiresAt?: Date | string | null;
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
}
