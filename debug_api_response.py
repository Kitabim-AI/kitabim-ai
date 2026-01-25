import requests
import json

url = "http://localhost:8000/api/books?page=1&pageSize=10&sortBy=lastUpdated&order=-1"
try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print("Keys in response:", data.keys())
    if "books" in data:
        books = data["books"]
        print(f"Number of books: {len(books)}")
        if len(books) > 0:
            first_book = books[0]
            print("First book keys:", first_book.keys())
            print("First book ID:", first_book.get("id"))
            print("First book Title:", first_book.get("title"))
            # Print full first book to check for anomalies
            print(json.dumps(first_book, indent=2, ensure_ascii=False)[:500] + "...")
except Exception as e:
    print(f"Error: {e}")
