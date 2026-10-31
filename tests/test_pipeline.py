"""Network-free regression checks for import and resumable Gmail drafts."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from outreach import __main__ as cli
from outreach import mail, store


class PipelineTests(unittest.TestCase):
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

    def run_cli(self, *args):
        with patch.object(sys, "argv", ["outreach", *args]), patch.object(cli, "cfg", return_value={}), contextlib.redirect_stdout(io.StringIO()):
            cli.main()

    def test_import_skips_missing_url_and_accepts_cp932_headers(self):
        source = self.root / "targets.csv"
        source.write_text("会社名,URL\nURL欠損\n店舗A,https://unit.test/\n", encoding="cp932")
        self.run_cli("import", str(source))
        rows = store.Table("leads", cli.COLS).load()
        self.assertEqual([(r["name"], r["url"]) for r in rows], [("店舗A", "https://unit.test/")])

    def test_import_reports_unsupported_encoding(self):
        source = self.root / "targets.csv"
        source.write_bytes(b"name,url\n\x81")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            self.run_cli("import", str(source))
        self.assertEqual(raised.exception.code, 2)

    def test_rejected_gmail_append_is_not_success(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.append.return_value = ("NO", [b"no such mailbox"])
        with patch.dict(os.environ, {"GMAIL_USER": "sender@unit.test", "GMAIL_APP_PASSWORD": "test-only"}), patch("imaplib.IMAP4_SSL", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "IMAP APPEND: NO"):
                mail.save_draft("target@unit.test", "Test", "Draft")

    def test_failed_draft_is_retried_on_next_command(self):
        table = store.Table("leads", cli.COLS)
        table.save([{"id": "unit", "name": "Company", "url": "https://unit.test/", "email": "target@unit.test", "subject": "Test", "message": "Draft", "status": "mail_only"}])
        with patch.object(mail, "save_draft", side_effect=RuntimeError("APPEND rejected")):
            self.run_cli("drafts")
        row = table.load()[0]
        self.assertEqual(row["status"], "mail_only")
        self.assertIn("APPEND rejected", row["note"])
        with patch.object(mail, "save_draft") as saved:
            self.run_cli("drafts")
        saved.assert_called_once_with("target@unit.test", "Test", "Draft")
        row = table.load()[0]
        self.assertEqual(row["status"], "drafted")
        self.assertEqual(row["note"], "")


if __name__ == "__main__":
    unittest.main()
