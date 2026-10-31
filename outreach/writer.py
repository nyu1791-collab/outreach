"""相手のサイト内容から1社ごとの営業文を作る。キー無しならテンプレ差し込み。"""
from pathlib import Path

from . import llm

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def campaign(cfg: dict, name: str | None) -> dict:
    """config の上書き: campaigns.<name> の offer / prompt / channel / max_chars などを全体設定に重ねる"""
    name = name or cfg.get("default_campaign") or ""
    over = (cfg.get("campaigns") or {}).get(name) or {}
    merged = {**cfg, **{k: v for k, v in over.items() if k != "offer"}}
    merged["offer"] = {**cfg.get("offer", {}), **(over.get("offer") or {})}
    merged["campaign"] = name
    merged.setdefault("channel", "form")
    return merged


def write(lead: dict, cfg: dict) -> dict:
    s, offer = cfg["sender"], cfg["offer"]
    tmpl = (PROMPTS / cfg.get("prompt", "message.md")).read_text(encoding="utf-8")
    prompt = tmpl.format(
        sender_name=s["name"], sender_company=s.get("company", ""), offer=offer["summary"],
        price=offer.get("price", ""), cta=offer.get("cta", ""), target_hint=offer.get("target_hint", ""), target_name=lead["name"],
        target_url=lead["url"], hook=lead.get("hook", ""), target_text=lead.get("summary", "")[:5000], max_chars=cfg.get("max_chars", 500),
    )
    res = llm.ask(prompt, json_mode=True)
    # 本文が無い/短すぎる応答で署名だけを送らないよう、形式を確認してから使う
    if isinstance(res, dict) and isinstance(res.get("body"), str) and len(res["body"].strip()) >= 50:
        subject = res.get("subject") if isinstance(res.get("subject"), str) and res["subject"].strip() else offer.get("subject", "ご提案のご連絡")
        return {"subject": subject.strip(), "body": res["body"].strip() + "\n" + footer(cfg)}
    if cfg.get("channel") == "dm":
        return {"subject": "", "body": f"はじめまして、{s['name']}です。{offer.get('short') or offer['summary']}をしています。\n"
                                       f"{offer.get('cta', '')}" + footer(cfg)}
    body = (
        f"{lead['name']} ご担当者様\n\n突然のご連絡失礼いたします。{s.get('company','')}の{s['name']}と申します。\n"
        f"貴社サイトを拝見し、{offer.get('short') or offer['summary']}でお力になれると考えご連絡しました。\n{offer.get('cta','')}\n"
    )
    return {"subject": offer.get("subject", "ご提案のご連絡"), "body": body + footer(cfg)}


def footer(cfg: dict) -> str:
    s = cfg["sender"]
    if cfg.get("channel") == "dm":  # DM は短く。不要なら無視してよい旨だけ
        return "\n（不要でしたらスルーしてください🙏）"
    lines = ["", "――――――――――", f"{s.get('company','')} {s['name']}", s.get("email", ""), s.get("url", ""),
             cfg.get("optout", "今後のご連絡が不要な場合はお手数ですがその旨ご返信ください。以後お送りいたしません。")]
    return "\n".join(l for l in lines if l is not None)
