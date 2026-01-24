
export interface ExtractionResult {
  pageNumber: number;
  text: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
}

export interface Book {
  id: string;
  contentHash: string;
  title: string;
  author: string;
  totalPages: number;
  content: string;
  results: ExtractionResult[];
  status: 'uploading' | 'processing' | 'ready' | 'error';
  uploadDate: Date;
}

export interface Message {
  role: 'user' | 'model';
  text: string;
}
