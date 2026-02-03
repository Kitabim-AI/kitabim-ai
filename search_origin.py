import fitz
import os

results = []
search_dir = '/data/uploads'
search_str = 'تەبىئىي جۇغراپىيىلىك شارائىتى'

for f in os.listdir(search_dir):
    if f.endswith('.pdf') and f != '260f1cc626b9.pdf':
        try:
            doc = fitz.open(os.path.join(search_dir, f))
            # Only check first 20 pages to be fast, it's a TOC page
            for i in range(min(20, len(doc))):
                if search_str in doc[i].get_text():
                    results.append(f"{f} (Page {i+1})")
                    break
            doc.close()
        except:
            pass

print(" | ".join(results))
