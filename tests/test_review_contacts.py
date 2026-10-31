"""見直し: 人の最終確認・宛先メールの選び方・AI応答の形式崩れ（外部通信なし）。"""
import unittest
from unittest.mock import patch

from outreach import __main__ as cli
from outreach import filler, writer

CFG = {"sender": {"name": "山田 太郎", "company": "山田商事", "email": "a@unit.test"},
       "offer": {"summary": "売上集計の自動化", "short": "売上集計ツール", "subject": "既定の件名"}}
LEAD = {"name": "相手", "url": "https://shop.unit.test/", "summary": "", "hook": ""}


class HumanConfirmTests(unittest.IsolatedAsyncioTestCase):
    async def answer(self, *keys):
        with patch("builtins.input", side_effect=list(keys)):
            return await filler.ask_human(3)

    async def test_enter_alone_is_not_sent(self):
        self.assertEqual(await self.answer(""), "filled")

    async def test_explicit_answers(self):
        self.assertEqual(await self.answer("y"), "sent")
        self.assertEqual(await self.answer("s"), "skipped")
        self.assertEqual(await self.answer("x", "y"), "sent")  # 不明な入力は聞き直す


class EmailChoiceTests(unittest.TestCase):
    def test_only_same_site_addresses_are_used(self):
        self.assertEqual(cli.pick_email({"url": "https://www.shop.co.jp/", "email": "design@agency.jp, info@shop.co.jp"}), "info@shop.co.jp")
        self.assertEqual(cli.pick_email({"url": "https://shop.jp/", "email": "web@agency.jp"}), "")
        self.assertEqual(cli.pick_email({"url": "https://a.example.com/", "email": "x@mail.example.com"}), "x@mail.example.com")


class WriterShapeTests(unittest.TestCase):
    def test_bad_ai_output_falls_back_to_template(self):
        for bad in ({"subject": "件名だけ"}, {"body": "短い"}, ["list"], {"body": None}):
            with patch.object(writer.llm, "ask", return_value=bad):
                m = writer.write(LEAD, CFG)
            self.assertIn("売上集計ツール", m["body"], bad)
            self.assertEqual(m["subject"], "既定の件名")

    def test_good_ai_output_keeps_body_and_adds_footer(self):
        body = "相手サイトの具体的な内容に触れた本文です。" * 4
        with patch.object(writer.llm, "ask", return_value={"subject": " 件名 ", "body": body}):
            m = writer.write(LEAD, CFG)
        self.assertEqual(m["subject"], "件名")
        self.assertTrue(m["body"].startswith(body))
        self.assertIn("山田商事", m["body"])


if __name__ == "__main__":
    unittest.main()
