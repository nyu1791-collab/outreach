"""使い方: python -m outreach <command>
  discover "渋谷 美容室" -n 20   検索で候補サイトを追加
  add URL [--name 名前]          1件追加 / import leads.csv で一括
  scrape                          サイト解析（連絡先・本文）
  write                           AIで営業文を生成
  fill [--agent] [--headless]     フォーム自動入力（既定は人間が最終送信）
  drafts                          メールアドレスがある先は Gmail 下書きに保存
  run                             scrape→write→fill を一気に
  status                          件数サマリ"""
import argparse
import asyncio
import csv
import hashlib
import random
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from . import scrape, writer  # noqa: E402
from .store import Table  # noqa: E402

COLS = ["id", "name", "url", "contact_url", "email", "socials", "summary", "subject", "message", "status", "note", "updated_at"]


def cfg():
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def lid(url):
    return hashlib.md5(url.encode()).hexdigest()[:8]


def add_rows(new):
    t = Table("leads", COLS)
    rows = t.load()
    have = {r["url"].rstrip("/") for r in rows}
    n = 0
    for x in new:
        u = x["url"].strip()
        if not u or u.rstrip("/") in have:
            continue
        rows.append({"id": lid(u), "name": x.get("name") or u, "url": u, "status": "new", "updated_at": now()})
        have.add(u.rstrip("/")); n += 1
    t.save(rows)
    print(f"+{n}件 追加（合計 {len(rows)}）")


def step(status_from, status_to, fn, limit):
    t = Table("leads", COLS)
    rows = t.load()
    todo = [r for r in rows if r["status"] == status_from][:limit]
    for i, r in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {r['name'][:30]}  {r['url']}")
        try:
            fn(r)
            r["status"] = r.get("_next", status_to)
        except Exception as e:
            r["status"], r["note"] = "error", f"{status_from}: {e}"[:300]
            print(f"  ✗ {e}")
        r.pop("_next", None)
        r["updated_at"] = now()
        t.save(rows)  # 1件ごと保存＝途中で止めても再開できる
    return len(todo)


def do_scrape(r):
    a = scrape.analyze(r["url"])
    r["contact_url"], r["email"], r["socials"], r["summary"] = a["contact_url"], a["email"], a["socials"], a["text"]
    if r["name"] == r["url"] and a["title"]:
        r["name"] = a["title"][:60]
    if not a["contact_url"] and not a["email"]:
        r["_next"], r["note"] = "no_contact", "フォーム/メール見つからず"
    time.sleep(random.uniform(1, 3))


def do_write(r, c):
    m = writer.write(r, c)
    r["subject"], r["message"] = m["subject"], m["body"]


def main():
    ap = argparse.ArgumentParser(prog="outreach", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("discover"); d.add_argument("query"); d.add_argument("-n", type=int, default=20)
    a = sp.add_parser("add"); a.add_argument("url"); a.add_argument("--name", default="")
    im = sp.add_parser("import"); im.add_argument("csv")
    for name in ("scrape", "write", "fill", "drafts", "run"):
        p = sp.add_parser(name); p.add_argument("--limit", type=int, default=50)
        if name in ("fill", "run"):
            p.add_argument("--agent", action="store_true", help="browser-use AIエージェントで入力")
            p.add_argument("--headless", action="store_true", help="画面なし（スクショのみ・送信しない）")
    sp.add_parser("status")
    args = ap.parse_args()
    c = cfg()

    if args.cmd == "discover":
        add_rows(scrape.discover(args.query, args.n))
    elif args.cmd == "add":
        add_rows([{"url": args.url, "name": args.name}])
    elif args.cmd == "import":
        with open(args.csv, encoding="utf-8-sig") as f:
            add_rows(list(csv.DictReader(f)))
    if args.cmd in ("scrape", "run"):
        step("new", "scraped", do_scrape, args.limit)
    if args.cmd in ("write", "run"):
        step("scraped", "written", lambda r: do_write(r, c), args.limit)
    if args.cmd in ("fill", "run"):
        from . import filler

        def do_fill(r):
            if not r["contact_url"]:
                r["_next"] = "mail_only" if r["email"] else "no_contact"; return
            msg = {"subject": r["subject"], "body": r["message"]}
            if args.agent:
                res, n = asyncio.run(filler.fill_agent(r["contact_url"], c, msg))
            else:
                res, n = asyncio.run(filler.fill_heuristic(r["contact_url"], c, msg, r["id"], headless=args.headless))
            r["_next"], r["note"] = res, f"入力{n}項目"
            time.sleep(c.get("interval_sec", 5))
        step("written", "filled", do_fill, min(args.limit, c.get("daily_limit", 30)))
    if args.cmd == "drafts":
        from . import mail

        def do_draft(r):
            mail.save_draft(r["email"].split(",")[0].strip(), r["subject"], r["message"])
            r["_next"] = "drafted"
        step("mail_only", "drafted", do_draft, args.limit)
    if args.cmd == "status":
        print(dict(Counter(r["status"] for r in Table("leads", COLS).load())))


if __name__ == "__main__":
    main()
