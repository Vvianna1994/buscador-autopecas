"""Extração convencional (sem IA) dos dados de anúncios a partir do HTML.

Ordem de preferência das fontes de dados:
1. JSON-LD schema.org (Product / Offer / ItemList)
2. Microdados schema.org (itemprop)
3. Meta tags (Open Graph / product:*)
4. Tabela de especificações e heurísticas (h1, elementos de preço)
Campos não encontrados ficam vazios. Nada é inventado.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from . import brands, codes

PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2})?)")

SPEC_BRAND = ("marca", "fabricante", "brand", "manufacturer", "marca da peça", "marca da peca")
SPEC_CODE = ("código do fabricante", "codigo do fabricante", "cód. fabricante", "cod. fabricante",
             "código da peça", "codigo da peca", "referência", "referencia", "part number", "mpn",
             "número de peça", "numero de peca", "código", "codigo", "ref", "ref.", "modelo")
SPEC_OEM = ("código original", "codigo original", "oem", "número original", "numero original",
            "código oem", "codigo oem", "número oem", "numero oem")
SPEC_COND = ("condição", "condicao", "estado", "condition")


@dataclass
class Listing:
    url: str
    domain: str
    store: str = ""
    seller: str = ""
    title: str = ""
    brand: str = ""
    announced_code: str = ""
    oem_code: str = ""
    sku: str = ""
    mpn: str = ""
    description: str = ""
    price: float | None = None
    currency: str = "BRL"
    condition: str = ""          # novo | usado | recondicionado | "" (não informado)
    image: str = ""
    availability: str = ""
    data_source: str = ""        # jsonld | microdata | meta | heuristica
    match: str = "none"          # exact | mentions | none
    match_where: str = ""
    spec_codes: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PageData:
    url: str
    domain: str
    title: str
    text: str
    listings: list[Listing]
    soup: BeautifulSoup | None = None
    product_like: bool = False


# ---------------- utilidades ----------------

def parse_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = str(value).strip().replace("R$", "").replace("\xa0", " ").strip()
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    elif re.search(r"\.\d{3}$", s) and s.count(".") >= 1 and not re.search(r"\.\d{1,2}$", s):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def _clean(s) -> str:
    if s is None:
        return ""
    if isinstance(s, dict):
        s = s.get("name") or s.get("@id") or ""
    if isinstance(s, list):
        s = s[0] if s else ""
        return _clean(s)
    return re.sub(r"\s+", " ", str(s)).strip()


def _image(v, base: str) -> str:
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl") or ""
    v = _clean(v)
    return urljoin(base, v) if v else ""


def _condition(v: str) -> str:
    f = brands.fold(v)
    if not f:
        return ""
    if "refurb" in f or "recondicion" in f or "remanufat" in f:
        return "recondicionado"
    if "used" in f or "usad" in f or "seminov" in f:
        return "usado"
    if "new" in f or "novo" in f or "nova" in f:
        return "novo"
    return ""


def _types(node: dict) -> set[str]:
    t = node.get("@type", "")
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


# ---------------- JSON-LD ----------------

def _jsonld_nodes(soup: BeautifulSoup) -> list[dict]:
    out: list[dict] = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            out.append(n)
            for k in ("@graph", "mainEntity", "itemListElement", "item"):
                if k in n:
                    walk(n[k])

    for tag in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        raw = tag.string or tag.get_text() or ""
        try:
            walk(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            # alguns sites colocam vários objetos ou vírgulas sobrando; tenta limpar o básico
            try:
                walk(json.loads(re.sub(r",\s*([}\]])", r"\1", raw.strip())))
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def _from_jsonld_product(p: dict, base_url: str) -> dict:
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        priced = [o for o in offers if isinstance(o, dict) and (o.get("price") or o.get("lowPrice"))]
        offers = min(priced, key=lambda o: parse_price(o.get("price") or o.get("lowPrice")) or 9e9) \
            if priced else (offers[0] if offers and isinstance(offers[0], dict) else {})
    if not isinstance(offers, dict):
        offers = {}
    price = offers.get("price") or offers.get("lowPrice")
    if price is None and isinstance(offers.get("priceSpecification"), dict):
        price = offers["priceSpecification"].get("price")
    return {
        "title": _clean(p.get("name")),
        "brand": _clean(p.get("brand") or p.get("manufacturer")),
        "sku": _clean(p.get("sku")),
        "mpn": _clean(p.get("mpn") or p.get("productID")),
        "description": _clean(p.get("description"))[:600],
        "image": _image(p.get("image"), base_url),
        "price": parse_price(price),
        "currency": _clean(offers.get("priceCurrency")) or "BRL",
        "condition": _condition(_clean(offers.get("itemCondition") or p.get("itemCondition"))),
        "seller": _clean(offers.get("seller")),
        "availability": _clean(offers.get("availability")).rsplit("/", 1)[-1],
        "url": urljoin(base_url, _clean(p.get("url") or offers.get("url"))) if (p.get("url") or offers.get("url")) else "",
    }


# ---------------- microdados / meta / especificações ----------------

def _microdata(soup: BeautifulSoup, base_url: str) -> dict | None:
    scope = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
    if not scope:
        return None

    def prop(name):
        el = scope.find(attrs={"itemprop": name})
        if not el:
            return ""
        return el.get("content") or el.get("src") or el.get("href") or el.get_text(" ", strip=True)

    brand_el = scope.find(attrs={"itemprop": "brand"})
    brand = ""
    if brand_el:
        inner = brand_el.find(attrs={"itemprop": "name"})
        brand = (inner.get("content") or inner.get_text(" ", strip=True)) if inner else \
            (brand_el.get("content") or brand_el.get_text(" ", strip=True))
    return {
        "title": _clean(prop("name")), "brand": _clean(brand), "sku": _clean(prop("sku")),
        "mpn": _clean(prop("mpn")), "description": _clean(prop("description"))[:600],
        "image": _image(prop("image"), base_url), "price": parse_price(prop("price") or prop("lowPrice")),
        "currency": _clean(prop("priceCurrency")) or "BRL",
        "condition": _condition(_clean(prop("itemCondition"))), "availability": "",
        "seller": "", "url": "",
    }


def _meta(soup: BeautifulSoup, name: str) -> str:
    el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
    return _clean(el.get("content")) if el and el.get("content") else ""


def spec_pairs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Pares rótulo/valor de tabelas de especificação, listas de definição e 'Rótulo: valor'."""
    pairs: list[tuple[str, str]] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) == 2:
            pairs.append((cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True)))
    for dl in soup.find_all("dl"):
        for dt in dl.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                pairs.append((dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)))
    for el in soup.find_all(["li", "p", "span", "div"], limit=4000):
        if el.find(["li", "p", "div", "table"]):
            continue
        t = el.get_text(" ", strip=True)
        if 3 < len(t) < 120 and ":" in t:
            k, v = t.split(":", 1)
            if 1 < len(k) < 40 and v.strip():
                pairs.append((k.strip(), v.strip()))
    return [(brands.fold(k).rstrip(" :"), v[:200]) for k, v in pairs]


def _spec_lookup(pairs, labels) -> list[str]:
    return [v for k, v in pairs if k in labels]


def _heuristic_price(soup: BeautifulSoup) -> float | None:
    for el in soup.find_all(attrs={"class": re.compile(r"price|preco|valor", re.I)}, limit=200):
        t = el.get_text(" ", strip=True)
        if not t or re.search(r"\d+\s*x\s*(de)?\s*R\$", t, re.I) or "parcela" in t.lower():
            continue
        m = PRICE_RE.search(t)
        if m:
            return parse_price(m.group(1))
    return None


# ---------------- página ----------------

def extract_page(html: str, url: str, code: str) -> PageData:
    soup = BeautifulSoup(html, "lxml")
    domain = urlsplit(url).netloc.lower().removeprefix("www.")
    site_name = _meta(soup, "og:site_name") or domain
    page_title = _clean(soup.title.string if soup.title else "")
    jsonld = _jsonld_nodes(soup)
    products = [n for n in jsonld if "product" in _types(n) or "productgroup" in _types(n)]
    # texto visível (sem scripts) para procurar códigos e referências
    text_soup = BeautifulSoup(html, "lxml")
    for t in text_soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        t.decompose()
    text = re.sub(r"\s+", " ", text_soup.get_text(" ", strip=True))
    pairs = spec_pairs(text_soup)

    listings: list[Listing] = []
    if len(products) > 1:
        # página com vários produtos (busca interna, categoria): só itens que citam o código
        for p in products:
            d = _from_jsonld_product(p, url)
            blob = " ".join([d["title"], d["sku"], d["mpn"], d["description"]])
            if not codes.contains(blob, code):
                continue
            listings.append(_build(d, d["url"] or url, domain, site_name, code, blob, [], "jsonld"))
        return PageData(url, domain, page_title, text, listings, text_soup, product_like=bool(products))

    d = None
    source = ""
    if products:
        d, source = _from_jsonld_product(products[0], url), "jsonld"
    md = _microdata(soup, url)
    if md:
        if d is None:
            d, source = md, "microdata"
        else:
            for k, v in md.items():
                if not d.get(k) and v:
                    d[k] = v
    meta = {
        "title": _meta(soup, "og:title"), "image": _image(_meta(soup, "og:image"), url),
        "price": parse_price(_meta(soup, "product:price:amount") or _meta(soup, "og:price:amount")),
        "brand": _meta(soup, "product:brand"), "condition": _condition(_meta(soup, "product:condition")),
        "currency": _meta(soup, "product:price:currency") or _meta(soup, "og:price:currency"),
        "description": _meta(soup, "og:description") or _meta(soup, "description"),
    }
    product_like = bool(d) or bool(meta["price"]) or _meta(soup, "og:type").lower() == "product"
    if d is None:
        d = {"title": "", "brand": "", "sku": "", "mpn": "", "description": "", "image": "", "price": None,
             "currency": "BRL", "condition": "", "seller": "", "availability": "", "url": ""}
        source = "meta" if meta["price"] else "heuristica"
    for k, v in meta.items():
        if not d.get(k) and v:
            d[k] = v
    d["description"] = (d.get("description") or "")[:600]

    # complementos pela tabela de especificações
    if not d["brand"]:
        b = _spec_lookup(pairs, SPEC_BRAND)
        d["brand"] = b[0] if b else ""
    if not d["condition"]:
        c = _spec_lookup(pairs, SPEC_COND)
        d["condition"] = _condition(c[0]) if c else ""
    if not d["title"]:
        h1 = text_soup.find("h1")
        d["title"] = _clean(h1.get_text(" ", strip=True)) if h1 else ""
    if d["price"] is None and product_like is False:
        hp = _heuristic_price(soup)
        if hp:
            d["price"] = hp
            product_like = True
    elif d["price"] is None:
        d["price"] = _heuristic_price(soup)

    spec_codes = [v for v in _spec_lookup(pairs, SPEC_CODE) if codes.looks_like_part_code(v)]
    oem = [v for v in _spec_lookup(pairs, SPEC_OEM) if codes.looks_like_part_code(v)]
    if oem:
        d["oem_code"] = oem[0]
    if not d["title"] and not d["price"]:
        return PageData(url, domain, page_title, text, [], text_soup, product_like=False)
    listing = _build(d, url, domain, site_name, code, text, spec_codes, source)
    if not product_like and listing.price is None:
        # página informativa (fórum, catálogo, PDF convertido): serve para referências, não é anúncio
        return PageData(url, domain, page_title, text, [], text_soup, product_like=False)
    return PageData(url, domain, page_title, text, [listing], text_soup, product_like=True)


def _build(d: dict, url: str, domain: str, site_name: str, code: str, page_text: str,
           spec_codes: list[str], source: str) -> Listing:
    li = Listing(url=url, domain=domain, store=site_name, seller=d.get("seller") or "",
                 title=d.get("title") or "", brand=d.get("brand") or "", sku=d.get("sku") or "",
                 mpn=d.get("mpn") or "", description=d.get("description") or "", price=d.get("price"),
                 currency=(d.get("currency") or "BRL").upper(), condition=d.get("condition") or "",
                 image=d.get("image") or "", availability=d.get("availability") or "",
                 oem_code=d.get("oem_code") or "", data_source=source, spec_codes=spec_codes)
    classify_code(li, code, page_text)
    li.missing = [name for name, val in (("preço", li.price), ("nome", li.title), ("fabricante", li.brand),
                                         ("foto", li.image), ("condição", li.condition)) if not val]
    return li


def classify_code(li: Listing, code: str, page_text: str) -> None:
    """Define o código anunciado e se o anúncio é do código pesquisado ou apenas o cita."""
    own_codes = [c for c in (li.mpn, *li.spec_codes) if c and codes.looks_like_part_code(c)]
    sku_ok = li.sku if li.sku and codes.looks_like_part_code(li.sku) and not li.sku.isdigit() else ""
    if any(codes.same(c, code) for c in (*own_codes, li.sku)):
        li.announced_code, li.match, li.match_where = code, "exact", "código do produto"
        return
    other = next((c for c in own_codes if not codes.contains(c, code)), "") or sku_ok
    aftermarket = bool(li.brand) and not brands.is_automaker(li.brand)
    if codes.contains(li.title, code):
        if other and aftermarket:
            li.announced_code, li.match, li.match_where = other, "mentions", "título"
        else:
            li.announced_code, li.match, li.match_where = code, "exact", "título"
        return
    if codes.contains(li.description, code) or codes.contains(page_text, code):
        li.announced_code = other
        li.match, li.match_where = "mentions", "descrição/página"
        if li.oem_code and codes.same(li.oem_code, code):
            li.match_where = "código original informado"
        return
    li.announced_code = other
    li.match = "none"
