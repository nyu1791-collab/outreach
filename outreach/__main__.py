"""使い方: python -m outreach <command>
  discover "渋谷 美容室" -n 20   検索で候補サイトを追加
  add URL [--name 名前]          1件追加 / import leads.csv で一括
  scrape                          サイト解析（連絡先・本文）
  write                           AIで営業文を生成
  research                        連絡先なし/SNSのみの相手を browser-use AI が調査
  fill [--agent] [--headless]     フォーム自動入力（既定は人間が最終送信。難しいフォームは自動で AI に切替）
  drafts                          メールアドレスがある先は Gmail 下書きに保存
  run                             scrape→write→fill を一気に
  export-dm                       DM 下書き（dm_ready）を data/dm_<campaign>.csv に書き出す（送信は人）
  mark ID 状態                    結果を記録（例: mark 1a2b3c4d sent / replied / ng）
  status                          件数サマリ
  ※ どのコマンドも --campaign 名（config.yaml の campaigns）で対象を絞る/付ける"""
import argparse
import asyncio
import csv
import hashlib
import os
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from . import scrape, writer  # noqa: E402
from . import store  # noqa: E402
from .store import Table  # noqa: E402

COLS = ["id", "name", "url", "contact_url", "email", "socials", "hook", "summary", "subject", "message", "status", "note", "updated_at", "form_attempted_at", "campaign", "sample"]


def cfg():
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def lid(url):
    return hashlib.md5(url.encode()).hexdigest()[:8]


def add_rows(new, campaign=""):
    t = Table("leads", COLS)
    rows = t.load()
    have = {r["url"].rstrip("/") for r in rows}
    n = 0
    for x in new:
        u = (x.get("url") or "").strip()
        if not u or u.rstrip("/") in have:
            continue
        rows.append({"id": lid(u), "name": x.get("name") or u, "url": u, "status": "new", "updated_at": now(),
                     "campaign": campaign, "sample": x.get("sample", "")})
        have.add(u.rstrip("/")); n += 1
    t.save(rows)
    print(f"+{n}件 追加（合計 {len(rows)}）")


CAMPAIGN = None  # --campaign 指定時はそのキャンペーンの行だけ処理


def step(status_from, status_to, fn, limit, on_error_status="error", in_progress_status=None, attempt_field=None):
    if limit < 0:
        raise ValueError("limitは0以上で指定してください")
    t = Table("leads", COLS)
    rows = t.load()
    todo = [r for r in rows if r["status"] == status_from and (CAMPAIGN is None or r.get("campaign", "") == CAMPAIGN)][:limit]
    for i, r in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {r['name'][:30]}  {r['url']}")
        start_status = in_progress_status(r) if callable(in_progress_status) else in_progress_status
        if start_status:
            r["status"], r["updated_at"] = start_status, now()
            if attempt_field:
                r[attempt_field] = now()
            t.save(rows)  # 副作用の前に保存。中断後の無条件な重複実行を防ぐ。
        try:
            fn(r)
            r["status"] = r.get("_next", status_to)
        except Exception as e:
            r["status"], r["note"] = on_error_status, f"{status_from}: {e}"[:300]
            print(f"  ✗ {e}")
        r.pop("_next", None)
        r["updated_at"] = now()
        t.save(rows)  # 1件ごと保存＝途中で止めても再開できる
    return len(todo)


CFG = {}


def cfg_for(r):
    return writer.campaign(CFG, r.get("campaign") or None)


def do_scrape(r):
    cc = cfg_for(r)
    a = scrape.analyze(r["url"], cc.get("extract_hint", ""), web=cc.get("web_research", True))
    r["contact_url"], r["email"], r["socials"], r["summary"] = a["contact_url"], a["email"], a["socials"], a["text"]
    r["hook"] = a["hook"]
    if a["title"] and (r["name"] == r["url"] or len(r["name"]) > 40):
        r["name"] = a["title"][:60]
    if a["no_sales"]:
        r["_next"], r["note"] = "no_sales", "営業お断り表記あり"
    elif cfg_for(r).get("channel") == "dm":
        pass  # DM は SNS から送るので問い合わせ先が無くてよい
    elif not a["contact_url"] and not a["email"]:
        r["_next"], r["note"] = "no_contact", "フォーム/メール見つからず"
    time.sleep(random.uniform(1, 3))


def do_write(r, c):
    cc = cfg_for(r)
    m = writer.write(r, cc)
    r["subject"], r["message"] = m["subject"], m["body"]
    if cc.get("channel") == "dm":
        r["_next"] = "dm_ready"


def _site(host):
    host = host.lower().removeprefix("www.")
    parts = host.split(".")
    # example.co.jp / example.jp / shop.example.com → 末尾の登録ドメイン部分で比較
    return ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ("co", "or", "ne", "ac", "go", "lg", "ed", "gr", "ad", "com", "net", "org") else ".".join(parts[-2:])


def pick_email(r):
    """サイトと同じドメインのメールだけを宛先候補にする。"""
    from urllib.parse import urlparse
    site = _site(urlparse(r["url"]).netloc)
    for e in (x.strip() for x in r["email"].split(",")):
        if "@" in e and _site(e.rsplit("@", 1)[1]) == site:
            return e
    return ""


def nonnegative_int(value):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("0以上の整数で指定してください")
    if result < 0:
        raise argparse.ArgumentTypeError("0以上の整数で指定してください")
    return result


def main():
    ap = argparse.ArgumentParser(prog="outreach", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("discover"); d.add_argument("query"); d.add_argument("-n", type=nonnegative_int, default=20)
    a = sp.add_parser("add"); a.add_argument("url"); a.add_argument("--name", default=""); a.add_argument("--sample", default="")
    im = sp.add_parser("import"); im.add_argument("csv")
    sp.add_parser("export-dm")
    mk = sp.add_parser("mark"); mk.add_argument("id"); mk.add_argument("state")
    for name in ("scrape", "research", "write", "fill", "drafts", "run"):
        p = sp.add_parser(name); p.add_argument("--limit", type=nonnegative_int, default=50)
        if name in ("fill", "run"):
            p.add_argument("--agent", action="store_true", help="browser-use AIエージェントで入力")
            p.add_argument("--headless", action="store_true", help="画面なし（スクショのみ・送信しない）")
    sp.add_parser("status")
    sp.add_parser("llm-check", help="Gemini 等の接続確認")
    for sub in sp.choices.values():
        sub.add_argument("--campaign", default=None, help="config.yaml の campaigns の名前")
    args = ap.parse_args()
    if getattr(args, "limit", None) == 0 or (args.cmd == "discover" and args.n == 0):
        return
    if args.cmd == "llm-check":
        from . import llm
        return llm.check()
    global CAMPAIGN
    c = cfg()
    CFG.clear(); CFG.update(c)
    scrape.COOKIES.update(c.get("cookies") or {})
    if args.campaign and args.campaign not in (c.get("campaigns") or {}):
        ap.error(f"campaigns に {args.campaign} がありません: {', '.join(c.get('campaigns') or {})}")
    CAMPAIGN = args.campaign
    new_campaign = args.campaign or c.get("default_campaign", "")

    if args.cmd == "discover":
        add_rows(scrape.discover(args.query, args.n), new_campaign)
    elif args.cmd == "add":
        add_rows([{"url": args.url, "name": args.name, "sample": args.sample}], new_campaign)
    elif args.cmd == "import":
        rows = None
        for enc in ("utf-8-sig", "cp932"):  # Excel保存の Shift_JIS も読める
            try:
                with open(args.csv, encoding=enc, newline="") as f:
                    rows = list(csv.DictReader(f))
                break
            except UnicodeDecodeError:
                continue
        if rows is None:
            ap.error("CSV は UTF-8 または CP932 で保存してください")
        # 列名ゆれ吸収（URL/url/ホームページ, 会社名/name 等）
        norm = lambda r: {"url": next((v for k, v in r.items() if k and k.strip().lower() in ("url", "ホームページ", "website", "サイト")), ""),
                          "name": next((v for k, v in r.items() if k and k.strip().lower() in ("name", "会社名", "企業名", "店舗名", "名前")), "")}
        add_rows([dict(norm(r), sample=r.get("sample", "")) for r in rows], new_campaign)
    if args.cmd in ("scrape", "run"):
        step("new", "scraped", do_scrape, args.limit)
    if args.cmd == "research":
        from . import agent

        def do_research(r):
            info = asyncio.run(agent.research(r))
            if not info:
                r["_next"] = "no_contact"; return
            r["email"] = r["email"] or info.email
            r["contact_url"] = r["contact_url"] or info.contact_url
            r["socials"] = " ".join(dict.fromkeys(r["socials"].split() + [p.profile_url for p in info.profiles]))
            r["hook"] = " / ".join(x for x in (r["hook"], info.recent_activity, info.audience) if x)
            r["note"] = info.note[:200]
            r["_next"] = "scraped" if (r["email"] or r["contact_url"]) else "no_contact"
        step("no_contact", "scraped", do_research, args.limit)
    if args.cmd in ("write", "run"):
        step("scraped", "written", lambda r: do_write(r, c), args.limit)
    if args.cmd in ("fill", "run"):
        from . import filler

        def do_fill(r):
            c = cfg_for(r)
            if not r["contact_url"]:
                r["_next"] = "mail_only" if r["email"] else "no_contact"; return
            msg = {"subject": r["subject"], "body": r["message"]}
            note = ""
            res, n = ("retry_agent", 0) if args.agent else asyncio.run(
                filler.fill_heuristic(r["contact_url"], c, msg, r["id"], headless=args.headless))
            if res == "retry_agent":
                if not os.getenv("GEMINI_API_KEY"):
                    r["_next"], r["note"] = "error", "フォーム項目を特定できず（GEMINI_API_KEY を入れると AI が入力）"; return
                from . import agent
                print("  → browser-use AI エージェントで入力")
                res, n, note = asyncio.run(agent.fill_form(r["contact_url"], c, msg, wait_human=not args.headless,
                                                           headless=args.headless))
            r["_next"], r["note"] = res, f"入力{n}項目 {note}".strip()
            time.sleep(c.get("interval_sec", 5))
        today = datetime.now().strftime("%Y-%m-%d")
        done_today = sum(1 for r in Table("leads", COLS).load()
                         if r.get("form_attempted_at", "").startswith(today) or
                         (not r.get("form_attempted_at") and r["status"] in ("filled", "sent") and r["updated_at"].startswith(today)))
        left = max(0, c.get("daily_limit", 30) - done_today)
        if left == 0:
            print(f"本日の上限 {c.get('daily_limit', 30)} 件に達しています（config.yaml の daily_limit）")
        step("written", "filled", do_fill, min(args.limit, left), on_error_status="fill_uncertain",
             in_progress_status=lambda r: "filling" if r["contact_url"] else None,
             attempt_field="form_attempted_at")
    if args.cmd == "drafts":
        from . import mail

        def do_draft(r):
            to = pick_email(r)
            if not to:  # サイト制作会社のクレジット等、相手以外の可能性があるアドレスには自動で作らない
                r["_next"], r["note"] = "mail_check", f"サイトと別ドメインのアドレスのみ（{r['email']}）。相手のものか確認して email 列を直す"
                return
            try:
                mail.save_draft(to, r["subject"], r["message"])
            except mail.DraftUncertain as exc:
                r["_next"], r["note"] = "draft_uncertain", str(exc)
                return
            r["_next"] = "drafted"
            r["note"] = ""
        step("mail_only", "drafted", do_draft, args.limit, on_error_status="mail_only", in_progress_status="drafting")
    if args.cmd == "export-dm":
        rows = [r for r in Table("leads", COLS).load() if r["status"] == "dm_ready" and (CAMPAIGN is None or r["campaign"] == CAMPAIGN)]
        out = store.DATA / f"dm_{CAMPAIGN or 'all'}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "名前", "URL", "SNS", "添付サンプル", "メッセージ"])
            for r in rows:
                w.writerow([r["id"], r["name"], r["url"], r["socials"], r["sample"], r["message"]])
        print(f"{len(rows)}件 → {out}\n送ったら: python -m outreach mark <id> sent")
    if args.cmd == "mark":
        t = Table("leads", COLS)
        rows = t.load()
        hit = [r for r in rows if r["id"] == args.id]
        if not hit:
            ap.error(f"id {args.id} がありません")
        hit[0]["status"], hit[0]["updated_at"] = args.state, now()
        t.save(rows)
        print(f"{args.id} → {args.state}")
    if args.cmd == "status":
        rows = Table("leads", COLS).load()
        for camp in sorted({r.get("campaign", "") for r in rows}):
            print(f"[{camp or '-'}]", dict(Counter(r["status"] for r in rows if r.get("campaign", "") == camp)))


if __name__ == "__main__":
    main()
