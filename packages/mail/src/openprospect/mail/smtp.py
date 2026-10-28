"""Plain SMTP sending for individually written emails (the job track). The agency sequence
goes through Listmonk instead; see sequence.py."""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid


class SendingLimitReached(Exception):
    """The provider refused more mail today. Stop and try tomorrow."""


# Daily-quota answers from common providers: Gmail 5.4.5, Outlook/Microsoft 365 5.7.708 / "sending limit",
# Zoho / Yahoo / generic "daily limit" or "quota exceeded" wording.
LIMIT_RE = re.compile(
    r"5\.4\.5|5\.7\.708|sending limit|daily (user )?(sending )?limit|quota exceeded|too many messages", re.I
)


def send_plain(
    host: str, port: int, user: str, password: str, sender_name: str, to: str, subject: str, body: str
) -> None:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, user)) if sender_name else user
    msg["To"] = to.strip()
    msg["Subject"] = subject.strip()
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1] or None)
    msg.set_content(body.strip() + "\n")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=60) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
    except smtplib.SMTPException as e:
        if LIMIT_RE.search(str(e)):
            raise SendingLimitReached(str(e)) from e
        raise
