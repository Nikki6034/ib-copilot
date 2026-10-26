"""Live IB / FIG / M&A news via free Google News RSS (no API key required).

Returns real, dated, source-linked headlines. Results are cached briefly to avoid
refetching. If the network is unavailable the feed returns ok=False and an empty list —
the app shows an honest "unavailable" state and never fabricates or mislabels news.
"""

from __future__ import annotations

import html
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

CATEGORY_QUERIES = {
    "all": "investment banking M&A OR bank merger OR FIG deal",
    "fig": "bank merger OR insurance acquisition OR \"financial institutions\" deal",
    "ma": "merger acquisition announced deal advisor",
    "fintech": "fintech acquisition OR payments company M&A",
    "banking": "bank acquisition OR regional bank merger",
    "insurance": "insurance company merger OR acquisition",
    "asset_management": "asset manager acquisition OR wealth management deal",
    "macro": "Federal Reserve interest rates bank earnings",
}
CATEGORIES = ["all", "fig", "ma", "fintech", "banking", "insurance", "asset_management", "macro"]

_CACHE: dict[str, tuple[float, list]] = {}
_TTL = 600  # seconds


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def fetch(category: str = "all", limit: int = 12) -> dict:
    category = category if category in CATEGORY_QUERIES else "all"
    now = time.time()
    if category in _CACHE and now - _CACHE[category][0] < _TTL:
        return {"ok": True, "items": _CACHE[category][1], "cached": True}
    q = CATEGORY_QUERIES[category]
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
           "&hl=en-US&gl=US&ceid=US:en")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (IB Copilot)"})
        data = urllib.request.urlopen(req, timeout=12).read()
        root = ET.fromstring(data)
        items = []
        for it in root.findall(".//item")[:limit]:
            src = it.find("{*}source")
            pub = it.findtext("pubDate") or ""
            try:
                date = parsedate_to_datetime(pub).strftime("%Y-%m-%d") if pub else ""
            except Exception:  # noqa: BLE001
                date = pub[:16]
            items.append({
                "headline": _clean(it.findtext("title")),
                "source": src.text if src is not None else "news",
                "url": it.findtext("link") or "",
                "date": date,
                "category": category,
            })
        _CACHE[category] = (now, items)
        return {"ok": True, "items": items, "cached": False}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:140]}", "items": []}
