from pymongo import MongoClient
import sys

try:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["kitabim_ai_db"]
    book_id = "70359ef50513"
    
    print(f"Checking book: {book_id}")
    book = db.books.find_one({"id": book_id}, {"id": 1, "title": 1})
    
    if book:
        print(f"FOUND: {book}")
    else:
        print("NOT FOUND")
        
    # Also check if there are ANY books to confirm DB connection
    count = db.books.count_documents({})
    print(f"Total books in DB: {count}")

except Exception as e:
    print(f"Error: {e}")
