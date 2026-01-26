import google.generativeai as genai
import numpy as np
import asyncio
from app.core.config import settings

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

async def get_embedding(text: str):
    try:
        if not text.strip():
            return None
        # Clean text slightly for embedding
        clean_text = text.replace("\n", " ")[:2000] 
        result = await asyncio.to_thread(
            genai.embed_content,
            model="models/embedding-001",
            content=clean_text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_a = np.linalg.norm(v1)
    norm_b = np.linalg.norm(v2)
    return dot_product / (norm_a * norm_b)

async def get_generative_model():
    return genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
