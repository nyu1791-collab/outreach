"""Review regressions: durable side effects, limits, and storage preservation; no network."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from outreach import __main__ as cli
from outreach import filler, mail, scrape, store


class ReviewSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data_patch = patch.object(store, "DATA", self.root / "data")
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)
        self.env_patch = patch.dict(os.environ, {"GOOGLE_SHEET_ID": ""})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.table = store.Table("leads", cli.COLS)

    def run_cli(self, *args, config=None):
        with patch.object(sys, "argv", ["outreach", *args]), patch.object(cli, "cfg", return_value=config or {}), contextlib.redirect_stdout(io.StringIO()):
            cli.main()

    def lead(self, index="one", status="written"):
        return {"id": index, "name": "Company", "url": f"https://unit.test/{index}",
                "contact_url": "https://unit.test/contact", "email": "target@unit.test",
                "subject": "Test", "message": "Draft", "status": status}

    def test_negative_limits_are_rejected_before_configuration_or_side_effects(self):
        commands = [(name, "--limit", "-1") for name in ("scrape", "research", "write", "fill", "drafts", "run")]
        commands.append(("discover", "query", "-n", "-1"))
        for args in commands:
            with self.subTest(args=args), patch.object(cli, "cfg") as config, patch.object(sys, "argv", ["outreach", *args]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli.main()
            self.assertEqual(raised.exception.code, 2)
            config.assert_not_called()

    def test_zero_limits_are_noop_including_optional_agent_command(self):
        commands = [(name, "--limit", "0") for name in ("scrape", "research", "write", "fill", "drafts", "run")]
        commands.append(("discover", "query", "-n", "0"))
        for args in commands:
            with self.subTest(args=args), patch.object(cli, "cfg") as config, patch.object(sys, "argv", ["outreach", *args]):
                cli.main()
            config.assert_not_called()

    def test_csv_write_failure_preserves_previous_history_and_cleans_temp(self):
        self.table.save([self.lead(status="sent")])
        original = self.table.path.read_bytes()
        broken_writer = MagicMock()
        broken_writer.writerows.side_effect = OSError("disk full")
        with patch.object(store.csv, "writer", return_value=broken_writer), self.assertRaises(OSError):
            self.table.save([self.lead(status="written")])
        self.assertEqual(self.table.path.read_bytes(), original)
        self.assertEqual(list(self.table.path.parent.glob("*.tmp")), [])

    def test_csv_replace_failure_preserves_previous_history(self):
        self.table.save([self.lead(status="sent")])
        original = self.table.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("Excel has the file open")), self.assertRaises(PermissionError):
            self.table.save([self.lead(status="written")])
        self.assertEqual(self.table.path.read_bytes(), original)
        self.assertEqual(list(self.table.path.parent.glob("*.tmp")), [])

    def test_sheets_replaces_data_and_trailing_rows_in_one_update_without_clear(self):
        sheet = MagicMock()
        sheet.get_all_values.return_value = [["id", "status", "old"], ["one", "sent", "legacy"], ["two", "sent", "legacy"]]
        table = store.Table("sheet", ["id", "status"])
        table.ws = sheet
        table.save([{"id": "new", "status": "written"}])
        sheet.clear.assert_not_called()
        sheet.update.assert_called_once_with([["id", "status", ""], ["new", "written", ""], ["", "", ""]], "A1")

    def test_sheets_update_failure_does_not_clear_previous_rows(self):
        sheet = MagicMock()
        sheet.get_all_values.return_value = [["id"], ["existing"]]
        sheet.update.side_effect = OSError("response lost")
        self.table.ws = sheet
        with self.assertRaises(OSError):
            self.table.save([])
        sheet.clear.assert_not_called()

    def test_form_interruption_is_persisted_before_side_effect_and_not_repeated(self):
        self.table.save([self.lead()])
        calls = []

        async def interrupted(*args, **kwargs):
            saved = self.table.load()[0]
            self.assertEqual(saved["status"], "filling")
            self.assertTrue(saved["form_attempted_at"])
            calls.append(args[3])
            raise KeyboardInterrupt()

        with patch.object(filler, "fill_heuristic", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_cli("fill", "--headless", config={"daily_limit": 3, "interval_sec": 0})
            self.run_cli("fill", "--headless", config={"daily_limit": 3, "interval_sec": 0})
        self.assertEqual(calls, ["one"])
        self.assertEqual(self.table.load()[0]["status"], "filling")

    def test_skipped_form_attempts_still_consume_daily_limit_across_runs(self):
        self.table.save([self.lead(str(index)) for index in range(4)])

        async def skipped(*args, **kwargs):
            return "skipped", 2

        with patch.object(filler, "fill_heuristic", side_effect=skipped) as fill:
            self.run_cli("fill", "--headless", config={"daily_limit": 2, "interval_sec": 0})
            self.run_cli("fill", "--headless", config={"daily_limit": 2, "interval_sec": 0})
        self.assertEqual(fill.call_count, 2)
        self.assertEqual(sum(row["status"] == "written" for row in self.table.load()), 2)

    def test_draft_interruption_is_persisted_before_append_and_not_repeated(self):
        self.table.save([self.lead(status="mail_only")])

        def interrupted(*args):
            self.assertEqual(self.table.load()[0]["status"], "drafting")
            raise KeyboardInterrupt()

        with patch.object(mail, "save_draft", side_effect=interrupted) as save:
            with self.assertRaises(KeyboardInterrupt):
                self.run_cli("drafts")
            self.run_cli("drafts")
        self.assertEqual(save.call_count, 1)
        self.assertEqual(self.table.load()[0]["status"], "drafting")

    def test_uncertain_append_is_held_for_review_without_automatic_retry(self):
        self.table.save([self.lead(status="mail_only")])
        with patch.object(mail, "save_draft", side_effect=mail.DraftUncertain("check Gmail")) as save:
            self.run_cli("drafts")
            self.run_cli("drafts")
        self.assertEqual(save.call_count, 1)
        saved = self.table.load()[0]
        self.assertEqual(saved["status"], "draft_uncertain")
        self.assertIn("check Gmail", saved["note"])

    def test_append_response_loss_is_classified_as_uncertain(self):
        connection = MagicMock()
        connection.append.side_effect = OSError("connection lost after APPEND")
        with patch.dict(os.environ, {"GMAIL_USER": "sender@unit.test", "GMAIL_APP_PASSWORD": "test-only"}), patch.object(mail.imaplib, "IMAP4_SSL", return_value=connection), self.assertRaises(mail.DraftUncertain):
            mail.save_draft("target@unit.test", "Test", "Draft")
        connection.logout.assert_called_once()

    def test_logout_failure_after_confirmed_append_does_not_invalidate_success(self):
        connection = MagicMock()
        connection.append.return_value = ("OK", [b"saved"])
        connection.logout.side_effect = OSError("disconnect")
        with patch.dict(os.environ, {"GMAIL_USER": "sender@unit.test", "GMAIL_APP_PASSWORD": "test-only"}), patch.object(mail.imaplib, "IMAP4_SSL", return_value=connection):
            mail.save_draft("target@unit.test", "Test", "Draft")

    def test_unrecognized_append_status_is_not_treated_as_a_definite_rejection(self):
        connection = MagicMock()
        connection.append.return_value = ("BYE", [b"connection closed"])
        with patch.dict(os.environ, {"GMAIL_USER": "sender@unit.test", "GMAIL_APP_PASSWORD": "test-only"}), patch.object(mail.imaplib, "IMAP4_SSL", return_value=connection), self.assertRaises(mail.DraftUncertain):
            mail.save_draft("target@unit.test", "Test", "Draft")

    def test_no_sales_detection_handles_particles_compound_words_and_line_breaks(self):
        prohibited = ["営業目的でのお問い合わせはご遠慮ください", "営業目的の\nお問い合わせは\nお断りします",
                      "営業・勧誘目的のお問い合わせはお断りします", "セールスの電話は固くお断りします"]
        for text in prohibited:
            with self.subTest(text=text):
                self.assertTrue(scrape.has_no_sales_notice(text))
        for text in ("営業目的のお問い合わせは歓迎します", "営業目的以外のお問い合わせは禁止です", "営業時間のお問い合わせはこちら"):
            with self.subTest(text=text):
                self.assertFalse(scrape.has_no_sales_notice(text))

    def test_site_analysis_uses_shared_no_sales_detection_without_llm(self):
        text = "営業目的でのお問い合わせはご遠慮ください"
        with patch.object(scrape.fc, "client", return_value=None), patch.object(scrape, "_local", return_value=(text, [], "Company", {}, False, "")), patch.object(scrape.llm, "ask", return_value=None):
            self.assertTrue(scrape.analyze("https://unit.test")["no_sales"])


if __name__ == "__main__":
    unittest.main()
