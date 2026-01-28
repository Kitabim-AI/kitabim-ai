import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Settings:
    PROJECT_NAME: str = "Kitabim.AI"
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL_NAME: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    GEMINI_CATEGORIZATION_MODEL: str = os.getenv("GEMINI_CATEGORIZATION_MODEL", "gemini-3-flash-preview")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
    
    # Database
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME: str = "kitabim_ai_db"
    
    # Directories
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    UPLOADS_DIR: str = os.path.join(DATA_DIR, "uploads")
    COVERS_DIR: str = os.path.join(DATA_DIR, "covers")
    
    # Parallel Processing
    MAX_PARALLEL_PAGES: int = int(os.getenv("MAX_PARALLEL_PAGES", "1"))
    
    # OCR Settings
    OCR_PROVIDER: str = os.getenv("OCR_PROVIDER", "gemini").lower()
    LOCAL_OCR_URL: str = os.getenv("LOCAL_OCR_URL", "http://localhost:8001")

settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
os.makedirs(settings.COVERS_DIR, exist_ok=True)
