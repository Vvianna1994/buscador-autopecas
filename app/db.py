"""Armazenamento em SQLite: configurações, histórico/cache de pesquisas, falhas de acesso,
consumo de tokens e análises de fabricantes e vendedores."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, code_norm TEXT NOT NULL,
    collected_at TEXT NOT NULL, status TEXT NOT NULL,
    stats TEXT, result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_searches_code ON searches(code_norm, collected_at);
CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER, at TEXT NOT NULL, url TEXT NOT NULL, domain TEXT,
    outcome TEXT NOT NULL, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_access_search ON access_log(search_id);
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL, search_id INTEGER, operation TEXT NOT NULL, subject TEXT,
    model TEXT, input_tokens INTEGER, output_tokens INTEGER,
    cache_read_tokens INTEGER, cache_write_tokens INTEGER,
    web_searches INTEGER, cost_usd REAL, ok INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS manufacturer_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_norm TEXT NOT NULL, brand TEXT NOT NULL, category TEXT NOT NULL,
    at TEXT NOT NULL, tier TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_manu ON manufacturer_analyses(brand_norm, category, at);
CREATE TABLE IF NOT EXISTS seller_reputation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_key TEXT NOT NULL, seller TEXT NOT NULL, at TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_seller ON seller_reputation(seller_key, at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = Path(config.DB_PATH)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def reset(path: str) -> None:
    """Troca o arquivo do banco (usado nos testes)."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None
    config.DB_PATH = Path(path)


def execute(sql: str, args: tuple = ()) -> int:
    with _lock:
        c = conn()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


# ---------- configurações ----------

def get_settings() -> dict:
    s = dict(config.DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        if row["key"] in s:
            s[row["key"]] = json.loads(row["value"])
    return s


def update_settings(changes: dict) -> dict:
    defaults = config.DEFAULT_SETTINGS
    for k, v in changes.items():
        if k not in defaults:
            raise ValueError(f"configuração desconhecida: {k}")
        expected = type(defaults[k])
        if expected is bool:
            v = bool(v)
        elif expected is int:
            v = int(v)
            if v < 0:
                raise ValueError(f"{k} não pode ser negativo")
        else:
            v = str(v)
        execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, json.dumps(v)))
    return get_settings()


# ---------- pesquisas ----------

def create_search(code: str, code_norm: str) -> int:
    return execute("INSERT INTO searches(code, code_norm, collected_at, status) VALUES(?,?,?,?)",
                   (code, code_norm, now(), "running"))


def finish_search(search_id: int, status: str, stats: dict | None, result: dict | None,
                  error: str | None = None) -> None:
    execute("UPDATE searches SET status=?, stats=?, result=?, error=?, collected_at=? WHERE id=?",
            (status, json.dumps(stats) if stats else None,
             json.dumps(result, ensure_ascii=False) if result else None, error, now(), search_id))


def get_search(search_id: int) -> dict | None:
    rows = query("SELECT * FROM searches WHERE id=?", (search_id,))
    return _decode_search(rows[0]) if rows else None


def latest_valid_search(code_norm: str, max_age_hours: int) -> dict | None:
    if max_age_hours <= 0:
        return None
    limit = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat(timespec="seconds")
    rows = query("SELECT * FROM searches WHERE code_norm=? AND status='done' AND collected_at>=? "
                 "ORDER BY collected_at DESC LIMIT 1", (code_norm, limit))
    return _decode_search(rows[0]) if rows else None


def search_history(limit: int = 50) -> list[dict]:
    rows = query("SELECT id, code, code_norm, collected_at, status, stats, error FROM searches "
                 "ORDER BY id DESC LIMIT ?", (limit,))
    return [_decode_search(r) for r in rows]


def _decode_search(r: dict) -> dict:
    for k in ("stats", "result"):
        if r.get(k):
            r[k] = json.loads(r[k])
    return r


# ---------- falhas de acesso ----------

def log_access(search_id: int | None, url: str, domain: str, outcome: str, detail: str = "") -> None:
    execute("INSERT INTO access_log(search_id, at, url, domain, outcome, detail) VALUES(?,?,?,?,?,?)",
            (search_id, now(), url, domain, outcome, detail[:500]))


def access_failures(limit: int = 200) -> list[dict]:
    return query("SELECT a.*, s.code FROM access_log a LEFT JOIN searches s ON s.id = a.search_id "
                 "WHERE a.outcome != 'ok' ORDER BY a.id DESC LIMIT ?", (limit,))


# ---------- tokens ----------

def log_tokens(**row) -> None:
    cols = ["at", "search_id", "operation", "subject", "model", "input_tokens", "output_tokens",
            "cache_read_tokens", "cache_write_tokens", "web_searches", "cost_usd", "ok", "detail"]
    row.setdefault("at", now())
    execute(f"INSERT INTO token_usage({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
            tuple(row.get(c) for c in cols))


def token_report(limit: int = 200) -> dict:
    rows = query("SELECT * FROM token_usage ORDER BY id DESC LIMIT ?", (limit,))
    totals = query("SELECT operation, model, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
                   "SUM(output_tokens) AS output_tokens, SUM(web_searches) AS web_searches, "
                   "SUM(cost_usd) AS cost_usd FROM token_usage GROUP BY operation, model")
    grand = query("SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens, "
                  "COALESCE(SUM(output_tokens),0) AS output_tokens, "
                  "COALESCE(SUM(cost_usd),0) AS cost_usd FROM token_usage")[0]
    return {"rows": rows, "by_operation": totals, "total": grand}


# ---------- fabricantes ----------

def get_manufacturer(brand_norm: str, category: str, max_age_days: int) -> dict | None:
    limit = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = query("SELECT * FROM manufacturer_analyses WHERE brand_norm=? AND category=? AND at>=? "
                 "ORDER BY at DESC LIMIT 1", (brand_norm, category, limit))
    if not rows:
        return None
    d = json.loads(rows[0]["data"])
    d["analyzed_at"] = rows[0]["at"]
    return d


def save_manufacturer(brand_norm: str, brand: str, category: str, data: dict) -> None:
    execute("INSERT INTO manufacturer_analyses(brand_norm, brand, category, at, tier, data) "
            "VALUES(?,?,?,?,?,?)",
            (brand_norm, brand, category, now(), data.get("tier", ""), json.dumps(data, ensure_ascii=False)))


def manufacturer_history(limit: int = 200) -> list[dict]:
    rows = query("SELECT * FROM manufacturer_analyses ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["data"] = json.loads(r["data"])
    return rows


# ---------- vendedores ----------

def get_reputation(seller_key: str, max_age_days: int) -> dict | None:
    limit = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = query("SELECT * FROM seller_reputation WHERE seller_key=? AND at>=? ORDER BY at DESC LIMIT 1",
                 (seller_key, limit))
    if not rows:
        return None
    d = json.loads(rows[0]["data"])
    d["analyzed_at"] = rows[0]["at"]
    return d


def save_reputation(seller_key: str, seller: str, data: dict) -> None:
    execute("INSERT INTO seller_reputation(seller_key, seller, at, data) VALUES(?,?,?,?)",
            (seller_key, seller, now(), json.dumps(data, ensure_ascii=False)))
