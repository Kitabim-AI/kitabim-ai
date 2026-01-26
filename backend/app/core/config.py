import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Kitabim.AI"
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL_NAME: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    GEMINI_CATEGORIZATION_MODEL: str = os.getenv("GEMINI_CATEGORIZATION_MODEL", "gemini-1.5-flash")
    
    # Database
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME: str = "kitabim_ai_db"
    
    # Directories
    UPLOADS_DIR: str = "uploads"
    COVERS_DIR: str = "covers"
    
    # Parallel Processing
    MAX_PARALLEL_PAGES: int = int(os.getenv("MAX_PARALLEL_PAGES", "1"))

settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.COVERS_DIR, exist_ok=True)
