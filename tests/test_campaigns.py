"""キャンペーン（営業先の種類）ごとの提案・チャネル切替。外部通信なし。"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from outreach import __main__ as cli
from outreach import scrape, store, writer

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(store, "DATA", Path(self.tmp.name)), patch.dict(os.environ, {"GOOGLE_SHEET_ID": "", "GEMINI_API_KEY": "",
                                                                                          "OPENROUTER_API_KEY": "", "LLM_PROVIDER": ""})):
            p.start(); self.addCleanup(p.stop)

    def run_cli(self, *args):
        out = io.StringIO()
        with patch.object(sys, "argv", ["outreach", *args]), patch.object(cli, "cfg", return_value=CFG), contextlib.redirect_stdout(out):
            cli.main()
        return out.getvalue()

    def test_campaign_overrides_offer_and_channel(self):
        c = writer.campaign(CFG, "doujin")
        self.assertEqual(c["channel"], "dm")
        self.assertIn("英語版", c["offer"]["short"])
        self.assertEqual(c["sender"], CFG["sender"])
        self.assertEqual(writer.campaign(CFG, None)["campaign"], "sales-csv")

    def test_dm_campaign_flow_and_filtering(self):
        analyzed = {"title": "サークルA", "contact_url": "", "email": "", "socials": "https://x.com/a", "hook": "新作が好評",
                    "no_sales": False, "text": "作品の説明"}
        self.run_cli("add", "https://www.dlsite.com/maniax/circle/profile/=/maker_id/RG0001.html", "--campaign", "doujin", "--sample", "out/sample.png")
        self.run_cli("add", "https://shop.example/", "--campaign", "shop-diary")
        with patch.object(scrape, "analyze", return_value=analyzed) as an, patch.object(cli.time, "sleep"):
            self.run_cli("scrape", "--campaign", "doujin")
        self.assertIn("英語", an.call_args[0][1])               # キャンペーンの抽出ヒントが渡る
        self.run_cli("write", "--campaign", "doujin")
        rows = {r["campaign"]: r for r in store.Table("leads", cli.COLS).load()}
        self.assertEqual(rows["doujin"]["status"], "dm_ready")
        self.assertIn("スルー", rows["doujin"]["message"])        # DM 用の短い締め
        self.assertEqual(rows["shop-diary"]["status"], "new")      # 他キャンペーンは触らない
        out = self.run_cli("export-dm", "--campaign", "doujin")
        self.assertIn("1件", out)
        text = (Path(self.tmp.name) / "dm_doujin.csv").read_text(encoding="utf-8-sig")
        self.assertIn("out/sample.png", text)
        self.run_cli("mark", rows["doujin"]["id"], "sent")
        self.assertEqual({r["campaign"]: r["status"] for r in store.Table("leads", cli.COLS).load()}["doujin"], "sent")

    def test_cookies_apply_to_matching_domains(self):
        scrape.COOKIES.update({"dlsite.com": {"adultchecked": "1"}})
        self.assertEqual(scrape._cookies("https://www.dlsite.com/x"), {"adultchecked": "1"})
        self.assertEqual(scrape._cookies("https://example.com/"), {})


if __name__ == "__main__":
    unittest.main()
