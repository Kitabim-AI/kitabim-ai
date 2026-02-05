
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DATABASE", "kitabim_ai_db")

def migrate():
    client = MongoClient(MONGODB_URL)
    db = client[DB_NAME]
    
    print(f"Connected to {DB_NAME}. Cleaning up legacy fields from books...")
    
    result = db.books.update_many(
        {}, 
        {"$unset": {
            "previousContent": "", 
            "previousResults": "", 
            "previousVersionAt": ""
        }}
    )
    
    print(f"Migration complete. Modified {result.modified_count} books.")
    client.close()

if __name__ == "__main__":
    migrate()
