import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from app.services import genai_client

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

texts = ["Hello", "World"]
print("Testing batch embedding...")
try:
    result = client.models.embed_content(
        model="models/embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    embeddings = genai_client.extract_embeddings_list(result)
    print(f"Embedding batch size: {len(embeddings)}")
    if embeddings:
        print(f"Length of first embedding: {len(embeddings[0])}")
        print(f"Type of first item: {type(embeddings[0])}")
except Exception as e:
    print(f"Error: {e}")
