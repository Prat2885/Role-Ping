from collections.abc import Callable
from dataclasses import dataclass, replace

from jobalert.config import AppConfig, SiteConfig
from jobalert.filters import job_matches
from jobalert.models import FetchError, Job
from jobalert.store import Store

FetchJobs = Callable[[SiteConfig], list[Job]]
SendAlert = Callable[[list[Job]], None]


@dataclass
class SiteResult:
    site_name: str
    matched: int = 0
    seeded: int = 0
    pending: int = 0
    initialized_now: bool = False
    error: str | None = None


@dataclass
class CheckReport:
    sites: list[SiteResult]
    emailed: list[Job]
    email_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.email_error is None and all(site.error is None for site in self.sites)


def run_check(
    app: AppConfig,
    store: Store,
    fetch_jobs: FetchJobs,
    send_alert: SendAlert,
    include_existing: bool = False,
    deliver: bool = True,
) -> CheckReport:
    """Fetch each site, remember new openings, and email ones that should alert.

    The first successful check for a site records current matches as seeded and
    does not email them. Later checks email only openings that were not stored
    before. Pass include_existing to email the current list on that first check.
    Pass deliver=False to leave them pending for one combined email.
    """
    results: list[SiteResult] = []
    for site in app.sites:
        results.append(_check_site(app, store, fetch_jobs, site, include_existing))

    to_send = store.list_pending()
    for result in results:
        if result.error is None:
            result.pending = sum(1 for job in to_send if job.site_name == result.site_name)

    if not to_send or not deliver:
        return CheckReport(results, [])

    try:
        send_alert(to_send)
    except Exception as exc:
        return CheckReport(results, [], str(exc))

    store.mark_sent([(job.site_name, job.id) for job in to_send])
    return CheckReport(results, to_send)


def _check_site(
    app: AppConfig,
    store: Store,
    fetch_jobs: FetchJobs,
    site: SiteConfig,
    include_existing: bool,
) -> SiteResult:
    try:
        fetched = fetch_jobs(site)
    except FetchError as exc:
        return SiteResult(site.name, error=str(exc))
    except Exception as exc:
        return SiteResult(site.name, error=f"Unexpected error: {exc}")

    keywords = app.filters.keywords if site.keywords is None else site.keywords
    locations = app.filters.locations if site.locations is None else site.locations
    matched = _matching_jobs(site.name, fetched, keywords, locations)
    first_run = not store.is_initialized(site.name)
    seeded = 0
    for job in matched:
        if store.has(site.name, job.id):
            continue
        status = "seeded" if first_run and not include_existing else "pending"
        store.insert(job, status)
        if status == "seeded":
            seeded += 1
    if first_run:
        store.mark_initialized(site.name)
    else:
        store.touch(site.name)
    return SiteResult(
        site_name=site.name,
        matched=len(matched),
        seeded=seeded,
        initialized_now=first_run,
    )


def _matching_jobs(
    site_name: str,
    fetched: list[Job],
    keywords: list[str],
    locations: list[str],
) -> list[Job]:
    matched: list[Job] = []
    seen: set[str] = set()
    for job in fetched:
        if not job.id or not job.title or not job.url or job.id in seen:
            continue
        seen.add(job.id)
        if not job_matches(job, keywords, locations):
            continue
        matched.append(replace(job, site_name=site_name))
    return matched
