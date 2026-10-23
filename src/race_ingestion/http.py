from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str


class RespectfulClient:
    def __init__(self, user_agent: str | None = None, timeout: float | None = None):
        self.user_agent = user_agent or os.getenv(
            "INGESTION_USER_AGENT", "CorridasBrasilBot/0.1 (+mailto:contato@example.com)"
        )
        self.timeout = timeout or float(os.getenv("INGESTION_TIMEOUT_SECONDS", "30"))
        self.client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6"},
            timeout=self.timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}

    def close(self) -> None:
        self.client.close()

    def _robot(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root in self._robots:
            return self._robots[root]
        robots_url = f"{root}/robots.txt"
        try:
            response = self.client.get(robots_url)
            if response.status_code == 404:
                self._robots[root] = None
                return None
            response.raise_for_status()
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            self._robots[root] = parser
            return parser
        except httpx.HTTPError:
            # Falha de rede não vira autorização implícita: o fetch principal ainda pode falhar;
            # o log do job registra a indisponibilidade do robots.txt.
            self._robots[root] = None
            return None

    def allowed(self, url: str) -> bool:
        parser = self._robot(url)
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def fetch(self, url: str, delay_seconds: float = 2.0, render: str = "http") -> FetchResult:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt não permite coleta de {url}")
        host = urlsplit(url).netloc
        wait = delay_seconds - (time.monotonic() - self._last_request.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        try:
            response = self.client.get(url)
            self._last_request[host] = time.monotonic()
            response.raise_for_status()
            text = response.text
            if render in {"auto", "browser"} and self._looks_js_empty(text):
                text = self._fetch_browser(str(response.url))
            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                content_type=response.headers.get("content-type", ""),
                text=text,
            )
        except httpx.HTTPError:
            if render in {"auto", "browser"}:
                text = self._fetch_browser(url)
                return FetchResult(url=url, status_code=200, content_type="text/html", text=text)
            raise

    @staticmethod
    def _looks_js_empty(text: str) -> bool:
        low = text.lower()
        return len(text) < 2500 or ("<script" in low and "<article" not in low and "application/ld+json" not in low)

    def _fetch_browser(self, url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Página dinâmica detectada. Instale: pip install -e '.[browser]' && playwright install chromium"
            ) from exc
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.user_agent, locale="pt-BR")
            page.goto(url, wait_until="networkidle", timeout=int(self.timeout * 1000))
            content = page.content()
            browser.close()
            return content
