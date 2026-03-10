
import { Book, PaginatedBooks } from '@shared/types';
import { authFetch, getAuthHeaders } from './authService';

const API_BASE = '/api';

export const PersistenceService = {
  async getBookContent(id: string): Promise<string> {
    try {
      const response = await authFetch(`${API_BASE}/books/${id}/content`);
      if (!response.ok) throw new Error("Failed to fetch content");
      const data = await response.json();
      return data.content || "";
    } catch (error) {
      console.error("Failed to fetch book content:", error);
      return "";
    }
  },

  async findBookByHash(hash: string): Promise<Book | null> {
    try {
      const response = await authFetch(`${API_BASE}/books/hash/${hash}`);
      if (!response.ok) return null;
      const data = await response.json();
      return {
        ...data,
        pages: data.pages || [],
        uploadDate: new Date(data.uploadDate)
      };
    } catch (error) {
      console.error("Backend unreachable", error);
      return null;
    }
  },

  async saveBookGlobally(book: Book): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${book.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(book),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to save book: ${response.status} ${errorText}`);
    }
  },

  async getGlobalLibrary(page: number = 1, pageSize: number = 10, q?: string, sortBy: string = 'title', order: number = 1, groupByWork: boolean = false, category?: string): Promise<PaginatedBooks> {
    try {
      let url = `${API_BASE}/books/?page=${page}&pageSize=${pageSize}&sortBy=${sortBy}&order=${order}`;
      if (q && q.trim()) url += `&q=${encodeURIComponent(q.trim())}`;
      if (category && category.trim()) url += `&category=${encodeURIComponent(category.trim())}`;
      if (groupByWork) url += `&groupByWork=true`;

      const response = await authFetch(url);
      if (!response.ok) throw new Error("Failed to fetch");
      const data = await response.json();
      return {
        ...data,
        books: data.books.map((b: any) => ({
          ...b,
          pages: b.pages || [],
          uploadDate: new Date(b.uploadDate),
          lastUpdated: b.lastUpdated ? new Date(b.lastUpdated) : null,
        }))
      };
    } catch (error) {
      console.error("Failed to fetch library", error);
      return { books: [], total: 0, totalReady: 0, page, pageSize };
    }
  },

  async getBookById(id: string): Promise<Book | null> {
    try {
      const response = await authFetch(`${API_BASE}/books/${id}`);
      if (!response.ok) throw new Error("Failed to fetch book");
      const b = await response.json();
      return {
        ...b,
        pages: b.pages || [],
        uploadDate: new Date(b.uploadDate),
        lastUpdated: b.lastUpdated ? new Date(b.lastUpdated) : null,
      };
    } catch (error) {
      console.error("Failed to fetch book by id", error);
      return null;
    }
  },

  async getBookPages(id: string, skip: number, limit: number): Promise<any[]> {
    try {
      const response = await authFetch(`${API_BASE}/books/${id}/pages?skip=${skip}&limit=${limit}`);
      if (!response.ok) throw new Error("Failed to fetch pages");
      return await response.json();
    } catch (error) {
      console.error("Failed to fetch pages", error);
      return [];
    }
  },

  async getPage(bookId: string, pageNum: number): Promise<any | null> {
    try {
      const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}`);
      if (!response.ok) throw new Error("Failed to fetch page");
      return await response.json();
    } catch (error) {
      console.error("Failed to fetch page", error);
      return null;
    }
  },

  async deleteBook(bookId: string): Promise<void> {
    try {
      const response = await authFetch(`${API_BASE}/books/${bookId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        if (response.status === 403) {
          throw new Error("Permission denied: Admin access required");
        }
        throw new Error("Failed to delete book");
      }
    } catch (error) {
      console.error("Failed to delete book from backend", error);
      throw error;
    }
  },

  /**
   * Uploads a PDF to the backend for server-side processing.
   */
  async uploadPdf(file: File): Promise<{ bookId: string; status: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await authFetch(`${API_BASE}/books/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Editor access required");
      }
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return { bookId: data.bookId, status: data.status };
  },

  async downloadBook(bookId: string, fileName: string): Promise<void> {
    try {
      const response = await authFetch(`${API_BASE}/books/${bookId}/download`);
      if (!response.ok) {
        if (response.status === 401) throw new Error("Authentication required");
        if (response.status === 403) throw new Error("Permission denied");
        if (response.status === 404) throw new Error("File not found");
        throw new Error("Failed to download book");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("Download failed:", error);
      throw error;
    }
  },

  async triggerSpellCheck(bookId: string): Promise<{ queued: number }> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/spell-check/trigger`, {
      method: 'POST',
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to trigger spell check");
    }
    return response.json();
  },

  async reindexBook(bookId: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/reindex`, {
      method: 'POST',
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Editor access required");
      }
      throw new Error("Failed to start reindexing");
    }
  },

  async reprocessBook(bookId: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/reprocess`, {
      method: 'POST',
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Admin access required");
      }
      throw new Error("Failed to start re-OCR");
    }
  },

  async resetFailedPages(bookId: string): Promise<{ status: string; count: number }> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/reset-failed-pages`, {
      method: 'POST',
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Editor access required");
      }
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to reset failed pages");
    }
    return response.json();
  },

  async updatePage(bookId: string, pageNum: number, text: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!response.ok) {
      throw new Error("Failed to update page text");
    }
  },

  async resetPage(bookId: string, pageNum: number): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/reset`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error("Failed to reset page");
    }
  },

  async updateBookMetadata(book_id: string, updates: Partial<Book>): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${book_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    });

    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Editor access required");
      }
      throw new Error("Failed to update book metadata");
    }
  },

  async updateBookCover(bookId: string, file: File): Promise<{ coverUrl: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await authFetch(`${API_BASE}/books/${bookId}/cover`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Editor access required");
      }
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${errorText}`);
    }

    return response.json();
  },

  async updateBookTags(bookId: string, tags: string[]): Promise<void> {
    // Legacy support or specific tag update
    return this.updateBookMetadata(bookId, { tags });
  },

  async getSuggestions(q: string): Promise<any[]> {
    try {
      const response = await authFetch(`${API_BASE}/books/suggest?q=${encodeURIComponent(q)}`);
      if (!response.ok) return [];
      const data = await response.json();
      return data.suggestions || [];
    } catch (error) {
      console.error("Failed to fetch suggestions", error);
      return [];
    }
  },

  async getRandomProverb(keywords?: string | string[]): Promise<{ text: string; volume: number; pageNumber: number }> {
    try {
      let url = `${API_BASE}/books/random-proverb`;
      if (keywords) {
        const keywordParam = Array.isArray(keywords) ? keywords.join(',') : keywords;
        url += `?keyword=${encodeURIComponent(keywordParam)}`;
      }
      const response = await authFetch(url);
      if (!response.ok) throw new Error("Failed to fetch proverb");
      return await response.json();
    } catch (error) {
      console.error("Failed to fetch random proverb", error);
      return { text: "كىتاب — بىلىم بۇلىقى.", volume: 1, pageNumber: 1 };
    }
  },

  async getTopCategories(limit: number = 100, sort: string = 'count'): Promise<string[]> {
    try {
      const response = await authFetch(`${API_BASE}/books/top-categories?limit=${limit}&sort=${sort}`);
      if (!response.ok) throw new Error("Failed to fetch categories");
      const data = await response.json();
      return data.categories || [];
    } catch (error) {
      console.error("Failed to fetch categories", error);
      return [];
    }
  }
};
