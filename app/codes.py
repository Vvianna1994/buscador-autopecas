"""Códigos de peças: validação da entrada, normalização, variações de formatação e
localização do código em textos (tolerando hífens, pontos e espaços)."""

from __future__ import annotations

import re

SEPARATORS = r"[\s.\-/_]"
_VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-/_]{2,39}$")


class InvalidCode(ValueError):
    pass


def normalize(code: str) -> str:
    """'88162-0K021' -> '881620K021'"""
    return re.sub(SEPARATORS, "", code or "").upper()


def validate(raw: str) -> str:
    """Aceita somente códigos de peça. Recusa textos descritivos (nome de peça, placa etc.)."""
    code = re.sub(r"\s+", " ", (raw or "").strip())
    if not _VALID.match(code):
        raise InvalidCode("Informe apenas o código da peça (letras, números, '-', '.', '/').")
    norm = normalize(code)
    if len(norm) < 3:
        raise InvalidCode("Código muito curto.")
    if not re.search(r"\d", norm):
        raise InvalidCode("O código deve conter números. A pesquisa por nome não é aceita.")
    # Palavras longas só de letras indicam texto descritivo ("filtro de oleo 1234")
    words = code.split(" ")
    if any(len(w) >= 4 and w.isalpha() for w in words):
        raise InvalidCode("A pesquisa aceita somente o código da peça, sem descrição.")
    return code


def variations(code: str) -> list[str]:
    """Variações de formatação úteis para a pesquisa no Google."""
    norm = normalize(code)
    out = [code.upper()]
    if norm not in out:
        out.append(norm)
    # Códigos de 10 caracteres das montadoras japonesas costumam ser escritos 5-5 (88162-0K021)
    if len(norm) == 10 and norm.isalnum() and code.upper() == norm:
        out.append(f"{norm[:5]}-{norm[5:]}")
    return out


def pattern(code: str) -> re.Pattern:
    """Regex que encontra o código com ou sem separadores e sem fazer parte de outro código."""
    norm = normalize(code)
    body = f"{SEPARATORS}?".join(re.escape(ch) for ch in norm)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def contains(text: str, code: str) -> bool:
    return bool(text) and bool(pattern(code).search(text))


def same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and normalize(a) == normalize(b)


def looks_like_part_code(s: str) -> bool:
    """Heurística: 4-25 caracteres, com dígito, sem ser só um número pequeno ou um preço."""
    s = (s or "").strip()
    n = normalize(s)
    if not (4 <= len(n) <= 25) or not re.search(r"\d", n) or not n.isalnum():
        return False
    if re.fullmatch(r"\d{1,5}", n):  # números curtos costumam ser quantidade, ano etc.
        return False
    if re.fullmatch(r"(19|20)\d\d", n):
        return False
    return True
