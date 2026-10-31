"""お問い合わせフォーム自動入力。
- 標準: Playwright でラベル/placeholder/name をキーワード照合して入力 → スクショ → 人間が確認して送信（半自動）
- 入力できた項目が少ない/複雑なフォームは __main__ 側で agent.fill_form（browser-use）へ自動切替"""
import asyncio
import os
import re
from pathlib import Path

from .scrape import has_no_sales_notice

DELIVERY_RE = re.compile(
    r"送信(?:が)?完了(?:しました|いたしました)|送信されました|送信完了(?=[\s。.!！]|$)"
    r"|お問い合わせ(?:を)?(?:受け付けました|受付いたしました)"
    r"|thank you for (?:your (?:message|inquiry)|contacting us)"
    r"|(?:message|inquiry) (?:has been |was )?(?:successfully )?sent",
    re.IGNORECASE,
)

# 姓/名・セイ/メイに分かれた欄（日本のフォームに多い）。ラベルが「姓」「名」単独のものだけ当てる
_ALONE = r"(?:^|\s){}(?:\s|$|[（(：:*※])"
FIELD_RULES = [  # (キー, 判定パターン)  上から順に照合
    ("email_confirm", r"(確認|再入力|confirm).*(mail|メール)|(mail|メール).*(確認|再入力|confirm)"),
    ("email", r"mail|メール"),
    ("kana_last", r"セイ|せい|kana.?(last|sei|family)|(last|sei|family).?kana|(?:フリガナ|ふりがな)\s*[（(]?\s*姓"),
    ("kana_first", r"メイ|めい|kana.?(first|mei|given)|(first|mei|given).?kana|(?:フリガナ|ふりがな)\s*[（(]?\s*名(?!前)"),
    ("kana", r"kana|フリガナ|ふりがな|カナ"),
    ("company", r"company|会社|法人|御社|貴社|組織|団体|屋号|corp"),
    ("tel", r"tel|phone|電話|携帯"),
    ("zip", r"zip|postal|郵便"),
    ("address", r"address|住所|所在地"),
    ("subject", r"subject|title|件名|タイトル|用件"),
    ("url", r"url|website|ホームページ|サイト"),
    ("last_name", r"last.?name|family.?name|lname|(?:^|[\s_\-\[])sei(?:$|[\s_\-\]\d])|" + _ALONE.format("姓")),
    ("first_name", r"first.?name|given.?name|fname|(?:^|[\s_\-\[])mei(?:$|[\s_\-\]\d])|" + _ALONE.format("名")),
    ("name", r"name|名前|氏名|担当者"),
]
PREFS = ("北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 "
         "福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 "
         "山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県").split()


def _split(full):
    parts = re.split(r"[\s\u3000]+", (full or "").strip(), maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (full or "", "")
SHOTS = Path(os.getenv("DATA_DIR", "data")) / "shots"


def _values(cfg, msg):
    s = cfg["sender"]
    last, first = _split(s["name"])
    kana_last, kana_first = _split(s.get("kana", ""))
    return {"last_name": last, "first_name": first, "kana_last": kana_last, "kana_first": kana_first,
            "email": s.get("email", ""), "email_confirm": s.get("email", ""), "kana": s.get("kana", ""),
            "company": s.get("company", "") or s["name"], "tel": s.get("tel", ""), "zip": s.get("zip", ""),
            "address": s.get("address", ""), "subject": msg["subject"], "url": s.get("url", ""), "name": s["name"],
            "message": msg["body"]}


async def _describe(el):
    return await el.evaluate("""e => {
        const lab = (e.id && document.querySelector(`label[for="${e.id}"]`)) || e.closest('label');
        const row = e.closest('tr,dl,li,.form-group,.row,p,div');
        // 同じ行に「姓」「名」が並ぶ表では、行の先頭ではなく入力欄の直前の見出しセルを使う
        const cell = e.closest('td,dd');
        const prev = cell && cell.previousElementSibling;
        const th = (prev && /^(TH|DT|LABEL)$/.test(prev.tagName)) ? prev.innerText
                 : (row ? (row.querySelector('th,dt,label')||{}).innerText : '');
        return [e.name, e.id, e.placeholder, e.getAttribute('aria-label'), lab?lab.innerText:'', th||''].join(' ');
    }""")


async def ask_human(filled):
    """人間の最終確認。Enter だけでは「送信済み」にしない（押し間違いで送ったことにならないように）。"""
    while True:
        ans = (await asyncio.to_thread(
            input, f"  [{filled}項目入力] ブラウザで確認してください。 y=送信した / s=送らない / Enter=入力だけ（未送信） : ")).strip().lower()
        if ans in ("y", "yes", "送信"):
            return "sent"
        if ans in ("s", "skip"):
            return "skipped"
        if ans == "":
            return "filled"


async def fill_heuristic(url, cfg, msg, lead_id, headless=False, wait_human=True):
    from playwright.async_api import async_playwright
    vals = _values(cfg, msg)
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, executable_path=os.getenv("CHROME_PATH") or None)
        page = await browser.new_page(locale="ja-JP")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(1500)
        before_text = await page.inner_text("body")
        if has_no_sales_notice(before_text):
            await page.screenshot(path=str(SHOTS / f"{lead_id}.png"), full_page=True)
            await browser.close()
            return "no_sales", 0
        filled = 0
        for el in await page.query_selector_all("input, textarea, select"):
            try:
                if not await el.is_visible():
                    continue
                tag = await el.evaluate("e => e.tagName.toLowerCase()")
                typ = (await el.get_attribute("type") or "text").lower()
                desc = (await _describe(el)).lower()
                if tag == "textarea":
                    await el.fill(vals["message"]); filled += 1; continue
                if typ == "checkbox" and re.search(r"同意|agree|privacy|個人情報|プライバシー", desc):
                    await el.check(); continue
                if tag == "select":
                    # 当てはまる選択肢が無ければ選ばない（末尾を選ぶと都道府県=沖縄県 等の誤入力になる）
                    opts = await el.evaluate("e => [...e.options].filter(o => o.value).map(o => [o.value, o.text])")
                    texts = " ".join(t for _, t in opts)
                    if sum(p in texts for p in PREFS) >= 10:  # 都道府県
                        pref = next((p for p in PREFS if p in (cfg["sender"].get("address") or "")), None)
                        pick = next((v for v, t in opts if pref and pref in t), None)
                    else:
                        pick = next((v for v, t in opts if re.search(r"その他|other|提案|営業|相談|業務提携", t, re.I)), None)
                    if pick:
                        await el.select_option(pick)
                    continue
                if typ in ("hidden", "submit", "button", "radio", "checkbox", "file", "image", "reset"):
                    continue
                if typ == "email":
                    key = "email_confirm" if re.search(FIELD_RULES[0][1], desc) else "email"
                else:
                    key = next((k for k, pat in FIELD_RULES if re.search(pat, desc)), None)
                if key and vals.get(key):
                    await el.fill(vals[key]); filled += 1
            except Exception:
                continue
        shot = SHOTS / f"{lead_id}.png"
        await page.screenshot(path=str(shot), full_page=True)
        result = "filled"
        if filled < 2:  # ほぼ入らなかった → 呼び出し側で AI エージェントへ
            await browser.close()
            return "retry_agent", filled
        if wait_human and not headless:
            result = await ask_human(filled)
        elif cfg.get("auto_submit"):
            btn = await page.query_selector("button[type=submit], input[type=submit], button:has-text('送信'), button:has-text('確認')")
            if btn:
                await btn.click(); await page.wait_for_timeout(3000)
                after_text = await page.inner_text("body")
                # 「確認」への遷移や入力エラーは送信成功ではない。
                if DELIVERY_RE.search(after_text) and not DELIVERY_RE.search(before_text):
                    result = "sent"
                await page.screenshot(path=str(shot), full_page=True)
        await browser.close()
        return result, filled
