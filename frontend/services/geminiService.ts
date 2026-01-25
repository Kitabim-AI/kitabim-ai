
import { GoogleGenAI } from "@google/genai";

const getAIClient = () => {
  const apiKey = process.env.API_KEY;
  if (!apiKey) throw new Error("API Key is missing");
  return new GoogleGenAI({ apiKey });
};

const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));

export const extractUyghurText = async (base64Image: string, retries = 5): Promise<string> => {
  const ai = getAIClient();
  const prompt = `Extract all text from this image accurately. 
  The text is in the Uyghur language (Arabic script).
  Rules:
  1. Maintain the exact original layout and formatting.
  2. Use correct Uyghur Arabic Unicode characters.
  3. Ensure Right-to-Left (RTL) reading order is preserved.
  4. Preserve punctuation and paragraph structures.
  5. If there are tables or lists, represent them clearly.
  Output ONLY the extracted Uyghur text.`;

  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const response = await ai.models.generateContent({
        model: 'gemini-3-flash-preview', // Flash is cheapest/latest in this env
        contents: {
          parts: [
            { inlineData: { mimeType: 'image/jpeg', data: base64Image } },
            { text: prompt }
          ]
        },
        config: {
          temperature: 0.1,
          topP: 0.95,
          topK: 40
        }
      });

      return response.text || '';
    } catch (error: any) {
      const isOverloaded = error?.message?.includes('503') || error?.message?.includes('overloaded') || error?.message?.includes('429');
      if (isOverloaded && attempt < retries - 1) {
        // More aggressive backoff for parallel processing: 2s, 4s, 8s, 16s...
        const waitTime = Math.pow(2, attempt + 1) * 1000 + Math.random() * 2000;
        console.warn(`Gemini API busy (503/429). Retrying in ${Math.round(waitTime)}ms... (Attempt ${attempt + 1}/${retries})`);
        await sleep(waitTime);
        continue;
      }
      throw error;
    }
  }
  return '';
};

export const chatWithBook = async (question: string, bookId: string, currentPage?: number): Promise<string> => {
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookId, question, currentPage })
    });

    if (!response.ok) throw new Error("Chat request failed");
    const data = await response.json();
    return data.answer;
  } catch (err) {
    console.error("Chat Error:", err);
    return "ئەپسۇس، جاۋاب تاپالمىدىم.";
  }
};
