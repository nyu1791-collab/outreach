"""相手のサイト内容から1社ごとの営業文を作る。キー無しならテンプレ差し込み。"""
from pathlib import Path

from . import llm

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "message.md"


def write(lead: dict, cfg: dict) -> dict:
    s, offer = cfg["sender"], cfg["offer"]
    tmpl = PROMPT.read_text(encoding="utf-8")
    prompt = tmpl.format(
        sender_name=s["name"], sender_company=s.get("company", ""), offer=offer["summary"],
        price=offer.get("price", ""), cta=offer.get("cta", ""), target_name=lead["name"],
        target_url=lead["url"], hook=lead.get("hook", ""), target_text=lead.get("summary", "")[:5000], max_chars=cfg.get("max_chars", 500),
    )
    res = llm.ask(prompt, json_mode=True)
    if res:
        return {"subject": res.get("subject", ""), "body": res.get("body", "") + footer(cfg)}
    body = (
        f"{lead['name']} ご担当者様\n\n突然のご連絡失礼いたします。{s.get('company','')}の{s['name']}と申します。\n"
        f"貴社サイトを拝見し、{offer['summary']}でお力になれると考えご連絡しました。\n{offer.get('cta','')}\n"
    )
    return {"subject": offer.get("subject", "ご提案のご連絡"), "body": body + footer(cfg)}


def footer(cfg: dict) -> str:
    s = cfg["sender"]
    lines = ["", "――――――――――", f"{s.get('company','')} {s['name']}", s.get("email", ""), s.get("url", ""),
             cfg.get("optout", "今後のご連絡が不要な場合はお手数ですがその旨ご返信ください。以後お送りいたしません。")]
    return "\n".join(l for l in lines if l is not None)
