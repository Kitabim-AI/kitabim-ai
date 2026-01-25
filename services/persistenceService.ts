
import { Book } from '../types';

const API_BASE = '/api'; // This would point to your Python FastAPI server

export const PersistenceService = {
  /**
   * Checks if the book has already been processed by any user via the backend.
   */
  async findBookByHash(hash: string): Promise<Book | null> {
    try {
      const response = await fetch(`${API_BASE}/books/hash/${hash}`);
      if (!response.ok) return null;
      const data = await response.json();
      return { ...data, uploadDate: new Date(data.uploadDate) };
    } catch (error) {
      console.error("Backend unreachable, falling back to local check", error);
      return null;
    }
  },

  /**
   * Fetches a single book by its ID.
   */
  async getBook(bookId: string): Promise<Book | null> {
    try {
      const response = await fetch(`${API_BASE}/books/${bookId}`);
      if (!response.ok) return null;
      const data = await response.json();
      return { ...data, uploadDate: new Date(data.uploadDate) };
    } catch (error) {
      console.error("Failed to fetch book", error);
      return null;
    }
  },

  /**
   * Uploads a PDF file to the backend for processing.
   */
  async uploadFile(file: File): Promise<{ bookId: string; status: string }> {
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

    return response.json();
  },

  /**
   * Saves the extracted book to the shared Document DB.
   */
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

  /**
   * Fetches books available in the public library with pagination.
   */
  async getGlobalLibrary(page: number = 1, pageSize: number = 12, query: string = ''): Promise<{ books: Book[], total: number }> {
    try {
      const url = new URL(`${window.location.origin}${API_BASE}/books`);
      url.searchParams.append('page', page.toString());
      url.searchParams.append('pageSize', pageSize.toString());
      if (query) url.searchParams.append('q', query);

      const response = await fetch(url.toString());
      if (!response.ok) return { books: [], total: 0 };

      const data = await response.json();
      const books = (data.books || []).map((b: any) => ({
        ...b,
        uploadDate: new Date(b.uploadDate),
        lastUpdated: b.lastUpdated ? new Date(b.lastUpdated) : undefined
      }));

      return { books, total: data.total || 0 };
    } catch (error) {
      console.error("Failed to fetch library", error);
      return { books: [], total: 0 };
    }
  },

  /**
   * Updates an existing book in the shared Document DB.
   */
  async updateBook(bookId: string, updates: Partial<Book>): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/books/${bookId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (!response.ok) throw new Error("Failed to update book");
    } catch (error) {
      console.error("Failed to update book", error);
    }
  },

  /**
   * Interacts with the backend chat API for RAG-based questions.
   */
  async chatWithBook(bookId: string, question: string, currentPage?: number): Promise<string> {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookId, question, currentPage }),
    });

    if (!response.ok) throw new Error("Chat request failed");
    const data = await response.json();
    return data.answer;
  },

  /**
   * Deletes a book from the shared Document DB.
   */
  async deleteBook(bookId: string): Promise<void> {
    try {
      await fetch(`${API_BASE}/books/${bookId}`, {
        method: 'DELETE',
      });
    } catch (error) {
      console.error("Failed to delete book from backend", error);
    }
  }
};
