
export interface ExtractionResult {
  pageNumber: number;
  text: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
}

export interface Book {
  id: string;
  contentHash: string; // SHA-256 fingerprint of the file
  title: string;
  author: string;
  totalPages: number;
  content: string; // Full extracted text
  results: ExtractionResult[];
  status: 'uploading' | 'processing' | 'ready' | 'error';
  uploadDate: Date;
}

export interface Message {
  role: 'user' | 'model';
  text: string;
}
