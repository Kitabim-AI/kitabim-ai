
import requests
import json

response = requests.get("http://localhost:8000/api/books/cea06b495380")
if response.ok:
    b = response.json()
    print(f"Book ID: {b.get('id')}, Title: {b.get('title')}")
    print(f"  Pages exists: {'pages' in b}, Results exists: {'results' in b}")
    if 'pages' in b: print(f"  Pages count: {len(b['pages'])}")
    if 'results' in b: print(f"  Results count: {len(b['results'])}")
else:
    print(f"Error: {response.status_code}")
