import re


def normalize_markdown(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def strip_markdown(text: str) -> str:
    if not text:
        return ""
    stripped = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = re.sub(r"^#{1,6}\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*>+\s?", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*[-*+]\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*\d+[.)]\s+", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^(-{3,}|\*{3,}|_{3,})\s*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"(`+)([^`]+)\1", r"\2", stripped)
    stripped = re.sub(r"(\*\*|__)(.*?)\1", r"\2", stripped)
    stripped = re.sub(r"(\*|_)(.*?)\1", r"\2", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.strip()
