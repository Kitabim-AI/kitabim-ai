
const API_BASE = '/api';

export const extractUyghurText = async (base64Image: string, retries = 5): Promise<string> => {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const response = await fetch(`${API_BASE}/ai/ocr/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageBase64: base64Image })
      });
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

export const chatWithBook = async (question: string, bookId: string, currentPage?: number, history: { role: string, text: string }[] = []): Promise<string> => {
  try {
    const response = await fetch(`${API_BASE}/chat/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookId, question, currentPage, history })
    });

    if (!response.ok) throw new Error("Chat request failed");
    const data = await response.json();
    return data.answer;
  } catch (err) {
    console.error("Chat Error:", err);
    return "ئەپسۇس، جاۋاب تاپالمىدىم.";
  }
};
