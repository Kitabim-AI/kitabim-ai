import numpy as np
from google.genai import types
from app.core.config import settings
from app.services import genai_client

async def get_embedding(text: str):
    try:
        if not text.strip():
            return None
        # Clean text slightly for embedding
        clean_text = text.replace("\n", " ")[:2000] 
        client = genai_client.get_genai_client()
        result = await client.aio.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=clean_text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            ),
        )
        return genai_client.extract_embedding_vector(result)
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_a = np.linalg.norm(v1)
    norm_b = np.linalg.norm(v2)
    return dot_product / (norm_a * norm_b)

async def get_generative_model():
    return genai_client.get_genai_client()
