
import { authFetch } from './authService';

const API_BASE = '/api';

export const extractUyghurText = async (base64Image: string, retries = 5): Promise<string> => {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const response = await authFetch(`${API_BASE}/ai/ocr/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageBase64: base64Image })
      });
      if (response.status === 403) {
        throw new Error('Permission denied: Editor access required for OCR');
      }
      if (!response.ok) throw new Error(`OCR request failed: ${response.status}`);
      const data = await response.json();
      return data.text || '';
    } catch (error: any) {
      const isOverloaded = error?.message?.includes('503') || error?.message?.includes('overloaded') || error?.message?.includes('429');
      if (isOverloaded && attempt < retries - 1) {
        // More aggressive backoff for parallel processing: 2s, 4s, 8s, 16s...
        const waitTime = Math.pow(2, attempt + 1) * 1000 + Math.random() * 2000;
        console.warn(`Gemini API busy (503/429). Retrying in ${Math.round(waitTime)}ms... (Attempt ${attempt + 1}/${retries})`);
        await new Promise(res => setTimeout(res, waitTime));
        continue;
      }
      throw error;
    }
  }
  return '';
};

export const chatWithBook = async (
  question: string, 
  bookId: string, 
  currentPage?: number, 
  history: { role: string, text: string }[] = [],
  onUsageUpdate?: (usage: any) => void
): Promise<string> => {
  try {
    const response = await authFetch(`${API_BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookId, question, currentPage, history })
    });

    if (response.status === 401) {
      return "سوئالغا جاۋاب بېرىش ئۈچۈن تىزىملىتىڭ.";
    }
    if (response.status === 403) {
      return "بۇ ئىقتىدارنى ئىشلىتىشكە ھوقۇقىڭىز يوق.";
    }
    if (response.status === 429) {
      try {
        const errorData = await response.json();
        return errorData.detail || "كەچۈرۈڭ، سېستىما ئالدىراش ياكى كۈندىلىك چەكلىمىڭىز توشتى.";
      } catch (e) {
        return "كەچۈرۈڭ، سېستىما ئالدىراش ياكى كۈندىلىك چەكلىمىڭىز توشتى.";
      }
    }
    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      console.error(`Chat API error (${response.status}):`, errorText);
      return "كەچۈرۈڭ، سېستىما خاتالىقى كۆرۈلدى (500).";
    }
    const data = await response.json();
    if (onUsageUpdate && data.usage) {
      onUsageUpdate(data.usage);
    }
    return data.answer;
  } catch (err) {
    console.error("Chat Error:", err);
    return "ئەپسۇس، ئۇلىنىش خاتالىقى كۆرۈلدى. توردىن ئۈزۈلۈپ قالغان بولۇشىڭىز مۇمكىن.";
  }
};

export const chatWithBookStream = async (
  question: string,
  bookId: string,
  currentPage: number | undefined,
  history: { role: string; text: string }[],
  onChunk: (chunk: string) => void,
  onComplete: () => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
  onCorrection?: (correctedText: string) => void,
  onUsageUpdate?: (usage: any) => void
): Promise<void> => {
  try {
    const response = await authFetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookId, question, currentPage, history }),
      signal,
    });

    if (response.status === 401) {
      onError("سوئالغا جاۋاب بېرىش ئۈچۈن تىزىملىتىڭ.");
      return;
    }
    if (response.status === 403) {
      onError("بۇ ئىقتىدارنى ئىشلىتىشكە ھوقۇقىڭىز يوق.");
      return;
    }
    if (response.status === 429) {
      onError("كەچۈرۈڭ، سېستىما ئالدىراش ياكى كۈندىلىك چەكلىمىڭىز توشتى.");
      return;
    }
    if (!response.ok) {
      onError("كەچۈرۈڭ، سېستىما خاتالىقى كۆرۈلدى (500).");
      return;
    }

    // Parse SSE stream
    const reader = response.body?.getReader();
    if (!reader) {
      onError("Stream not available");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (signal?.aborted) {
        await reader.cancel();
        return;
      }

      if (done) {
        break;
      }

      // Decode and add to buffer
      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE events (lines ending with \n\n)
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || ''; // Keep incomplete event in buffer

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));

            if (data.error) {
              onError(data.error);
              return;
            } else if (data.chunk) {
              onChunk(data.chunk);
            } else if (data.correction) {
              // Backend has sent a corrected version with fixed citations
              if (onCorrection) {
                onCorrection(data.correction);
              }
            } else if (data.done) {
              if (onUsageUpdate && data.usage) {
                onUsageUpdate(data.usage);
              }
              onComplete();
              return;
            }
          } catch (parseError) {
            console.error("Failed to parse SSE event:", line, parseError);
          }
        }
      }
    }

    onComplete();
  } catch (err) {
    console.error("Chat Stream Error:", err);
    onError("ئەپسۇس، ئۇلىنىش خاتالىقى كۆرۈلدى.");
  }
};

export const getChatUsage = async (): Promise<{ usage: number, limit: number | null, hasReachedLimit: boolean }> => {
  try {
    const response = await authFetch(`${API_BASE}/chat/usage`);
    if (!response.ok) return { usage: 0, limit: null, hasReachedLimit: false };
    return await response.json();
  } catch (err) {
    console.error("Chat Usage Error:", err);
    return { usage: 0, limit: null, hasReachedLimit: false };
  }
};
