import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Listing models...")
try:
    for m in client.models.list():
        methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
        if "generateContent" in methods or "generate_content" in methods:
            print(m.name)
except Exception as e:
    print(f"Error: {e}")
