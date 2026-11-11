import logging
import sys
import time
from pathlib import Path

import typer

from jobalert.config import load_config, load_smtp
from jobalert.discover import run_discover
from jobalert.fetch import fetch_site, make_client
from jobalert.models import ConfigError, Job
from jobalert.notify import build_message, deliver_email
from jobalert.profile import format_profile, load_profile, save_profile
from jobalert.store import Store
from jobalert.watcher import CheckReport, run_check

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Watch careers pages and email openings that match a CV.",
)


def main() -> None:
    _configure_stdio()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    app()


@app.command()
def check(
    config: Path = typer.Option(
        Path("config.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config.",
    ),
    include_existing: bool = typer.Option(
        False,
        "--include-existing",
        help="On the first check of a site, email openings that are already posted.",
    ),
) -> None:
    """Check every configured careers page once."""
    loaded = _load(config)
    try:
        report = _execute(loaded, include_existing)
    except ConfigError as exc:
        logging.error("%s", exc)
        raise typer.Exit(code=1) from exc
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def watch(
    config: Path = typer.Option(
        Path("config.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config.",
    ),
    include_existing: bool = typer.Option(
        False,
        "--include-existing",
        help="On the first check of a site, email openings that are already posted.",
    ),
) -> None:
    """Keep checking on the interval from the config. Stop with Ctrl+C."""
    logging.info("Watching configured careers pages. Stop with Ctrl+C.")
    minutes = 30
    try:
        while True:
            try:
                loaded = load_config(config)
            except ConfigError as exc:
                logging.error("%s", exc)
            else:
                minutes = loaded.app.schedule_minutes
                try:
                    report = _execute(loaded, include_existing)
                except ConfigError as exc:
                    logging.error("%s", exc)
                else:
                    if not report.ok:
                        logging.error("Check failed. The next check will try again.")
            time.sleep(minutes * 60)
    except KeyboardInterrupt:
        logging.info("Stopped.")


@app.command("test-email")
def test_email(
    config: Path = typer.Option(
        Path("config.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config.",
    ),
) -> None:
    """Send a test message to the address in the config."""
    loaded = _load(config)
    try:
        smtp = load_smtp(loaded.directory)
    except ConfigError as exc:
        logging.error("%s", exc)
        raise typer.Exit(code=1) from exc
    prefix = loaded.app.email.subject_prefix
    subject = f"{prefix} Test message"
    body = (
        "Job alert agent can send mail to this address.\n"
        "No careers pages were checked for this message.\n"
    )
    try:
        deliver_email(smtp, loaded.app.email.to, subject, body)
    except Exception as exc:
        logging.error("Test email failed: %s", exc)
        raise typer.Exit(code=1) from exc
    logging.info("Sent a test email to %s.", loaded.app.email.to)


@app.command()
def profile(
    cv: Path | None = typer.Argument(None, help="PDF, DOCX, or TXT CV to read."),
    config: Path = typer.Option(
        Path("config.yaml"),
        "--config",
        "-c",
        help="Path to the YAML config.",
    ),
) -> None:
    """Save the experience level and job titles used to search major boards."""
    loaded = _load(config)
    if cv is None:
        try:
            saved = load_profile(loaded.directory)
        except ConfigError as exc:
            logging.error("%s", exc)
            raise typer.Exit(code=1) from exc
        if saved is None:
            logging.error("No CV profile yet. Example: jobalert profile resume.pdf")
            raise typer.Exit(code=1)
        logging.info("%s", format_profile(saved))
        return
    try:
        saved = save_profile(loaded.directory, cv)
    except ConfigError as exc:
        logging.error("%s", exc)
        raise typer.Exit(code=1) from exc
    logging.info("Saved CV profile.\n%s", format_profile(saved))


def _execute(loaded, include_existing: bool) -> CheckReport:
    smtp = load_smtp(loaded.directory)

    def send_alert(jobs: list[Job]) -> None:
        subject, body = build_message(loaded.app.email.subject_prefix, jobs)
        deliver_email(smtp, loaded.app.email.to, subject, body)

    with make_client() as client, Store(loaded.database_path()) as store:
        reports = [
            run_check(
                loaded.app,
                store,
                lambda site: fetch_site(client, site),
                send_alert,
                include_existing=include_existing,
                deliver=False,
            )
        ]
        reports.append(_discover(loaded, store, client, send_alert, deliver=False))
        pending = store.list_pending()
        emailed: list[Job] = []
        email_error = None
        if pending:
            try:
                send_alert(pending)
                store.mark_sent([(job.site_name, job.id) for job in pending])
                emailed = pending
            except Exception as exc:
                email_error = str(exc)
    report = _combine(reports)
    report = CheckReport(report.sites, emailed, email_error or report.email_error)
    _log_report(report)
    return report


def _discover(loaded, store, client, send_alert, deliver: bool = True) -> CheckReport:
    try:
        saved = load_profile(loaded.directory)
    except ConfigError as exc:
        logging.error("%s", exc)
        return CheckReport([], [], str(exc))
    if saved is None:
        logging.info("No CV profile yet. Board search starts after: jobalert profile resume.pdf")
        return CheckReport([], [])
    logging.info(
        "Searching job boards, the YC directory, and company careers pages for %s roles.",
        saved.get("level"),
    )
    report = run_discover(
        saved,
        loaded.app.email,
        store,
        client,
        send_alert,
        env_file=loaded.directory / ".env",
        deliver=deliver,
    )
    if not report.sites and not report.emailed:
        logging.info("No live openings matched your experience level.")
    return report


def _combine(reports: list[CheckReport]) -> CheckReport:
    sites = []
    emailed = []
    email_error = None
    for report in reports:
        sites.extend(report.sites)
        emailed.extend(report.emailed)
        if report.email_error and email_error is None:
            email_error = report.email_error
    return CheckReport(sites, emailed, email_error)


def _load(config: Path):
    try:
        return load_config(config)
    except ConfigError as exc:
        logging.error("%s", exc)
        raise typer.Exit(code=1) from exc


def _log_report(report: CheckReport) -> None:
    for site in report.sites:
        if site.error:
            logging.error("%s: %s", site.site_name, site.error)
            continue
        if site.initialized_now and site.pending == 0:
            logging.info(
                "%s: first check recorded %s matching opening(s). No email sent.",
                site.site_name,
                site.seeded,
            )
        elif site.pending:
            logging.info(
                "%s: %s opening(s) waiting to email.",
                site.site_name,
                site.pending,
            )
        else:
            logging.info("%s: no new openings.", site.site_name)
    if report.emailed:
        logging.info("Emailed %s opening(s).", len(report.emailed))
    if report.email_error:
        logging.error("Email failed: %s", report.email_error)
        logging.error("Those openings stay queued and the next check will try again.")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
