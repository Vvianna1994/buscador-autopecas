"""Acesso às páginas encontradas.

- Respeita robots.txt (configurável) e identifica o robô no User-Agent.
- Detecta bloqueios (403/429, desafios anti-robô, captcha, login) e apenas registra:
  não tenta contornar autenticações ou proteções.
- Opcionalmente usa Playwright para páginas montadas por JavaScript.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from . import config

BLOCK_MARKERS = [
    "cf-chl-", "challenge-platform", "just a moment...", "attention required! | cloudflare",
    "captcha", "are you a robot", "você é um robô", "voce e um robo", "access denied",
    "acesso negado", "unusual traffic", "perimeterx", "px-captcha", "datadome", "incapsula",
]
LOGIN_MARKERS = ["faça login para continuar", "faca login para continuar", "entre na sua conta para"]


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int = 0
    html: str = ""
    outcome: str = "ok"   # ok | blocked | robots | http_error | timeout | error | unsupported
    detail: str = ""
    via_browser: bool = False

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


class RobotsCache:
    def __init__(self):
        self._cache: dict[str, robotparser.RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        lock = self._locks.setdefault(base, asyncio.Lock())
        async with lock:
            if base not in self._cache:
                rp = None
                try:
                    r = await client.get(base + "/robots.txt", timeout=8)
                    if r.status_code == 200 and "text/html" not in r.headers.get("content-type", ""):
                        rp = robotparser.RobotFileParser()
                        rp.parse(r.text.splitlines())
                except httpx.HTTPError:
                    rp = None  # sem robots.txt acessível => sem restrições declaradas
                self._cache[base] = rp
        rp = self._cache[base]
        return True if rp is None else rp.can_fetch(config.USER_AGENT, url)


def detect_block(status: int, html: str) -> str | None:
    if status in (401, 407):
        return f"exige autenticação (HTTP {status})"
    if status == 429:
        return "limite de acessos atingido (HTTP 429)"
    head = html[:20000].lower()
    if status in (403, 503) and any(m in head for m in BLOCK_MARKERS):
        return f"proteção anti-robô (HTTP {status})"
    title = re.search(r"<title[^>]*>(.*?)</title>", head, re.S)
    title = title.group(1).strip() if title else ""
    if any(m in title for m in BLOCK_MARKERS) or ("captcha" in head and len(head) < 15000):
        return "proteção anti-robô / captcha"
    if any(m in head for m in LOGIN_MARKERS) and len(head) < 15000:
        return "página exige login"
    if status == 403:
        return "acesso negado (HTTP 403)"
    return None


class Fetcher:
    def __init__(self, client: httpx.AsyncClient, settings: dict):
        self.client = client
        self.settings = settings
        self.robots = RobotsCache()
        self.sem = asyncio.Semaphore(max(1, int(settings.get("fetch_concurrency", 8))))
        self._domain_locks: dict[str, asyncio.Semaphore] = {}
        self._browser = None
        self._pw = None
        self._browser_lock = asyncio.Lock()

    async def fetch(self, url: str) -> FetchResult:
        domain = urlsplit(url).netloc
        dom_sem = self._domain_locks.setdefault(domain, asyncio.Semaphore(2))  # gentil com cada site
        async with self.sem, dom_sem:
            try:
                if self.settings.get("respect_robots", True) and not await self.robots.allowed(self.client, url):
                    return FetchResult(url, outcome="robots", detail="robots.txt não permite acesso automatizado")
                r = await self.client.get(url, timeout=float(self.settings.get("fetch_timeout", 15)),
                                          follow_redirects=True)
            except httpx.TimeoutException:
                return FetchResult(url, outcome="timeout", detail="tempo esgotado")
            except httpx.HTTPError as e:
                return FetchResult(url, outcome="error", detail=f"{type(e).__name__}: {e}"[:300])
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "xml" not in ctype and ctype:
                return FetchResult(url, str(r.url), r.status_code, outcome="unsupported",
                                   detail=f"formato não suportado ({ctype.split(';')[0]})")
            html = r.text
            block = detect_block(r.status_code, html)
            if block:
                return FetchResult(url, str(r.url), r.status_code, outcome="blocked", detail=block)
            if r.status_code >= 400:
                return FetchResult(url, str(r.url), r.status_code, outcome="http_error",
                                   detail=f"HTTP {r.status_code}")
            return FetchResult(url, str(r.url), r.status_code, html=html)

    async def render(self, url: str) -> FetchResult:
        """Carrega a página num navegador headless (Playwright) para sites montados por JavaScript."""
        async with self.sem:
            try:
                browser = await self._get_browser()
                page = await browser.new_page(user_agent=config.USER_AGENT)
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded",
                                           timeout=int(self.settings.get("fetch_timeout", 15)) * 1000)
                    await page.wait_for_timeout(1500)
                    html = await page.content()
                    status = resp.status if resp else 0
                finally:
                    await page.close()
            except Exception as e:  # navegador indisponível ou página com erro
                return FetchResult(url, outcome="error", detail=f"navegador: {type(e).__name__}: {e}"[:300],
                                   via_browser=True)
        block = detect_block(status, html)
        if block:
            return FetchResult(url, url, status, outcome="blocked", detail=block, via_browser=True)
        return FetchResult(url, url, status, html=html, via_browser=True)

    async def _get_browser(self):
        async with self._browser_lock:
            if self._browser is None:
                from playwright.async_api import async_playwright
                self._pw = await async_playwright().start()
                try:
                    self._browser = await self._pw.chromium.launch()
                except Exception:
                    self._browser = await self._pw.chromium.launch(
                        executable_path=config.env("CHROMIUM_PATH", "/opt/pw-browsers/chromium"),
                        args=["--headless", "--no-sandbox"])
            return self._browser

    async def close(self):
        if self._browser is not None:
            await self._browser.close()
            await self._pw.stop()
