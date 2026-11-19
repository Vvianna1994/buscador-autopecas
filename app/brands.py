"""Listas de referência usadas pelo processamento convencional (sem IA):
montadoras, fabricantes de autopeças, domínios de catálogos técnicos e categorias."""

from __future__ import annotations

import re
import unicodedata


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def brand_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(name))


# Montadoras: marca do produto igual a uma montadora => peça original (genuína)
AUTOMAKERS = {
    "toyota", "volkswagen", "vw", "fiat", "chevrolet", "gm", "generalmotors", "ford", "honda",
    "hyundai", "renault", "nissan", "peugeot", "citroen", "jeep", "mitsubishi", "kia",
    "mercedesbenz", "mercedes", "bmw", "audi", "volvo", "subaru", "suzuki", "mazda", "lexus",
    "landrover", "jaguar", "chery", "caoacherry", "jac", "byd", "gwm", "ram", "dodge", "chrysler",
    "porsche", "mini", "lifan", "troller", "iveco", "scania", "motorcraft", "mopar",
    "acdelco", "motrio",
}
# Marcas de reposição de montadora: tratadas como originais/genuínas
GENUINE_ALIASES = {"motorcraft": "Ford", "mopar": "Stellantis", "acdelco": "GM", "motrio": "Renault"}

# Fabricantes de autopeças (reposição / sistemistas). Usado para reconhecer "MARCA CÓDIGO".
PART_MAKERS = [
    "Bosch", "Denso", "NGK", "Mahle", "Metal Leve", "Tecfil", "Fram", "Wega", "Mann", "Mann-Filter",
    "Cofap", "Monroe", "Nakata", "SKF", "Valeo", "Sachs", "ZF", "TRW", "Fras-le", "Fras le", "Cobreq",
    "Hipper Freios", "Syl", "Jurid", "Ferodo", "Akebono", "Brembo", "Vetor", "Delphi",
    "Magneti Marelli", "Marelli", "Gates", "Dayco", "Contitech", "Continental", "Sabó", "Sabo",
    "Corteco", "Eaton", "Schaeffler", "LuK", "INA", "FAG", "Hella", "Osram", "Philips", "Champion",
    "Brosol", "Kostal", "Visconde", "Urba", "Axios", "Viemar", "Perfect", "Febi", "Lemförder",
    "Lemforder", "Meyle", "KYB", "Kayaba", "Mobensani", "Behr", "Nissens", "Aisin", "Hengst",
    "Purflux", "Baldwin", "Donaldson", "Fleetguard", "Wix", "Vex", "Inpel", "Real Filtros",
    "Authomix", "Ampri", "Spaal", "Indisa", "MTE-Thomson", "MTE", "Thompson", "Nytron", "Kolbenschmidt",
    "KS", "Pierburg", "Hitachi", "Mitsuba", "Iskra", "Wahler", "Fremax", "Hipervarejo", "Seineca",
    "Japanparts", "Ashika", "Blue Print", "Mapco", "Sakura", "Vic", "Tokico", "Remsa", "Textar",
    "Pagid", "Ate", "Lonaflex", "Pastilhas Ecopads", "Willtec", "Diamond", "Riosulense", "Taranto",
    "Elring", "Victor Reinz", "Reinz", "Bucher", "Rolemar", "Timken", "NSK", "NTN", "Koyo", "IRB",
    "Original Japan", "Moura", "Heliar", "Zetta", "Fortluz", "Arteb", "Cibie", "Orgus", "Lumileds",
]
_MAKER_BY_KEY = {brand_key(b): b for b in PART_MAKERS}

# Domínios de fabricantes / catálogos eletrônicos considerados fontes técnicas.
CATALOG_DOMAINS = {
    "bosch.com.br", "boschaftermarket.com", "bosch-automotive-catalog.com", "catalogo.bosch.com.br",
    "denso.com", "densoautoparts.com", "ngkntk.com.br", "ngk.com.br", "mahle-aftermarket.com",
    "mahle.com", "catalogo.mahle.com.br", "tecfil.com.br", "fram.com.br", "wega.com.br",
    "mann-filter.com", "cofap.com.br", "nakata.com.br", "skf.com", "valeo.com", "zf.com",
    "aftermarket.zf.com", "trw.com.br", "fras-le.com", "fras-le.com.br", "cobreq.com.br",
    "syl.com.br", "brembo.com", "delphiautoparts.com", "magnetimarelli.com.br", "marelli.com",
    "gates.com", "dayco.com", "contitech.com.br", "sabo.com.br", "corteco.com", "schaeffler.com",
    "schaeffler.com.br", "hella.com", "osram.com.br", "champion.com.br", "kostal.com",
    "viemar.com.br", "febi.com", "kyb.com.br", "behrhellaservice.com", "nissens.com", "aisin.com",
    "hengst.com", "wixfilters.com", "tecdoc.net", "web.tecalliance.net", "partslink24.com",
    "catalogoeletronico.com.br", "catalogo-eletronico.com.br", "catalogodepecas.com.br",
    "mte-thomson.com.br", "fremax.com.br", "remsa.com", "textar.com", "pagid.com",
    "monroe.com.br", "sachs.com.br", "lonaflex.com.br", "vetor.com.br", "authomix.com.br",
}


def is_automaker(brand: str) -> bool:
    k = brand_key(brand)
    return k in AUTOMAKERS or k in GENUINE_ALIASES


def canonical_maker(token: str) -> str | None:
    return _MAKER_BY_KEY.get(brand_key(token))


def maker_regex() -> re.Pattern:
    names = sorted({*PART_MAKERS, "Toyota", "Volkswagen", "Fiat", "Chevrolet", "GM", "Ford", "Honda",
                    "Hyundai", "Renault", "Nissan", "Peugeot", "Citroen", "Citroën", "Mitsubishi",
                    "Kia", "Jeep", "Motorcraft", "Mopar", "ACDelco", "Motrio"}, key=len, reverse=True)
    alt = "|".join(re.escape(n).replace(r"\ ", r"[\s\-]") for n in names)
    return re.compile(rf"(?<![A-Za-z])({alt})(?![A-Za-z])", re.IGNORECASE)


MAKER_RE = maker_regex()


def domain_is_catalog(domain: str, extra: set[str] | None = None) -> bool:
    d = (domain or "").lower().removeprefix("www.")
    pool = CATALOG_DOMAINS | (extra or set())
    return any(d == c or d.endswith("." + c) for c in pool)


# Categorias de produto (para classificar fabricantes por segmento)
CATEGORIES = [
    ("filtros", ["filtro", "elemento filtrante", "refil"]),
    ("freios", ["pastilha", "disco de freio", "lona", "sapata", "pinça", "pinca", "cilindro mestre",
                "flexivel de freio", "tambor", "fluido de freio", "freio"]),
    ("suspensão e direção", ["amortecedor", "mola", "bandeja", "pivô", "pivo", "bieleta", "terminal",
                              "barra axial", "coxim", "bucha", "batente", "caixa de direção", "suspens"]),
    ("motor", ["junta", "pistão", "pistao", "anel", "bronzina", "válvula", "valvula", "comando",
               "retentor", "bomba de óleo", "bomba de oleo", "cabeçote", "cabecote", "tucho"]),
    ("correias e tensores", ["correia", "tensor", "polia", "kit de distribuição", "kit distribuicao"]),
    ("ignição e injeção", ["vela", "bobina", "cabo de vela", "bico injetor", "injetor", "sensor",
                           "sonda lambda", "corpo de borboleta", "bomba de combustível",
                           "bomba de combustivel"]),
    ("arrefecimento", ["radiador", "bomba d'água", "bomba dagua", "bomba d agua", "válvula termostática",
                       "termostato", "reservatório", "eletroventilador", "mangueira"]),
    ("transmissão e embreagem", ["embreagem", "platô", "plato", "disco de embreagem", "rolamento",
                                  "atuador", "semieixo", "homocinética", "homocinetica", "câmbio",
                                  "cambio", "trizeta"]),
    ("elétrica", ["alternador", "motor de partida", "bateria", "regulador", "relé", "rele",
                  "chicote", "interruptor", "módulo", "modulo"]),
    ("iluminação", ["lâmpada", "lampada", "farol", "lanterna", "pisca"]),
    ("ar-condicionado", ["válvula de expansão", "compressor", "condensador", "evaporador", "ar condicionado"]),
    ("escapamento", ["catalisador", "escapamento", "silencioso", "abafador"]),
]


def categorize(texts: list[str]) -> str:
    """Categoria mais votada entre os títulos dos anúncios."""
    votes: dict[str, int] = {}
    for t in texts:
        f = fold(t)
        # vale a palavra-chave mais específica (mais longa): "válvula de expansão" > "válvula"
        best = max(((len(k), cat) for cat, kws in CATEGORIES for k in kws if fold(k) in f), default=None)
        if best:
            votes[best[1]] = votes.get(best[1], 0) + 1
    return max(votes, key=votes.get) if votes else "geral"
