"""
Sending email (password reset links) over SMTP, set in .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
MAIL_FROM. Works with Gmail (an app password) locally and any email service with SMTP in the cloud.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage


def is_configured():
    return bool(os.getenv("SMTP_HOST"))


def send_email(to, subject, text):
    """Send a plain-text email. Raises on failure (callers log it; the creator never sees SMTP details)."""
    host, port = os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT") or 587)
    user, password = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM") or user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    context = ssl.create_default_context()
    if port == 465:  # SSL from the start
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as s:
            if user:
                s.login(user, password)
            s.send_message(msg)
    else:  # 587 / 25: plain connection upgraded with STARTTLS
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=context)
            if user:
                s.login(user, password)
            s.send_message(msg)
