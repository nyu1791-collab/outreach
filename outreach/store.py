"""データ置き場。GOOGLE_SHEET_ID があればスプレッドシート、無ければ data/<name>.csv。
全件読み→編集→全件保存のシンプル設計（数千行までなら十分速い）。"""
import csv
import os
from pathlib import Path

DATA = Path(os.getenv("DATA_DIR", "data"))


class Table:
    def __init__(self, name: str, columns: list[str]):
        self.name, self.columns = name, columns
        self.ws = None
        sid = os.getenv("GOOGLE_SHEET_ID")
        cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        if sid and Path(cred).exists():
            import gspread
            sh = gspread.service_account(filename=cred).open_by_key(sid)
            try:
                self.ws = sh.worksheet(name)
            except gspread.WorksheetNotFound:
                self.ws = sh.add_worksheet(name, rows=1000, cols=len(columns))
                self.ws.append_row(columns)
        self.path = DATA / f"{name}.csv"

    def load(self) -> list[dict]:
        if self.ws:
            rows = self.ws.get_all_records(default_blank="")
        elif self.path.exists():
            with open(self.path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        else:
            rows = []
        return [{c: str(r.get(c, "") or "") for c in self.columns} for r in rows]

    def save(self, rows: list[dict]):
        data = [[r.get(c, "") for c in self.columns] for r in rows]
        if self.ws:
            self.ws.clear()
            self.ws.update([self.columns] + data, "A1")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(self.columns)
            w.writerows(data)
