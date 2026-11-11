import httpx
import logging
from dataclasses import replace
from pathlib import Path

from jobalert.config import AppConfig, EmailConfig, Filters, SiteConfig
from jobalert.level import job_fits, level_distance
from jobalert.liveness import page_is_live
from jobalert.llm_scan import select_matching_jobs
from jobalert.models import FetchError, Job
from jobalert.place import place_fits
from jobalert.sources.boards import Opening, fetch_boards
from jobalert.sources.companies import fetch_company_openings
from jobalert.store import Store
from jobalert.watcher import CheckReport, run_check

_REMOTE_BOARDS = {"Remotive", "Remote OK", "We Work Remotely", "Jobicy", "Himalayas"}

SOURCE_PAGES = {
    "Remotive": "https://remotive.com/remote-jobs",
    "Remote OK": "https://remoteok.com",
    "Arbeitnow": "https://www.arbeitnow.com",
    "Himalayas": "https://himalayas.app/jobs",
    "YC Work at a Startup": "https://www.workatastartup.com/jobs",
    "Jobicy": "https://jobicy.com",
    "The Muse": "https://www.themuse.com/jobs",
    "We Work Remotely": "https://weworkremotely.com/remote-jobs",
    "ATS directories": "https://github.com/SimplifyJobs/Summer2027-Internships",
    "LinkedIn": "https://www.linkedin.com/jobs",
    "Ashby": "https://jobs.ashbyhq.com",
    "Greenhouse": "https://job-boards.greenhouse.io",
    "Lever": "https://jobs.lever.co",
}


def choose_openings(
    profile: dict,
    openings: list[Opening],
    seen,
    is_live,
) -> tuple[list[Job], list[tuple[str, str]]]:
    """Pick every live opening at the CV's level, and list postings that are closed."""
    ranked = sorted(
        openings,
        key=lambda opening: (
            level_distance(profile, opening.job.title, opening.stated_level),
            opening.job.site_name,
            opening.job.title,
            opening.job.id,
        ),
    )
    chosen: list[Job] = []
    closed: list[tuple[str, str]] = []
    for opening in ranked:
        job = opening.job
        if seen(job.site_name, job.id):
            continue
        if not job_fits(profile, job.title, opening.text, opening.stated_level):
            continue
        if opening.expired:
            closed.append((job.site_name, job.id))
            continue
        state = is_live(job)
        if state == "closed":
            closed.append((job.site_name, job.id))
        elif state == "live":
            chosen.append(job)
    return chosen, closed


def _live_only(openings: list[Opening], is_live) -> tuple[list[Job], list[tuple[str, str]]]:
    chosen: list[Job] = []
    closed: list[tuple[str, str]] = []
    for opening in openings:
        job = opening.job
        state = is_live(job)
        if state == "closed":
            closed.append((job.site_name, job.id))
        elif state == "live":
            chosen.append(job)
    return chosen, closed


def run_discover(
    profile: dict,
    email: EmailConfig,
    store: Store,
    client: httpx.Client,
    send_alert,
    env_file: Path | None = None,
    deliver: bool = True,
) -> CheckReport:
    queries = [str(query) for query in profile.get("queries") or [] if str(query).strip()]
    openings, errors = fetch_boards(client, queries)
    try:
        openings.extend(fetch_company_openings(client, store, queries))
    except Exception as exc:
        logging.exception("Company careers scan failed: %s", exc)
    openings = [_as_remote_board(opening) for opening in openings]
    located = [
        opening
        for opening in openings
        if place_fits(opening.job.title, opening.job.location, opening.text)
    ]
    fresh = [
        opening
        for opening in located
        if not store.is_known(opening.job.site_name, opening.job.id) and not opening.expired
    ]
    logging.info(
        "Careers pages listed %s role links. %s are in India or remote. %s are new.",
        len(openings),
        len(located),
        len(fresh),
    )
    selected = select_matching_jobs(profile, [opening.job for opening in fresh], env_file)
    if selected is None:
        chosen, closed_keys = choose_openings(
            profile,
            located,
            store.is_known,
            lambda job: page_is_live(client, job.url),
        )
    else:
        picked = [fresh[index] for index in sorted(selected) if index < len(fresh)]
        chosen, closed_keys = _live_only(
            picked,
            lambda job: page_is_live(client, job.url),
        )
        logging.info(
            "Gemini kept %s of %s unseen openings. %s of those pages are still open.",
            len(selected),
            len(fresh),
            len(chosen),
        )
    for site_name, job_id in closed_keys:
        store.mark_closed(site_name, job_id)

    buckets: dict[str, list[Job]] = {}
    for job in chosen:
        buckets.setdefault(job.site_name, []).append(job)
    site_names = list(dict.fromkeys([*buckets, *errors]))
    if not site_names:
        return CheckReport([], [])

    app = AppConfig(
        email=email,
        filters=Filters(),
        sites=[
            SiteConfig(name=name, url=SOURCE_PAGES.get(name, "https://example.com/jobs"))
            for name in site_names
        ],
    )

    def fetch(site: SiteConfig) -> list[Job]:
        if site.name in errors:
            raise FetchError(errors[site.name])
        return buckets.get(site.name, [])

    return run_check(app, store, fetch, send_alert, include_existing=True, deliver=deliver)


def _as_remote_board(opening: Opening) -> Opening:
    if opening.job.site_name not in _REMOTE_BOARDS:
        return opening
    blob = f"{opening.job.title} {opening.job.location}".casefold()
    if any(word in blob for word in ("remote", "worldwide", "anywhere")):
        return opening
    location = f"{opening.job.location} · Remote".strip(" ·")
    job = replace(opening.job, location=location)
    return replace(opening, job=job, text=f"{opening.text} Remote")
