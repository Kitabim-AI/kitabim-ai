
import requests
import json

response = requests.get("http://localhost:8000/api/books?pageSize=5")
if response.ok:
    data = response.json()
    books = data.get("books", [])
    for b in books:
        print(f"Book ID: {b.get('id')}, Title: {b.get('title')}")
        print(f"  Pages exists: {'pages' in b}, Results exists: {'results' in b}")
        if 'pages' in b: print(f"  Pages: {b['pages']}")
        if 'results' in b: print(f"  Results: {b['results']}")
else:
    print(f"Error: {response.status_code}")
