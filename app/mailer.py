"""Send email through any SMTP service (Brevo now; switching only means new settings).

Settings come from the environment, never from code:
    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD
    MAIL_FROM    the address emails are sent from (must be verified with the provider)
    REPORT_TO    where "Report a problem" messages go

Uses only Python's standard library, so there is no provider SDK to lock us in.
"""

import os
import smtplib
from email.message import EmailMessage

SMTP_TIMEOUT_SECONDS = 20


class MailNotConfigured(Exception):
    """Raised when the SMTP settings are missing, e.g. on a laptop without .env values."""


def settings() -> dict[str, str]:
    names = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "REPORT_TO"]
    values = {}
    for name in names:
        value = os.environ.get(name)
        if not value:
            raise MailNotConfigured(f"{name} is not set")
        values[name] = value
    values["SMTP_PORT"] = os.environ.get("SMTP_PORT", "587")
    return values


def send_email(to: str, subject: str, body: str, reply_to: str | None = None) -> None:
    """Send one plain-text email. Raises MailNotConfigured or smtplib/OSError on failure."""
    config = settings()
    message = EmailMessage()
    message["From"] = config["MAIL_FROM"]
    message["To"] = to
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body)

    with smtplib.SMTP(config["SMTP_HOST"], int(config["SMTP_PORT"]), timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.starttls()
        smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
        smtp.send_message(message)


def send_problem_report(page: str, message: str, reply_email: str | None) -> None:
    """Email a "Report a problem" message to REPORT_TO. Nothing is stored."""
    to = settings()["REPORT_TO"]
    lines = [f"Page: {page or '(not given)'}", f"Reply to: {reply_email or '(no email given)'}", "", message]
    send_email(to, "Problem report from the scholarship site", "\n".join(lines), reply_to=reply_email)
