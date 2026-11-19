import pytest

from app import brands, codes
from app.crossref import CrossRefCollector, pairs_in_text
from app.extractor import extract_page, parse_price

from . import pages
from .pages import CODE


# ---------------- códigos ----------------

@pytest.mark.parametrize("raw", ["881620K021", "88162-0K021", "0 986 4B2 101", "PSL55", "W712/75"])
def test_accepts_codes(raw):
    assert codes.validate(raw)


@pytest.mark.parametrize("raw", ["filtro de oleo", "pastilha gol 2012", "ABC", "", "<script>"])
def test_rejects_non_codes(raw):
    with pytest.raises(codes.InvalidCode):
        codes.validate(raw)


def test_variations_and_matching():
    assert codes.variations("881620K021") == ["881620K021", "88162-0K021"]
    assert codes.variations("88162-0K021") == ["88162-0K021", "881620K021"]
    assert codes.contains("Válvula 88162 0K021 Hilux", CODE)
    assert codes.contains("ref: 88162.0k021.", CODE)
    assert not codes.contains("cod 881620K0210", CODE)  # parte de outro código
    assert not codes.contains("X881620K021", CODE)


def test_parse_price():
    assert parse_price("R$ 1.234,56") == 1234.56
    assert parse_price("689.90") == 689.90
    assert parse_price("1,234.56") == 1234.56
    assert parse_price("700,00") == 700.0
    assert parse_price("1.500") == 1500.0
    assert parse_price(0) is None and parse_price("") is None


def test_brands():
    assert brands.is_automaker("Toyota") and brands.is_automaker("Motorcraft")
    assert not brands.is_automaker("Bosch")
    assert brands.categorize(["Válvula de expansão ar condicionado", "Compressor ar condicionado"]) \
        == "ar-condicionado"
    assert brands.domain_is_catalog("www.tecfil.com.br")


# ---------------- extração ----------------

def test_extract_jsonld():
    pg = extract_page(pages.STORE_A, "https://alfa.example/p", CODE)
    [li] = pg.listings
    assert li.price == 689.90 and li.brand == "Toyota" and li.condition == "novo"
    assert li.store == "Loja Alfa Peças" and li.image == "https://img.alfa.example/v.jpg"
    assert li.match == "exact" and li.announced_code == CODE and li.data_source == "jsonld"
    assert li.missing == []


def test_extract_microdata_relative_image_and_missing_condition():
    [li] = extract_page(pages.STORE_B, "https://beta.example/x/item", CODE).listings
    assert li.price == 512.0 and li.brand == "Toyota" and li.image == "https://beta.example/img/valvula.jpg"
    assert li.match == "exact" and li.condition == "" and "condição" in li.missing


def test_extract_meta_and_spec_table():
    [li] = extract_page(pages.STORE_C, "https://c.example/u", CODE).listings
    assert li.price == 250.0 and li.condition == "usado" and li.brand == "Toyota" and li.match == "exact"


def test_aftermarket_listing_citing_code_is_not_original():
    [li] = extract_page(pages.STORE_D, "https://d.example/denso", CODE).listings
    assert li.match == "mentions" and li.announced_code == "DVE-1234" and li.brand == "Denso"


def test_listing_page_keeps_only_items_with_code():
    pg = extract_page(pages.LISTING_PAGE, "https://loja.example/busca?q=x", CODE)
    assert [li.url for li in pg.listings] == ["https://loja.example/p/1"]
    assert pg.listings[0].price == 700.0


def test_informative_page_has_no_listing():
    assert extract_page(pages.STORE_E, "https://e.example/tabela", CODE).listings == []


# ---------------- referências cruzadas ----------------

def test_pairs_in_text_spaced_code():
    pairs = pairs_in_text("Equivalência: Bosch 0 986 AC5 123 Filtro novo")
    assert ("Bosch", "0 986 AC5 123") == pairs[0][:2]


def test_crossref_confirmation_rules():
    col = CrossRefCollector(CODE, min_sources=2)
    col.add_page(extract_page(pages.STORE_D, "https://d.example/denso", CODE))
    refs = {r.brand: r for r in col.finalize()}
    # uma tabela só e um anúncio: ainda a verificar
    assert refs["Bosch"].status == "a_verificar"
    assert refs["Denso"].status == "a_verificar"
    col.add_page(extract_page(pages.STORE_E, "https://e.example/tabela", CODE))
    col.add_page(extract_page(pages.CATALOG, "https://www.mahle-aftermarket.com/cat", CODE))
    refs = {r.brand: r for r in col.finalize()}
    assert refs["Bosch"].status == "confirmada"          # duas tabelas independentes
    assert refs["Mahle"].status == "confirmada"          # catálogo do fabricante
    assert refs["Denso"].status == "a_verificar"          # só o anúncio afirma
    assert "Toyota" not in refs                          # o próprio código não é referência


def test_page_without_original_code_gives_no_evidence():
    col = CrossRefCollector(CODE)
    col.add_page(extract_page("<p>Referência: Bosch 0986AC5123</p>", "https://x.example", CODE))
    assert col.finalize() == []
