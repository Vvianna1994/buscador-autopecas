import pytest

from app import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db.reset(str(tmp_path / "test.db"))
    # Os testes nunca chamam a API real de IA nem de pesquisa
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "SERPAPI_KEY",
                "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.ai.available", lambda: False)
    yield
