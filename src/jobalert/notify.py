import smtplib
from email.message import EmailMessage

from jobalert.config import SmtpSettings
from jobalert.models import Job


def build_message(prefix: str, jobs: list[Job]) -> tuple[str, str]:
    label = prefix.strip() or "[Jobs]"
    if len(jobs) == 1:
        subject = f"{label} {jobs[0].title} — {jobs[0].site_name}"
    else:
        subject = f"{label} {len(jobs)} new openings"

    count_label = "opening" if len(jobs) == 1 else "openings"
    lines = [f"{len(jobs)} new job {count_label}:", ""]
    current_site = None
    for job in jobs:
        if job.site_name != current_site:
            current_site = job.site_name
            lines.append(current_site)
        lines.append(f"  {job.title}")
        if job.location:
            lines.append(f"  Location: {job.location}")
        if job.team:
            lines.append(f"  Team: {job.team}")
        lines.append(f"  {job.url}")
        lines.append("")
    return subject, "\n".join(lines).rstrip() + "\n"


def deliver_email(settings: SmtpSettings, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            _login_and_send(smtp, settings, message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        if settings.smtp_use_tls:
            smtp.starttls()
            smtp.ehlo()
        _login_and_send(smtp, settings, message)


def _login_and_send(
    smtp: smtplib.SMTP,
    settings: SmtpSettings,
    message: EmailMessage,
) -> None:
    if settings.smtp_username.strip():
        smtp.login(settings.smtp_username, settings.smtp_password)
    smtp.send_message(message)
