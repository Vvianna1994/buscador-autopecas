"""Normalização de texto em português para comparar anúncios."""

import re
import unicodedata

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokens(text: str) -> list[str]:
    return [t.replace(",", ".") for t in _TOKEN_RE.findall(normalize(text))]


def stem(word: str) -> str:
    """Stemmer mínimo para plurais em português (pastilhas -> pastilha)."""
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("oes") or word.endswith("aes"):
        return word[:-3] + "ao"
    if word.endswith(("res", "zes", "les")) and len(word) > 5:
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def has_phrase(token_list: list[str], phrase: str) -> bool:
    return f" {phrase} " in f" {' '.join(token_list)} "
