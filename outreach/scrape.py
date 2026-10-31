"""ページ取得 → LLMが読みやすいテキスト化 + 連絡先抽出。
Firecrawl のキーがあれば Firecrawl（JS描画・綺麗なMarkdown）、無ければ requests+BeautifulSoup。"""
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
CONTACT_HINTS = ("contact", "inquiry", "toiawase", "otoiawase", "form", "お問い合わせ", "お問合せ", "問い合わせ", "ご相談", "相談")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SOCIAL = ("twitter.com", "x.com", "instagram.com", "youtube.com", "tiktok.com", "facebook.com", "line.me")


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=20)
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def to_markdown(url: str) -> str:
    key = os.getenv("FIRECRAWL_API_KEY")
    if key:
        try:
            from firecrawl import Firecrawl
            doc = Firecrawl(api_key=key).scrape(url, formats=["markdown"], only_main_content=True)
            md = getattr(doc, "markdown", None) or (doc.get("markdown") if isinstance(doc, dict) else None)
            if md:
                return md
        except Exception as e:  # Firecrawl 失敗時はローカル取得へ
            print(f"  firecrawl失敗 → ローカル取得: {e}")
    soup = BeautifulSoup(fetch_html(url), "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def analyze(url: str) -> dict:
    """トップページから 会社名/お問い合わせURL/メール/SNS/本文 を取る。"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    contact_url = ""
    socials = set()
    for a in soup.find_all("a", href=True):
        href, label = a["href"], a.get_text(" ", strip=True).lower()
        full = urljoin(url, href)
        if not contact_url and any(h in (href.lower() + label) for h in CONTACT_HINTS) and not href.startswith("mailto:"):
            contact_url = full
        if any(s in urlparse(full).netloc for s in SOCIAL):
            socials.add(full.split("?")[0])
    emails = {e for e in EMAIL_RE.findall(html) if not e.lower().endswith((".png", ".jpg", ".gif", ".webp", ".svg"))}
    for a in soup.select('a[href^="mailto:"]'):
        emails.add(a["href"][7:].split("?")[0])
    if not contact_url and soup.find("form") and soup.find("textarea"):
        contact_url = url
    return {
        "title": title,
        "contact_url": contact_url,
        "email": ", ".join(sorted(emails)[:3]),
        "socials": " ".join(sorted(socials)[:5]),
        "text": to_markdown(url)[:6000],
    }


def discover(query: str, n: int = 20) -> list[dict]:
    """検索クエリから候補サイトを集める（DuckDuckGo、APIキー不要）。"""
    from ddgs import DDGS
    seen, out = set(), []
    for r in DDGS().text(query, region="jp-jp", max_results=n * 2):
        url = r.get("href", "")
        dom = urlparse(url).netloc
        if not dom or dom in seen:
            continue
        seen.add(dom)
        out.append({"name": r.get("title", dom), "url": f"{urlparse(url).scheme}://{dom}/"})
        if len(out) >= n:
            break
    return out
