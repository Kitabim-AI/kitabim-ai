
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
  content?: string;
  results: ExtractionResult[];
  status: 'uploading' | 'pending' | 'processing' | 'ready' | 'error';
  uploadDate: Date;
  lastUpdated: Date | null;
  coverUrl?: string;
  processingStep?: 'ocr' | 'rag';
  ocrProvider?: 'gemini' | 'local';
  previousContent?: string;
  previousResults?: ExtractionResult[];
  previousVersionAt?: Date | string | null;
  categories?: string[];
  tags?: string[];
  errors?: ErrorEvent[];
  lastError?: ErrorEvent | null;
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
