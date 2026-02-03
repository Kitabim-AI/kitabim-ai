
import { Book, PaginatedBooks } from '@shared/types';

const API_BASE = '/api';

export const PersistenceService = {
  async findBookByHash(hash: string): Promise<Book | null> {
    try {
      const response = await fetch(`${API_BASE}/books/hash/${hash}`);
      if (!response.ok) return null;
      const data = await response.json();
      return { ...data, uploadDate: new Date(data.uploadDate) };
    } catch (error) {
      console.error("Backend unreachable", error);
      return null;
    }
  },

  async saveBookGlobally(book: Book): Promise<void> {
    const response = await fetch(`${API_BASE}/books`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(book),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to save book: ${response.status} ${errorText}`);
    }
  },

  async getGlobalLibrary(page: number = 1, pageSize: number = 10, q?: string, sortBy: string = 'title', order: number = 1, groupByWork: boolean = false): Promise<PaginatedBooks> {
    try {
      let url = `${API_BASE}/books/?page=${page}&pageSize=${pageSize}&sortBy=${sortBy}&order=${order}`;
      if (q) url += `&q=${encodeURIComponent(q)}`;
      if (groupByWork) url += `&groupByWork=true`;

      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch");
      const data = await response.json();
      return {
        ...data,
        books: data.books.map((b: any) => ({
          ...b,
          uploadDate: new Date(b.uploadDate),
          lastUpdated: b.lastUpdated ? new Date(b.lastUpdated) : null,
          previousVersionAt: b.previousVersionAt ? new Date(b.previousVersionAt) : null
        }))
      };
    } catch (error) {
      console.error("Failed to fetch library", error);
      return { books: [], total: 0, totalReady: 0, page, pageSize };
    }
  },

  async getBookById(id: string): Promise<Book | null> {
    try {
      const response = await fetch(`${API_BASE}/books/${id}`);
      if (!response.ok) throw new Error("Failed to fetch book");
      const b = await response.json();
      return {
        ...b,
        uploadDate: new Date(b.uploadDate),
        lastUpdated: b.lastUpdated ? new Date(b.lastUpdated) : null,
        previousVersionAt: b.previousVersionAt ? new Date(b.previousVersionAt) : null
      };
    } catch (error) {
      console.error("Failed to fetch book by id", error);
      return null;
    }
  },

  async deleteBook(bookId: string): Promise<void> {
    try {
      await fetch(`${API_BASE}/books/${bookId}`, {
        method: 'DELETE',
      });
    } catch (error) {
      console.error("Failed to delete book from backend", error);
    }
  },

  /**
   * Uploads a PDF to the backend for server-side processing.
   */
  async uploadPdf(file: File): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/books/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return data.bookId;
  },

  async reprocessBook(bookId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/books/${bookId}/reprocess`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error("Failed to start reprocessing");
    }
  },

  async retryFailedOcr(bookId: string, provider?: 'local' | 'gemini'): Promise<void> {
    const response = await fetch(`${API_BASE}/books/${bookId}/retry-ocr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(provider ? { provider } : {}),
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to retry OCR: ${response.status} ${errorText}`);
    }
  },

  async startOcr(bookId: string, provider: 'local' | 'gemini'): Promise<void> {
    const response = await fetch(`${API_BASE}/books/${bookId}/start-ocr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider })
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to start OCR: ${response.status} ${errorText}`);
    }
  },

  async revertBook(bookId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/books/${bookId}/revert`, {
      method: 'POST',
    });
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to revert book: ${response.status} ${errorText}`);
    }
  },

  async updateBookMetadata(book_id: string, updates: Partial<Book>): Promise<void> {
    const response = await fetch(`${API_BASE}/books/${book_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    });

    if (!response.ok) {
      throw new Error("Failed to update book metadata");
    }
  },

  async updateBookTags(bookId: string, tags: string[]): Promise<void> {
    // Legacy support or specific tag update
    return this.updateBookMetadata(bookId, { tags });
  }
};
