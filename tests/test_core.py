from fastapi.testclient import TestClient

from app.main import app
from app.models import Offer
from app.parser import parse_query
from app.ranking import rank, years_in_title


def test_parse_full_query():
    pq = parse_query("pastilha de freio dianteira gol 1.0 2012 cobreq")
    assert pq.part_terms == ["pastilha", "freio"]
    assert pq.vehicle.brand == "Volkswagen" and pq.vehicle.model == "gol"
    assert pq.vehicle.engine == "1.0" and pq.vehicle.year == 2012
    assert pq.position == "dianteira" and pq.part_brand == "Cobreq"


def test_parse_compound_model_and_oem():
    assert parse_query("filtro ar corolla cross 2022").vehicle.model == "corolla cross"
    assert parse_query("pastilha 0986BB0597").oem_codes == ["0986BB0597"]


def test_years_in_title():
    assert years_in_title("Gol G5 08 a 12") == set(range(2008, 2013))
    assert years_in_title("Gol 2010/2013") == {2010, 2011, 2012, 2013}
    assert 2020 in years_in_title("Onix 2017 em diante")
    assert years_in_title("Pastilha Gol 1.0 16v") == set()


def _offer(title, price):
    return Offer(source="t", store=title[:5], title=title, price=price, shipping=0, url="")


def test_ranking_rejects_wrong_year_position_and_accessories():
    pq = parse_query("pastilha freio dianteira gol 2012")
    offers = [
        _offer("Pastilha Freio Dianteira Gol 2008 a 2016", 90),
        _offer("Pastilha Freio Traseira Gol 2008 a 2016", 70),
        _offer("Pastilha Freio Dianteira Gol 2003 a 2007", 60),
        _offer("Parafuso Pinça Pastilha Freio Gol", 10),
    ]
    results, _ = rank(pq, offers, only_compatible=True)
    assert [r.offer.price for r in results] == [90]
    assert results[0].compatibility == "confirmada"


def test_api_search_demo():
    r = TestClient(app).get("/api/search", params={"q": "amortecedor dianteiro gol 2014"})
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["compatibility"] == "confirmada"
    assert TestClient(app).get("/").status_code == 200
