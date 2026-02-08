import re
import unicodedata

def normalize_token(token: str) -> str:
    if not token:
        return ""
    normalized = unicodedata.normalize('NFKC', token)
    # The current regex that seems problematic
    normalized = re.sub(r'[^\w\u0600-\u06FF]', '', normalized)
    return normalized.strip()

test_tokens = [
    "ئېستېتىكىلىق،",
    "1940،",
    "قىزا،",
    "كتاب؟",
    "«سۆز»"
]

for t in test_tokens:
    print(f"Original: '{t}' -> Normalized: '{normalize_token(t)}'")
