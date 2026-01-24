
import { Book } from '../types';

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
    try {
      await fetch(`${API_BASE}/books`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(book),
      });
    } catch (error) {
      console.error("Failed to save book to backend", error);
    }
  },

  async getGlobalLibrary(): Promise<Book[]> {
    try {
      const response = await fetch(`${API_BASE}/books`);
      if (!response.ok) return [];
      const data = await response.json();
      return data.map((b: any) => ({ ...b, uploadDate: new Date(b.uploadDate) }));
    } catch (error) {
      console.error("Failed to fetch library", error);
      return [];
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
  }
};
