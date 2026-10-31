"""サイト解析: Firecrawl（vendor/firecrawl）で取得 → Gemini で営業に使う情報を構造化。
Firecrawl 未起動なら requests+BeautifulSoup、Gemini キー無しなら正規表現で最低限。"""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import fc, llm

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
CONTACT_HINTS = ("contact", "inquiry", "toiawase", "otoiawase", "form", "お問い合わせ", "お問合せ", "問い合わせ", "ご相談")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SOCIAL = ("twitter.com", "x.com", "instagram.com", "youtube.com", "tiktok.com", "facebook.com", "line.me", "note.com")
FORM_HOSTS = ("form.run", "docs.google.com", "forms.gle", "share.hsforms.com", "ssl.form-mailer.jp", "tayori.com", "formzu.net")
NO_SALES_RE = re.compile(
    r"(?:営業|セールス|勧誘)(?:[・/／、,と]*(?:営業|セールス|勧誘))*"
    r"(?:目的)?(?:での|による|に関する|の)?"
    r"(?:(?:お問い合わせ|お問合せ|お問合わせ|問い合わせ|問合せ|ご連絡|連絡|メール|電話|ご提案|提案)"
    r"(?:等|など)?(?:は|を|について)?)?"
    r"(?:は|を)?(?:固く|一切|原則)?"
    r"(?:ご遠慮|お断り|禁止|受け付けておりません|受け付けません|お受けできません)"
)


def has_no_sales_notice(text):
    """改行や全角空白を除いて共通の営業禁止表記を検査する。"""
    return bool(NO_SALES_RE.search(re.sub(r"\s+", "", text or "")))

EXTRACT_PROMPT = """以下は企業/個人のWebサイト本文です。営業アプローチ用に情報を抽出し JSON で返してください。
キー:
- company: 正式な会社名・屋号・チャンネル名
- summary: 何をしている相手か（80字）
- recent: 最近の取り組み・ニュース・新サービス（あれば60字、無ければ空）
- pain: 相手が抱えていそうな課題の推測（60字）
- hook: 営業文の冒頭で触れると良い具体的な一点（40字）
- no_sales: 「営業お断り」等の記載があれば true

本文:
{text}"""


COOKIES = {}  # {"dlsite.com": {"adultchecked": "1"}}  config.yaml の cookies から設定


def _cookies(url):
    host = urlparse(url).netloc
    return {k: v for dom, kv in COOKIES.items() if host == dom or host.endswith("." + dom) for k, v in kv.items()}


def _fetch(url):
    r = requests.get(url, headers=UA, timeout=20, cookies=_cookies(url))
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def _local(url):
    html = _fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title else ""
    links = [urljoin(url, a["href"]) for a in soup.find_all("a", href=True)]
    labels = {urljoin(url, a["href"]): a.get_text(" ", strip=True) for a in soup.find_all("a", href=True)}
    has_form = bool(soup.find("form") and soup.find("textarea"))
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()
    text = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()
    return text, links, title, labels, has_form, html


def _base(netloc):
    return netloc.lower().removeprefix("www.")


def _contact(url, links, labels):
    for l in links:
        low = (l + " " + labels.get(l, "")).lower()
        if l.startswith("mailto:"):
            continue
        host, site = _base(urlparse(l).netloc), _base(urlparse(url).netloc)
        if any(h in low for h in CONTACT_HINTS) and (host == site or host.endswith("." + site) or host in FORM_HOSTS):
            return l
    return ""


RESEARCH_PROMPT = """Google 検索で「{name}」（{url}）について調べ、営業メッセージの冒頭で触れられる**最近の具体的な事実**を最大3つ挙げてください。
（新店舗・新商品・新作・イベント・受賞・採用・SNSで話題になったこと等。直近1年以内を優先）
確認できない・別の会社の情報しか無い場合は facts を空にする。推測は書かない。
JSON のみ: {{"facts": ["事実1（いつ・何を）", ...]}}"""


def web_research(name, url):
    """Gemini + Google 検索で相手の最近の動きを出典付きで集める。-> (facts, sources)"""
    try:
        res, sources = llm.ask_sources(RESEARCH_PROMPT.format(name=name, url=url), json_mode=True, temperature=0, task="research")
    except Exception as e:
        print(f"  Web調査失敗: {e}")
        return [], []
    facts = [str(f) for f in (res.get("facts") if isinstance(res, dict) else []) or [] if str(f).strip()][:3]
    return (facts, sources[:5]) if facts and sources else ([], [])


def analyze(url: str, extract_hint: str = "", web: bool = False) -> dict:
    labels, has_form, raw = {}, False, ""
    if fc.client():
        try:
            text, links, title = fc.scrape(url, main_only=False)
        except Exception as e:
            print(f"  firecrawl失敗→ローカル: {e}")
            text, links, title, labels, has_form, raw = _local(url)
    else:
        text, links, title, labels, has_form, raw = _local(url)

    contact = _contact(url, links, labels)
    if not contact and fc.client():  # サイトマップ全体から問い合わせページを探す（Firecrawl map）
        try:
            cand = fc.map_urls(url, search="contact お問い合わせ inquiry", limit=10)
            contact = next((u for u in cand if any(h in u.lower() for h in CONTACT_HINTS)), "")
        except Exception:
            pass
    if not contact and has_form:
        contact = url

    blob = text + " " + raw + " " + " ".join(links)
    emails = sorted({e.rstrip(".") for e in EMAIL_RE.findall(blob)
                     if not e.lower().endswith((".png", ".jpg", ".gif", ".webp", ".svg")) and "example" not in e})
    socials = sorted({l.split("?")[0] for l in links if any(s in urlparse(l).netloc for s in SOCIAL)})

    info = None
    try:
        info = llm.ask(EXTRACT_PROMPT.format(text=text[:8000]) + (f"\n追加の指示: {extract_hint}" if extract_hint else ""),
                       json_mode=True, temperature=0, task="extract")
    except Exception as e:
        print(f"  抽出LLM失敗: {e}")
    info = info or {"company": title, "summary": text[:200].replace("\n", " "), "hook": "", "pain": "", "recent": ""}
    info["no_sales"] = bool(info.get("no_sales")) or has_no_sales_notice(text)
    facts, sources = web_research(info.get("company") or title or url, url) if web else ([], [])
    if facts:
        info["recent"] = " / ".join(facts)
    return {
        "title": info.get("company") or title,
        "contact_url": contact,
        "email": ", ".join(emails[:3]),
        "socials": " ".join(socials[:6]),
        "hook": " / ".join(x for x in (info.get("hook"), info.get("recent"), info.get("pain")) if x),
        "no_sales": info["no_sales"],
        "text": (f"【概要】{info.get('summary','')}\n【最近】{info.get('recent','')}\n【課題仮説】{info.get('pain','')}\n"
                 + ("【Web調査の出典】" + " ".join(s["uri"] for s in sources) + "\n" if sources else "") + "\n" + text)[:6000],
    }


def discover(query: str, n: int = 20) -> list[dict]:
    """検索で候補サイトを集める。Firecrawl search → 無ければ DuckDuckGo。"""
    raw = []
    if fc.client():
        try:
            raw = [{"href": r["url"], "title": r["title"]} for r in fc.search(query, limit=n * 2)]
        except Exception as e:
            print(f"  firecrawl search失敗→DuckDuckGo: {e}")
    if not raw:
        from ddgs import DDGS
        raw = list(DDGS().text(query, region="jp-jp", max_results=n * 2))
    skip = ("wikipedia.org", "amazon.", "rakuten.", "hotpepper", "tabelog", "indeed", "youtube.com", "x.com", "instagram.com")
    seen, out = set(), []
    for r in raw:
        u = urlparse(r.get("href", ""))
        if not u.netloc or u.netloc in seen or any(s in u.netloc for s in skip):
            continue
        seen.add(u.netloc)
        out.append({"name": r.get("title") or u.netloc, "url": f"{u.scheme}://{u.netloc}/"})
        if len(out) >= n:
            break
    return out
