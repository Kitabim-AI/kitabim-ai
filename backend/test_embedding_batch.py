import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

texts = ["Hello", "World"]
print("Testing batch embedding...")
try:
    result = genai.embed_content(
        model="models/embedding-001",
        content=texts,
        task_type="retrieval_document"
    )
    print(f"Result keys: {result.keys()}")
    print(f"Length of embedding: {len(result['embedding'])}")
    print(f"Type of first item: {type(result['embedding'][0])}")
except Exception as e:
    print(f"Error: {e}")
