import re
import unicodedata

def normalize_token_new(token: str) -> str:
    if not token:
        return ""
    normalized = unicodedata.normalize('NFKC', token)
    # Just use \W to remove non-word characters. 
    # In Python 3, \w matches characters in the 'Letter' category.
    # Arabic punctuation is NOT in the 'Letter' category.
    normalized = re.sub(r'[^\w]', '', normalized)
    return normalized.strip()

test_tokens = [
    "ئېستېتىكىلىق،",
    "1940،",
    "قىزا،",
    "كتاب؟",
    "«سۆز»",
    "word!",
    "123-456"
]

for t in test_tokens:
    print(f"Original: '{t}' -> Normalized: '{normalize_token_new(t)}'")
