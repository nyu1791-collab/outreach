"""データ置き場。GOOGLE_SHEET_ID があればスプレッドシート、無ければ data/<name>.csv。
全件読み→編集→全件保存のシンプル設計（数千行までなら十分速い）。"""
import csv
import os
import tempfile
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
            # 更新前にclearすると通信失敗時に全履歴が消える。末尾を含む1回の更新で置換する。
            existing = self.ws.get_all_values()
            width = max([len(self.columns), *(len(row) for row in existing)])
            grid = [self.columns] + data
            grid = [row + [""] * (width - len(row)) for row in grid]
            grid += [[""] * width for _ in range(max(0, len(existing) - len(grid)))]
            rows_now, cols_now = getattr(self.ws, "row_count", None), getattr(self.ws, "col_count", None)
            if isinstance(rows_now, int) and isinstance(cols_now, int) and (len(grid) > rows_now or width > cols_now):
                # シートの既定は1000行。超える更新は範囲外エラーになるので先に広げる
                self.ws.resize(rows=max(len(grid), rows_now), cols=max(width, cols_now))
            self.ws.update(grid, "A1")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, prefix=f".{self.name}-", suffix=".tmp",
                                             encoding="utf-8-sig", newline="", delete=False) as f:
                pending = Path(f.name)
                w = csv.writer(f)
                w.writerow(self.columns)
                w.writerows(data)
                f.flush()
                os.fsync(f.fileno())
            pending.replace(self.path)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
