"""Gmail の下書きフォルダへ直接保存（IMAP APPEND）。送信は人間が Gmail 上でワンクリック。"""
import imaplib
import os
import time
from email.header import Header
from email.mime.text import MIMEText


def save_draft(to: str, subject: str, body: str):
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = str(Header(subject, "utf-8")), user, to
    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(user, pw)
        box = os.getenv("GMAIL_DRAFTS", "[Gmail]/Drafts")
        status, _ = imap.append(f'"{box}"', r"\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if status != "OK":
            raise RuntimeError(f"Gmail の下書き保存に失敗しました（IMAP APPEND: {status}）。下書きフォルダ名を確認してください")
