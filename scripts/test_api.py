
import requests
import json

response = requests.get("http://localhost:8000/api/books?pageSize=5")
if response.ok:
    data = response.json()
    books = data.get("books", [])
    for b in books:
        print(f"Book ID: {b.get('id')}, Title: {b.get('title')}, Pages type: {type(b.get('pages'))}, Pages exists: {'pages' in b}")
        if 'pages' in b and b['pages'] is not None:
             print(f"  Pages len: {len(b['pages'])}")
else:
    print(f"Error: {response.status_code}")
