import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Listing models with embedding capability...")
try:
    for m in client.models.list():
        methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
        if "embedContent" in methods or "embed_content" in methods:
            print(f"{m.name} - {methods}")
except Exception as e:
    print(f"Error: {e}")
