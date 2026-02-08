
export interface ExtractionResult {
  pageNumber: number;
  text?: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
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
  status: 'uploading' | 'pending' | 'processing' | 'ready' | 'error';
  uploadDate: Date;
  lastUpdated: Date | null;
  coverUrl?: string;
  processingStep?: 'ocr' | 'rag';
  categories?: string[];
  tags?: string[];
  errors?: ErrorEvent[];
  lastError?: ErrorEvent | null;
  completedCount?: number;
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

export interface OcrCandidate {
  token: string;
  frequency: number;
  bookSpan: number;
  confidence: number;
  distance: number;
}

export interface OcrSuspect {
  token: string;
  frequency: number;
  bookSpan: number;
  candidates: OcrCandidate[];
  status?: string;
  lastSeenAt?: string;
}

export interface OcrRegistryStats {
  total_tokens: number;
  verified_tokens: number;
  suspect_tokens: number;
  corrected_tokens: number;
  health_score: number;
}

export interface OcrContext {
  bookTitle: string;
  bookId: string;
  volume?: number | null;
  pageNumber: number;
  snippet: string;
  matchedToken?: string;
}
