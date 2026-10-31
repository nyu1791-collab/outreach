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

    async def fill_page(self, body, sender):
        from playwright.async_api import Page
        captured = {}
        original_close = None

        async def fixture_goto(page, url, **kwargs):
            await page.set_content('<!doctype html><html lang="ja"><meta charset="utf-8"><body>' + body + "</body></html>")
            captured["page"] = page

        with tempfile.TemporaryDirectory() as tmp, patch.object(filler, "SHOTS", Path(tmp)), \
                patch.object(Page, "goto", fixture_goto):
            from playwright.async_api import Browser
            original_close = Browser.close

            async def keep_values(browser):
                captured["values"] = await captured["page"].evaluate(
                    "() => Object.fromEntries([...document.querySelectorAll('input,select,textarea')].map(e => [e.name, e.type === 'checkbox' ? e.checked : e.value]))")
                await original_close(browser)

            with patch.object(Browser, "close", keep_values):
                result = await filler.fill_heuristic("https://unit.test/contact", {"sender": sender, "auto_submit": False},
                                                     {"subject": "件名", "body": "本文"}, "unit", headless=True)
        return result, captured["values"]

    async def test_split_names_prefecture_and_unmatched_select(self):
        body = (
            '<form><table>'
            '<tr><th>姓</th><td><input name="name_sei"></td><th>名</th><td><input name="name_mei"></td></tr>'
            '<tr><th>フリガナ（姓）</th><td><input name="kana1"></td><th>フリガナ（名）</th><td><input name="kana2"></td></tr>'
            '<tr><th>会社名</th><td><input name="company"></td></tr>'
            '<tr><th>都道府県</th><td><select name="pref"><option value="">選択</option>'
            + "".join(f"<option>{p}</option>" for p in filler.PREFS) + '</select></td></tr>'
            '<tr><th>ご用件</th><td><select name="kind"><option value="">選択</option><option>資料請求</option><option>採用</option></select></td></tr>'
            '<tr><th>メール</th><td><input type="email" name="mail"></td></tr>'
            '<tr><th>内容</th><td><textarea name="body"></textarea></td></tr></table></form>')
        sender = {"name": "山田 太郎", "kana": "ヤマダ タロウ", "company": "山田商事", "email": "a@unit.test", "address": "東京都渋谷区1-1"}
        (status, filled), v = await self.fill_page(body, sender)
        self.assertEqual(status, "filled")
        self.assertEqual((v["name_sei"], v["name_mei"], v["kana1"], v["kana2"]), ("山田", "太郎", "ヤマダ", "タロウ"))
        self.assertEqual(v["company"], "山田商事")
        self.assertEqual(v["pref"], "東京都")
        self.assertEqual(v["kind"], "")  # 当てはまらない選択肢は選ばない（末尾の「採用」を選ばない）
        self.assertEqual(v["body"], "本文")


if __name__ == "__main__":
    unittest.main()
