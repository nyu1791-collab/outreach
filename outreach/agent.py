"""browser-use（vendor/browser-use）による AI ブラウザ操作。
取り入れた browser-use 公式サンプルのパターン:
  - examples/features/custom_output.py      → output_model_schema で結果を構造化
  - examples/features/sensitive_data.py     → 送り手の個人情報は LLM に見せずプレースホルダで入力
  - examples/custom-functions/*.py          → Tools に独自アクション（Web検索）を追加
  - examples/use-cases/find_influencer_profiles.py → SNS/連絡先リサーチ用の Profiles スキーマ
"""
import asyncio
import json
import os
from urllib.parse import urlparse

from pydantic import BaseModel

from browser_use import ActionResult, Agent, Browser, ChatGoogle, Tools


def make_llm():
    return ChatGoogle(model=os.getenv("BROWSER_USE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                      api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"), temperature=0)


# ---------------- フォーム入力 ----------------
class FormResult(BaseModel):
    filled: bool
    filled_fields: list[str]
    has_captcha: bool
    no_sales_notice: bool  # 「営業お断り」等の表記を見つけた
    note: str
    submitted: bool = False
    submission_evidence: str = ""


def _secrets(cfg):
    s = cfg["sender"]
    return {k: v for k, v in {
        "s_name": s.get("name", ""), "s_kana": s.get("kana", ""), "s_company": s.get("company", "") or s.get("name", ""),
        "s_email": s.get("email", ""), "s_tel": s.get("tel", ""), "s_zip": s.get("zip", ""),
        "s_address": s.get("address", ""), "s_url": s.get("url", ""),
    }.items() if v}


async def fill_form(url, cfg, msg, wait_human=True, headless=False):
    secrets = _secrets(cfg)
    domain = urlparse(url).netloc
    submit_rule = ("入力内容の確認画面に進むボタンまでは押して良いが、最終的な『送信』ボタンは絶対に押さないこと。"
                   if not cfg.get("auto_submit") or wait_human else "最後に送信ボタンを押して送信完了まで行うこと。")
    task = f"""{url} を開き、お問い合わせフォームに入力してください。
各欄には次のプレースホルダの値を使う: {', '.join(secrets)}
（s_name=氏名, s_kana=フリガナ, s_company=会社名, s_email=メール(確認欄にも同じ), s_tel=電話, s_zip=郵便番号, s_address=住所, s_url=URL）
件名欄があれば: {msg['subject']}
お問い合わせ内容（本文）欄には次の文章をそのまま入力:
-----
{msg['body']}
-----
- 問い合わせ種別の選択肢があれば「その他」「ご提案」「業務提携」等の近いものを選ぶ
- 個人情報・プライバシーポリシーへの同意チェックがあればチェック
- 必須でない欄で該当値が無いものは空のまま
- ページに「営業目的のお問い合わせはご遠慮ください」等の表記があれば入力せず no_sales_notice=true で終了
- CAPTCHA があれば has_captcha=true として終了
- submitted=true は最終送信後に完了画面を確認できた場合だけ。確認画面・入力エラーは false。
- 送信が完了した場合は submission_evidence に完了画面の文言をそのまま記録。未確認なら空文字。
- {submit_rule}"""
    from .scrape import FORM_HOSTS
    base = domain.removeprefix("www.")
    allowed = [domain, base, f"*.{base}", *FORM_HOSTS, "*.hsforms.com", "*.hubspot.com", "*.formrun.jp"]
    browser = Browser(headless=headless, keep_alive=True, allowed_domains=allowed)
    agent = Agent(task=task, llm=make_llm(), browser=browser, output_model_schema=FormResult,
                  sensitive_data={domain: secrets}, tools=Tools(exclude_actions=["search"]), use_vision=True)
    try:
        hist = await agent.run(max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")))
        raw = hist.final_result()
        res = FormResult.model_validate_json(raw) if raw else FormResult(filled=False, filled_fields=[], has_captcha=False,
                                                                       no_sales_notice=False, note="結果なし")
        if res.no_sales_notice:
            return "skipped", 0, "営業お断り表記"
        status = "filled" if res.filled else "error"
        if res.filled and wait_human and not headless:
            from .filler import ask_human
            status = await ask_human(len(res.filled_fields))
        elif res.filled and res.submitted and res.submission_evidence and not res.has_captcha and cfg.get("auto_submit") and not wait_human:
            status = "sent"
        note = ("CAPTCHAあり " if res.has_captcha else "") + res.note
        return status, len(res.filled_fields), note[:200]
    finally:
        await browser.kill()


# ---------------- 連絡先リサーチ（YouTuber・SNSクリエイター・サイトに連絡先が無い相手） ----------------
class Profile(BaseModel):
    platform: str
    profile_url: str


class ContactInfo(BaseModel):
    email: str
    contact_url: str
    profiles: list[Profile]
    audience: str  # 登録者数・フォロワー数など
    recent_activity: str  # 最新投稿・最近の活動
    note: str


def _research_tools():
    tools = Tools(exclude_actions=["search"])

    @tools.registry.action("Search the web for a query and return result URLs, titles and snippets")
    async def search_web(query: str):
        from . import fc
        try:
            if fc.client():
                res = fc.search(query, limit=8)
            else:
                from ddgs import DDGS
                res = [{"url": r["href"], "title": r["title"], "description": r.get("body", "")}
                       for r in DDGS().text(query, region="jp-jp", max_results=8)]
        except Exception as e:
            return ActionResult(error=str(e))
        return ActionResult(extracted_content=json.dumps(res, ensure_ascii=False, indent=1), include_in_memory=True)

    return tools


async def research(lead: dict, headless=True) -> ContactInfo | None:
    task = f"""営業先「{lead['name']}」（{lead['url']}）について、ビジネス用の連絡手段と最近の活動を調べてください。
手がかり: SNS={lead.get('socials','')}
- YouTube チャンネルなら「概要」タブのビジネス用メール・リンクを確認
- X / Instagram / TikTok のプロフィール欄のメール・リンク（lit.link, linktree 等も開く）を確認
- search_web アクションで「{lead['name']} お問い合わせ」「{lead['name']} 仕事依頼」等も検索
- 見つからない項目は空文字。推測で作らない"""
    browser = Browser(headless=headless)
    agent = Agent(task=task, llm=make_llm(), browser=browser, tools=_research_tools(), output_model_schema=ContactInfo)
    try:
        hist = await agent.run(max_steps=int(os.getenv("AGENT_MAX_STEPS", "30")))
        raw = hist.final_result()
        return ContactInfo.model_validate_json(raw) if raw else None
    finally:
        await browser.kill()
