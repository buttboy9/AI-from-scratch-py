"""Email new report files dropped into a folder.

Usage example:
  python report_emailer.py \
    --reports-dir ./reports \
    --to reports@company.com \
    --smtp-host smtp.gmail.com \
    --smtp-user you@company.com

Defaults can be provided via environment variables:
  REPORTS_DIR, SENT_DIR, FAILED_DIR, POLL_INTERVAL_SECONDS,
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
  EMAIL_FROM, EMAIL_TO
"""
from __future__ import annotations

import argparse
import os
import shutil
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path


def _env_or_default(env_key: str, fallback: str | None = None) -> str | None:
    value = os.getenv(env_key)
    if value is not None and value.strip() != "":
        return value
    return fallback


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Email report files from a folder.")
    parser.add_argument(
        "--reports-dir",
        default=_env_or_default("REPORTS_DIR", "./reports"),
        help="Folder to watch for new reports (default: ./reports or REPORTS_DIR).",
    )
    parser.add_argument(
        "--sent-dir",
        default=_env_or_default("SENT_DIR", "./sent"),
        help="Folder to move reports after sending (default: ./sent or SENT_DIR).",
    )
    parser.add_argument(
        "--failed-dir",
        default=_env_or_default("FAILED_DIR", "./failed"),
        help="Folder to move reports that failed to send (default: ./failed or FAILED_DIR).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(_env_or_default("POLL_INTERVAL_SECONDS", "10")),
        help="Polling interval in seconds (default: 10).",
    )
    parser.add_argument("--smtp-host", default=_env_or_default("SMTP_HOST"), required=False)
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=int(_env_or_default("SMTP_PORT", "587")),
    )
    parser.add_argument("--smtp-user", default=_env_or_default("SMTP_USER"), required=False)
    parser.add_argument("--smtp-password", default=_env_or_default("SMTP_PASSWORD"))
    parser.add_argument(
        "--email-from",
        default=_env_or_default("EMAIL_FROM"),
        required=False,
    )
    parser.add_argument(
        "--to",
        dest="email_to",
        action="append",
        default=None,
        help="Recipient email address (repeatable or use EMAIL_TO).",
    )
    parser.add_argument(
        "--subject",
        default="Automated Report",
        help="Email subject line (default: Automated Report).",
    )
    args = parser.parse_args()

    if args.email_to is None:
        env_to = _env_or_default("EMAIL_TO")
        if env_to:
            args.email_to = [addr.strip() for addr in env_to.split(",") if addr.strip()]

    if not args.email_to:
        parser.error("At least one recipient is required via --to or EMAIL_TO.")

    if not args.smtp_host:
        parser.error("SMTP host is required via --smtp-host or SMTP_HOST.")

    if not args.email_from:
        parser.error("Sender is required via --email-from or EMAIL_FROM.")

    return args


def _send_report(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str | None,
    smtp_password: str | None,
    email_from: str,
    email_to: list[str],
    subject: str,
    report_path: Path,
) -> None:
    message = EmailMessage()
    message["From"] = email_from
    message["To"] = ", ".join(email_to)
    message["Subject"] = subject
    message.set_content(
        f"Automated report attached: {report_path.name}\n\n"
        "This message was sent by report_emailer.py."
    )

    with report_path.open("rb") as report_file:
        report_data = report_file.read()

    message.add_attachment(
        report_data,
        maintype="application",
        subtype="octet-stream",
        filename=report_path.name,
    )

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.ehlo()
        if smtp_port == 587:
            smtp.starttls()
            smtp.ehlo()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def _ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = _parse_args()

    reports_dir = Path(args.reports_dir).expanduser().resolve()
    sent_dir = Path(args.sent_dir).expanduser().resolve()
    failed_dir = Path(args.failed_dir).expanduser().resolve()

    _ensure_dirs(reports_dir, sent_dir, failed_dir)

    print(f"Watching {reports_dir} for new reports. Press Ctrl+C to stop.")

    try:
        while True:
            report_files = sorted(
                [path for path in reports_dir.iterdir() if path.is_file()]
            )
            for report_path in report_files:
                try:
                    _send_report(
                        smtp_host=args.smtp_host,
                        smtp_port=args.smtp_port,
                        smtp_user=args.smtp_user,
                        smtp_password=args.smtp_password,
                        email_from=args.email_from,
                        email_to=args.email_to,
                        subject=args.subject,
                        report_path=report_path,
                    )
                except Exception as exc:  # noqa: BLE001 - keep simple for scripting.
                    print(f"Failed to send {report_path.name}: {exc}", file=sys.stderr)
                    destination = failed_dir / report_path.name
                else:
                    print(f"Sent {report_path.name}")
                    destination = sent_dir / report_path.name

                if destination.exists():
                    destination.unlink()
                shutil.move(str(report_path), destination)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopping report emailer.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
