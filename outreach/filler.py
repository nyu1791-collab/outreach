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

FIELD_RULES = [  # (キー, 判定パターン)  上から順に照合
    ("email_confirm", r"(確認|再入力|confirm).*(mail|メール)|(mail|メール).*(確認|再入力|confirm)"),
    ("email", r"mail|メール"),
    ("kana", r"kana|フリガナ|ふりがな|カナ"),
    ("company", r"company|会社|法人|御社|貴社|組織|団体|屋号|corp"),
    ("tel", r"tel|phone|電話|携帯"),
    ("zip", r"zip|postal|郵便"),
    ("address", r"address|住所|所在地"),
    ("subject", r"subject|title|件名|タイトル|用件"),
    ("url", r"url|website|ホームページ|サイト"),
    ("name", r"name|名前|氏名|担当者"),
]
SHOTS = Path(os.getenv("DATA_DIR", "data")) / "shots"


def _values(cfg, msg):
    s = cfg["sender"]
    return {"email": s.get("email", ""), "email_confirm": s.get("email", ""), "kana": s.get("kana", ""),
            "company": s.get("company", "") or s["name"], "tel": s.get("tel", ""), "zip": s.get("zip", ""),
            "address": s.get("address", ""), "subject": msg["subject"], "url": s.get("url", ""), "name": s["name"],
            "message": msg["body"]}


async def _describe(el):
    return await el.evaluate("""e => {
        const lab = (e.id && document.querySelector(`label[for="${e.id}"]`)) || e.closest('label');
        const row = e.closest('tr,dl,li,.form-group,.row,p,div');
        const th = row ? (row.querySelector('th,dt,label')||{}).innerText : '';
        return [e.name, e.id, e.placeholder, e.getAttribute('aria-label'), lab?lab.innerText:'', th||''].join(' ');
    }""")


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
                    opts = await el.evaluate("e => [...e.options].map(o => o.value).filter(Boolean)")
                    pick = next((o for o in opts if re.search(r"その他|other|提案|営業|相談", o, re.I)), opts[-1] if opts else None)
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
            ans = await asyncio.to_thread(input, f"  [{filled}項目入力] ブラウザで確認→送信したら Enter / スキップは s : ")
            result = "skipped" if ans.strip().lower() == "s" else "sent"
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
