"""Firecrawl 接続（vendor/firecrawl の公式 Python SDK を使用）。
優先順: FIRECRAWL_API_URL（ローカル self-host, キー不要） → FIRECRAWL_API_KEY（クラウド） → None（呼び出し側でフォールバック）"""
import os

_client = False


def client():
    global _client
    if _client is not False:
        return _client
    url, key = os.getenv("FIRECRAWL_API_URL"), os.getenv("FIRECRAWL_API_KEY")
    if not (url or key):
        _client = None
        return None
    try:
        from firecrawl import Firecrawl
    except ImportError:  # キーはあるが未導入（GitHub Actions 等）→ 通常のページ取得で続ける
        print("  Firecrawl のキーがありますがライブラリ未導入のため使いません（setup.ps1 -WithFirecrawl / pip install firecrawl-py）")
        _client = None
        return None
    _client = Firecrawl(api_key=key or "fc-local", api_url=url or "https://api.firecrawl.dev")
    return _client


def scrape(url, main_only=True):
    """-> (markdown, links, title)"""
    c = client()
    doc = c.scrape(url, formats=["markdown", "links"], only_main_content=main_only, timeout=60000)
    title = getattr(doc.metadata, "title", "") if doc.metadata else ""
    return doc.markdown or "", doc.links or [], title or ""


def map_urls(url, search=None, limit=30):
    res = client().map(url, search=search, limit=limit)
    return [l.url for l in (res.links if hasattr(res, "links") else res)]


def search(query, limit=10, location="Japan"):
    res = client().search(query, limit=limit, location=location)
    return [{"url": r.url, "title": getattr(r, "title", "") or "", "description": getattr(r, "description", "") or ""}
            for r in (res.web or [])]
