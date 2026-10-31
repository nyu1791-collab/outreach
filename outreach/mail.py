"""Gmail の下書きフォルダへ直接保存（IMAP APPEND）。送信は人間が Gmail 上でワンクリック。"""
import imaplib
import os
import time
from email.header import Header
from email.mime.text import MIMEText


class DraftRejected(RuntimeError):
    """IMAPが保存を明示的に拒否した。再試行してよい。"""


class DraftUncertain(RuntimeError):
    """APPENDの応答が不明。保存済みかGmail上で確認する必要がある。"""


def save_draft(to: str, subject: str, body: str):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = str(Header(subject, "utf-8")), user, to
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(user, pw)
        box = os.getenv("GMAIL_DRAFTS", "[Gmail]/Drafts")
        try:
            status, _ = imap.append(f'"{box}"', r"\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        except Exception as exc:
            raise DraftUncertain("Gmailの下書き保存結果が不明です。Gmail上で保存の有無を確認してください") from exc
        if status in ("NO", "BAD"):
            raise DraftRejected(f"Gmail の下書き保存に失敗しました（IMAP APPEND: {status}）。下書きフォルダ名を確認してください")
        if status != "OK":
            raise DraftUncertain(f"Gmailの下書き保存結果を解釈できません（IMAP APPEND: {status}）。Gmail上で確認してください")
    finally:
        # 保存成功後の切断失敗を、保存失敗として自動再試行しない。
        try:
            imap.logout()
        except Exception:
            pass
