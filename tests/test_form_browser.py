"""Opt-in real Chromium checks, using in-memory HTML and no external delivery.

OUTREACH_BROWSER_TESTS=1 CHROME_PATH=/usr/bin/chromium python -m unittest discover -s tests -v
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from outreach import filler


@unittest.skipUnless(os.getenv("OUTREACH_BROWSER_TESTS") == "1" and importlib.util.find_spec("playwright"), "opt-in local Chromium checks")
class FormBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, notice="", completion="", auto_submit=True):
        from playwright.async_api import Page

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = (
                '<!doctype html><html lang="ja"><meta charset="utf-8"><body>'
                f'<p>{notice}</p><form><label>メール<input type="email" name="email"></label>'
                '<textarea name="message"></textarea><button type="submit">確認</button></form>'
                '<script>document.querySelector("form").addEventListener("submit", event => {'
                f'event.preventDefault(); document.body.innerHTML = "<p>{completion}</p>";'
                '});</script></body></html>'
            )

            async def fixture_goto(page, url, **kwargs):
                self.assertEqual(url, "https://unit.test/contact")
                await page.set_content(html)

            config = {"sender": {"name": "Test", "email": "sender@unit.test"}, "auto_submit": auto_submit}
            with patch.object(filler, "SHOTS", root / "shots"), patch.object(Page, "goto", fixture_goto):
                return await filler.fill_heuristic("https://unit.test/contact", config, {"subject": "Test", "body": "Draft only"}, "unit", headless=True)

    async def test_no_sales_on_contact_page_stops_before_input(self):
        self.assertEqual(await self.run_fixture(notice="営業目的のお問い合わせはお断りします"), ("no_sales", 0))

    async def test_multiline_sales_notice_stops_before_input(self):
        self.assertEqual(await self.run_fixture(notice="営業・勧誘目的での<br>お問い合わせは<br>ご遠慮ください"), ("no_sales", 0))

    async def test_confirmation_page_is_not_sent(self):
        self.assertEqual(await self.run_fixture(completion="入力内容をご確認ください"), ("filled", 2))

    async def test_new_completion_screen_is_sent(self):
        self.assertEqual(await self.run_fixture(completion="送信が完了しました。"), ("sent", 2))

    async def test_preexisting_completion_phrase_cannot_confirm_delivery(self):
        self.assertEqual(await self.run_fixture(notice="前回の送信が完了しました。", completion="入力内容をご確認ください"), ("filled", 2))


if __name__ == "__main__":
    unittest.main()
