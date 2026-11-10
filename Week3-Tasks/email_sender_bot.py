#!/usr/bin/env python3
"""
Email Sender Bot
================
Send personalised emails with attachments to a list of recipients read
from a CSV file, using Gmail SMTP (App Password) over smtplib.

Features
--------
* Recipients from CSV - every column becomes a {placeholder} you can use
  in the subject and body (e.g. {name}, {company}).
* File attachments (one or more) with automatic MIME type detection.
* Retry logic with back-off, and automatic reconnect if Gmail drops the
  connection mid-batch.
* Full send-status logging: a human-readable log file AND a CSV report
  (timestamp, email, status, attempts, detail).
* Credentials are NEVER hard-coded: they come from environment
  variables, a local .env file, or a secure password prompt.
* --dry-run mode: builds and validates every email without sending.

Requirements: Python 3.9+ only. No third-party packages.

Quick start
-----------
    export GMAIL_ADDRESS="you@gmail.com"
    export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"   # Gmail App Password
    python email_sender_bot.py --recipients recipients.csv \
        --subject "Your weekly report, {name}" \
        --template message.txt --attach report.pdf

See README.md for the full guide (including how to create a Gmail
App Password).
"""

from __future__ import annotations

import argparse
import csv
import getpass
import logging
import mimetypes
import os
import re
import smtplib
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT_SSL = 465        # implicit TLS (recommended)
GMAIL_PORT_STARTTLS = 587   # used when --starttls is passed

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

STATUS_CSV = "send_status.csv"
LOG_FILE = "email_bot.log"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

class SafeDict(dict):
    """dict that leaves unknown {placeholders} untouched instead of
    raising KeyError, so a typo in the template can't crash a batch."""

    def __missing__(self, key):  # noqa: D102
        return "{" + key + "}"


def personalise(template: str, row: dict) -> str:
    """Replace {column} placeholders in *template* with values from *row*."""
    return template.format_map(SafeDict({k: (v or "") for k, v in row.items()}))


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (KEY=VALUE per line) - no dependency needed.

    Existing environment variables always win, so real env vars can
    override the file.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_credentials() -> tuple[str, str]:
    """Fetch the Gmail address + App Password without hard-coding them.

    Order: environment variables (or .env) -> interactive prompt.
    """
    load_dotenv()
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not address:
        address = input("Gmail address: ").strip()
    if not password:
        # getpass hides the password while typing - safe on shared screens.
        password = getpass.getpass("Gmail App Password (input hidden): ").strip()
    if not address or not password:
        raise SystemExit("Missing Gmail address or App Password. Aborting.")
    return address, password


# --------------------------------------------------------------------------
# Recipients
# --------------------------------------------------------------------------

def read_recipients(csv_path: str) -> list[dict]:
    """Read the recipient CSV. Must contain at least an 'email' column;
    every other column (name, company, ...) becomes a placeholder."""
    if not os.path.exists(csv_path):
        raise SystemExit(f"Recipients file not found: {csv_path}")
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "email" not in [f.lower() for f in reader.fieldnames]:
            raise SystemExit("CSV must have an 'email' column.")
        # Normalise header names to lower-case for predictable placeholders.
        rows = []
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Message building
# --------------------------------------------------------------------------

def build_message(sender: str, sender_name: str, to: str,
                  subject: str, body: str, attachments: list[str]) -> EmailMessage:
    """Build one email (text body + attachments) ready for smtplib."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    for path in attachments:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Attachment not found: {path}")
        ctype, _ = mimetypes.guess_type(path)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(path))
    return msg


# --------------------------------------------------------------------------
# Sending with retry
# --------------------------------------------------------------------------

class Sender:
    """Keeps one SMTP connection alive and re-opens it when Gmail drops
    it - long batches (100+ recipients) routinely outlive a connection."""

    def __init__(self, address: str, password: str, starttls: bool = False):
        self.address = address
        self.password = password
        self.starttls = starttls
        self.server: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    def connect(self) -> None:
        self.close()
        if self.starttls:
            self.server = smtplib.SMTP(GMAIL_HOST, GMAIL_PORT_STARTTLS, timeout=30)
            self.server.ehlo()
            self.server.starttls()
            self.server.ehlo()
        else:
            self.server = smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT_SSL, timeout=30)
        self.server.login(self.address, self.password)

    def close(self) -> None:
        if self.server is not None:
            try:
                self.server.quit()
            except Exception:
                pass
            self.server = None

    def send(self, msg: EmailMessage) -> None:
        if self.server is None:
            self.connect()
        self.server.send_message(msg)


def send_with_retry(sender: Sender, msg: EmailMessage,
                    retries: int = 3, base_delay: float = 5.0) -> tuple[bool, int, str]:
    """Send one message, retrying transient failures with back-off.

    Returns (success, attempts_used, detail).
    Authentication failures are NOT retried - they will never fix
    themselves and retrying can lock the account.
    """
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            sender.send(msg)
            return True, attempt, "OK"
        except smtplib.SMTPAuthenticationError as exc:
            return False, attempt, f"Authentication failed: {exc}"
        except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError) as exc:
            last_error = f"Connection problem: {exc}"
            sender.close()  # force a fresh connection on the next attempt
        except smtplib.SMTPException as exc:
            last_error = f"SMTP error: {exc}"
        except Exception as exc:  # last-resort guard so one bad row can't kill the batch
            last_error = f"Unexpected error: {exc}"

        if attempt < retries:
            wait = base_delay * attempt
            logging.info("  attempt %d failed (%s) - retrying in %ss",
                         attempt, last_error, wait)
            time.sleep(wait)
    return False, retries, last_error


# --------------------------------------------------------------------------
# Status reporting
# --------------------------------------------------------------------------

class StatusLog:
    """Writes one CSV row per recipient: timestamp,email,status,attempts,detail."""

    def __init__(self, path: str = STATUS_CSV):
        self.path = path
        new_file = not os.path.exists(path)
        self._fh = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        if new_file:
            self._writer.writerow(["timestamp", "email", "status", "attempts", "detail"])
            self._fh.flush()

    def record(self, email: str, status: str, attempts: int, detail: str) -> None:
        self._writer.writerow([datetime.now().isoformat(timespec="seconds"),
                               email, status, attempts, detail])
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


# --------------------------------------------------------------------------
# Main flow
# --------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Send personalised emails with attachments from a CSV list (Gmail SMTP).")
    p.add_argument("--recipients", default="recipients.csv",
                   help="CSV file with an 'email' column (default: recipients.csv)")
    p.add_argument("--subject", required=True,
                   help="Subject line - may use {placeholders}, e.g. 'Report for {name}'")
    p.add_argument("--template", default="message.txt",
                   help="Text file with the email body - may use {placeholders} (default: message.txt)")
    p.add_argument("--attach", action="append", default=[], metavar="FILE",
                   help="Attachment file. Repeat the flag for multiple files.")
    p.add_argument("--from-name", default="",
                   help="Display name shown as the sender, e.g. 'Reports Team'")
    p.add_argument("--delay", type=float, default=2.0,
                   help="Seconds to wait between sends (default: 2). Be kind to Gmail's limits.")
    p.add_argument("--retries", type=int, default=3,
                   help="Max send attempts per recipient (default: 3)")
    p.add_argument("--starttls", action="store_true",
                   help="Use port 587 + STARTTLS instead of 465 SSL")
    p.add_argument("--limit", type=int, default=0,
                   help="Send to only the first N recipients (0 = all). Handy for a test batch.")
    p.add_argument("--dry-run", action="store_true",
                   help="Build and validate everything, log the plan, but send NOTHING.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )

    # ---- Load inputs ------------------------------------------------------
    if not os.path.exists(args.template):
        logging.error("Template file not found: %s", args.template)
        return 1
    with open(args.template, encoding="utf-8") as fh:
        body_template = fh.read()

    try:
        recipients = read_recipients(args.recipients)
    except SystemExit as exc:
        logging.error(exc)
        return 1
    if args.limit > 0:
        recipients = recipients[:args.limit]
    logging.info("Loaded %d recipient row(s) from %s", len(recipients), args.recipients)

    for path in args.attach:
        if not os.path.exists(path):
            logging.error("Attachment not found: %s", path)
            return 1

    # ---- Credentials (skipped entirely in dry-run) ------------------------
    if args.dry_run:
        sender_address = os.environ.get("GMAIL_ADDRESS", "you@gmail.com")
        bot: Sender | None = None
        logging.info("DRY-RUN mode: nothing will be sent.")
    else:
        try:
            address, password = get_credentials()
        except SystemExit as exc:
            logging.error(exc)
            return 1
        sender_address = address
        bot = Sender(address, password, starttls=args.starttls)
        try:
            bot.connect()
            logging.info("Connected to Gmail SMTP as %s", address)
        except smtplib.SMTPAuthenticationError:
            logging.error("Gmail login failed. Check the address and that you are "
                          "using an App Password (not your normal password), with "
                          "2-Step Verification enabled.")
            return 1
        except Exception as exc:
            logging.error("Could not connect to Gmail SMTP: %s", exc)
            return 1

    # ---- Send loop ---------------------------------------------------------
    status = StatusLog()
    sent = failed = skipped = 0
    try:
        for i, row in enumerate(recipients, start=1):
            email = row.get("email", "")
            if not EMAIL_RE.match(email):
                logging.warning("[%d/%d] Skipping invalid email: %r", i, len(recipients), email)
                status.record(email or "(blank)", "SKIPPED", 0, "Invalid email address")
                skipped += 1
                continue

            subject = personalise(args.subject, row)
            body = personalise(body_template, row)
            msg = build_message(sender_address, args.from_name, email,
                                subject, body, args.attach)

            if args.dry_run:
                logging.info("[%d/%d] DRY-RUN -> %s | Subject: %s | Attachments: %s",
                             i, len(recipients), email, subject,
                             ", ".join(args.attach) if args.attach else "none")
                status.record(email, "DRY_RUN", 0, "Validated, not sent")
                sent += 1
                continue

            ok, attempts, detail = send_with_retry(bot, msg, retries=args.retries)
            if ok:
                logging.info("[%d/%d] Sent to %s (attempt %d)", i, len(recipients), email, attempts)
                status.record(email, "SENT", attempts, detail)
                sent += 1
            else:
                logging.error("[%d/%d] FAILED %s - %s", i, len(recipients), email, detail)
                status.record(email, "FAILED", attempts, detail)
                failed += 1

            if args.delay > 0 and i < len(recipients):
                time.sleep(args.delay)
    finally:
        if bot is not None:
            bot.close()
        status.close()

    logging.info("Done. Sent: %d | Failed: %d | Skipped: %d | Status report: %s",
                 sent, failed, skipped, STATUS_CSV)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
