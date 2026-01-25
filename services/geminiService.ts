
import { GoogleGenAI } from "@google/genai";

const getAIClient = () => {
  const apiKey = process.env.API_KEY;
  if (!apiKey) throw new Error("API Key is missing");
  return new GoogleGenAI({ apiKey });
};

/**
 * Strategy: Use Flash Lite for OCR. 
 * It is significantly cheaper than Pro or standard Flash while being excellent at vision/transcription.
 */
export const extractUyghurText = async (base64Image: string): Promise<string> => {
  const ai = getAIClient();

  const prompt = `Extract all Uyghur text from this image. 
  Rules: Maintain original formatting, use correct Uyghur Arabic script, ensure RTL order. 
  Output ONLY the extracted text.`;

  const response = await ai.models.generateContent({
    model: 'gemini-3-flash-preview', // Aligned with .env standard
    contents: {
      parts: [
        { inlineData: { mimeType: 'image/jpeg', data: base64Image } },
        { text: prompt }
      ]
    },
    config: { temperature: 0.1 }
  });

  return response.text || '';
};

/**
 * Strategy: Simple RAG (Retrieval Augmented Generation) snippet selection.
 * Instead of sending the WHOLE book (high token cost), we find chunks that 
 * contain keywords from the question.
 */
const getRelevantContext = (question: string, content: string, maxChars: number = 5000): string => {
  const keywords = question.toLowerCase().split(' ').filter(w => w.length > 3);
  if (keywords.length === 0 || content.length <= maxChars) return content.substring(0, maxChars);

  // Simple heuristic: find paragraphs containing most keywords
  const paragraphs = content.split('\n\n');
  const scoredParagraphs = paragraphs.map(p => {
    let score = 0;
    keywords.forEach(k => { if (p.toLowerCase().includes(k)) score++; });
    return { text: p, score };
  });

  return scoredParagraphs
    .sort((a, b) => b.score - a.score)
    .slice(0, 5) // Top 5 relevant paragraphs
    .map(p => p.text)
    .join('\n\n')
    .substring(0, maxChars);
};

export const chatWithBook = async (question: string, bookContent: string, history: { role: string, text: string }[]): Promise<string> => {
  const ai = getAIClient();

  // Minimize tokens by only sending relevant snippets
  const relevantContext = getRelevantContext(question, bookContent);

  const systemInstruction = `You are a helpful assistant for Uyghur documents. 
  Answer based ONLY on this context:
  ---
  ${relevantContext}
  ---
  Respond in Uyghur. Use RTL.`;

  const chat = ai.chats.create({
    model: 'gemini-3-flash-preview', // Latest in this environment
    config: {
      systemInstruction,
      temperature: 0.7,
    }
  });

  const response = await chat.sendMessage({ message: question });
  return response.text || "ئەپسۇس، جاۋاب تاپالمىدىم.";
};
