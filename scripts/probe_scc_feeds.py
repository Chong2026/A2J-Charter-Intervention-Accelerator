"""Discover and inspect the SCC's RSS/JSON feeds.

Goal: confirm that a feed exists for *leave applications* (grants), see which
fields it exposes, and decide whether Stage 1 can rely on it alone or also needs
the SCC docket pages.

Usage:
    pip install requests beautifulsoup4 lxml
    python scripts/probe_scc_feeds.py            # list feeds found on the RSS page
    python scripts/probe_scc_feeds.py URL [URL]  # fetch and preview specific feeds
"""
import json
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

INDEX_URL = "https://decisions.scc-csc.ca/scc-csc/en/rss/index.do"
HEADERS = {"User-Agent": "a2aj-charter-accelerator/0.1 (research; contact: your-email)"}


def list_feeds():
    r = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        href = urljoin(INDEX_URL, a["href"])
        if any(k in href.lower() for k in ("rss", "json", "feed", ".xml")):
            found.append((a.get_text(strip=True), href))
    print(f"{len(found)} candidate feed links on {INDEX_URL}\n")
    for text, href in found:
        print(f"- {text or '(no text)'}\n    {href}")


def preview(url, n=3):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    print(f"\n=== {url}\ncontent-type: {ctype}, {len(r.content)} bytes")
    if "json" in ctype or r.text.lstrip().startswith(("{", "[")):
        data = r.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("entries") or [data]
        print(f"top-level keys: {list(data)[:10] if isinstance(data, dict) else 'list'}")
        for item in items[:n]:
            print(json.dumps(item, indent=2, ensure_ascii=False)[:800])
    else:
        soup = BeautifulSoup(r.text, "xml")
        for item in soup.find_all(["item", "entry"])[:n]:
            print("---")
            for child in item.find_all(recursive=False):
                print(f"{child.name}: {child.get_text(strip=True)[:200]}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        list_feeds()
    else:
        for u in sys.argv[1:]:
            preview(u)
