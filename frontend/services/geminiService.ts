
import { GoogleGenAI } from "@google/genai";

const getAIClient = () => {
  const apiKey = process.env.API_KEY;
  if (!apiKey) throw new Error("API Key is missing");
  return new GoogleGenAI({ apiKey });
};

export const extractUyghurText = async (base64Image: string): Promise<string> => {
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

  const response = await ai.models.generateContent({
    model: 'gemini-3-flash-preview',
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
};

const getRelevantContext = (question: string, content: string, maxChars: number = 8000): string => {
  const keywords = question.toLowerCase().split(' ').filter(w => w.length > 3);
  if (keywords.length === 0 || content.length <= maxChars) return content.substring(0, maxChars);

  const paragraphs = content.split('\n\n');
  const scoredParagraphs = paragraphs.map(p => {
    let score = 0;
    keywords.forEach(k => { if (p.toLowerCase().includes(k)) score++; });
    return { text: p, score };
  });

  return scoredParagraphs
    .sort((a, b) => b.score - a.score)
    .slice(0, 8)
    .map(p => p.text)
    .join('\n\n')
    .substring(0, maxChars);
};

export const chatWithBook = async (question: string, bookContent: string, history: { role: string, text: string }[]): Promise<string> => {
  const ai = getAIClient();
  const relevantContext = getRelevantContext(question, bookContent);

  const systemInstruction = `You are Kitabim AI, a professional academic assistant specializing in Uyghur literature and documents.
  Your goal is to provide high-precision answers based on the provided text context.
  
  Context Content:
  ---
  ${relevantContext}
  ---
  
  Instructions:
  1. Base your answer strictly on the provided context.
  2. If the answer is not in the context, politely state that in Uyghur.
  3. Respond in professional, academic Uyghur.
  4. Ensure your output is correctly formatted for Right-to-Left (RTL) display.`;

  const chat = ai.chats.create({
    model: 'gemini-3-pro-preview',
    config: {
      systemInstruction,
      temperature: 0.3,
    }
  });

  const response = await chat.sendMessage({ message: question });
  return response.text || "ئەپسۇس، جاۋاب تاپالمىدىم.";
};
