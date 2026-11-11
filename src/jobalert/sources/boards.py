import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from jobalert.adapters.common import clean, epoch_ms_to_iso, get_json, get_text, job_or_none
from jobalert.models import FetchError, Job

SOURCE_NAMES = (
    "Remotive",
    "Remote OK",
    "Arbeitnow",
    "Himalayas",
    "YC Work at a Startup",
    "Jobicy",
    "The Muse",
    "We Work Remotely",
    "ATS directories",
    "LinkedIn",
)

_STOP = {"with", "from", "that", "this", "your", "role", "jobs", "and", "the", "for"}
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Opening:
    job: Job
    text: str
    stated_level: str | None = None
    expired: bool = False


def title_matches(title: str, queries: list[str]) -> bool:
    haystack = title.casefold()
    if not queries:
        return True
    for query in queries:
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", query.casefold())
            if len(word) >= 4 and word not in _STOP
        ]
        if words and all(word in haystack for word in words):
            return True
    return False


def _terms(queries: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for query in queries:
        text = " ".join(str(query).split())
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            terms.append(text)
    return terms[:8]


def _search_each(queries: list[str], fetch_term) -> list[Opening]:
    seen: set[str] = set()
    openings: list[Opening] = []
    for term in _terms(queries):
        for opening in fetch_term(term):
            if opening.job.id in seen:
                continue
            seen.add(opening.job.id)
            openings.append(opening)
    return openings


def fetch_boards(
    client: httpx.Client,
    queries: list[str],
) -> tuple[list[Opening], dict[str, str]]:
    openings: list[Opening] = []
    errors: dict[str, str] = {}
    for name, fetcher in (
        ("Remotive", fetch_remotive),
        ("Remote OK", fetch_remoteok),
        ("Arbeitnow", fetch_arbeitnow),
        ("Himalayas", fetch_himalayas),
        ("YC Work at a Startup", fetch_yc),
        ("Jobicy", fetch_jobicy),
        ("The Muse", fetch_muse),
        ("We Work Remotely", fetch_weworkremotely),
        ("ATS directories", _fetch_directories),
        ("LinkedIn", _fetch_linkedin),
    ):
        try:
            found = fetcher(client, queries)
        except FetchError as exc:
            errors[name] = str(exc)
            continue
        except Exception as exc:
            errors[name] = f"Unexpected error: {exc}"
            continue
        openings.extend(found)
    return openings, errors


def _fetch_directories(client: httpx.Client, queries: list[str]) -> list[Opening]:
    from jobalert.sources.directories import fetch_directories

    return fetch_directories(client, queries)


def _fetch_linkedin(client: httpx.Client, queries: list[str]) -> list[Opening]:
    from jobalert.sources.linkedin_jobs import fetch_linkedin

    return fetch_linkedin(client, queries)


def fetch_remotive(client: httpx.Client, queries: list[str]) -> list[Opening]:
    return _search_each(
        queries,
        lambda term: parse_remotive(
            get_json(client, f"https://remotive.com/api/remote-jobs?search={quote(term)}"),
            queries,
        ),
    )


def parse_remotive(payload: object, queries: list[str]) -> list[Opening]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise FetchError("Remotive returned an unexpected response.")
    return _take(_from_records(jobs, queries, _remotive_opening))


def fetch_remoteok(client: httpx.Client, queries: list[str]) -> list[Opening]:
    payload = get_json(client, "https://remoteok.com/api")
    return parse_remoteok(payload, queries)


def parse_remoteok(payload: object, queries: list[str]) -> list[Opening]:
    if not isinstance(payload, list):
        raise FetchError("Remote OK returned an unexpected response.")
    return _take(_from_records(payload, queries, _remoteok_opening))


def fetch_arbeitnow(client: httpx.Client, queries: list[str]) -> list[Opening]:
    return _search_each(
        queries,
        lambda term: parse_arbeitnow(
            get_json(client, f"https://www.arbeitnow.com/api/job-board-api?search={quote(term)}"),
            queries,
        ),
    )


def parse_arbeitnow(payload: object, queries: list[str]) -> list[Opening]:
    jobs = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise FetchError("Arbeitnow returned an unexpected response.")
    return _take(_from_records(jobs, queries, _arbeitnow_opening))


def fetch_himalayas(client: httpx.Client, queries: list[str]) -> list[Opening]:
    payload = get_json(client, "https://himalayas.app/jobs/api?limit=100")
    return parse_himalayas(payload, queries)


def parse_himalayas(payload: object, queries: list[str]) -> list[Opening]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise FetchError("Himalayas returned an unexpected response.")
    return _take(_from_records(jobs, queries, _himalayas_opening))


def _from_records(records: list, queries: list[str], build) -> list[Opening]:
    openings: list[Opening] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        opening = build(record)
        if opening is None or opening.job.id in seen:
            continue
        if queries and not title_matches(opening.job.title, queries):
            continue
        seen.add(opening.job.id)
        openings.append(opening)
    return openings


def _take(openings: list[Opening]) -> list[Opening]:
    return openings


def replace_site(job: Job, site_name: str) -> Job:
    from dataclasses import replace

    return replace(job, site_name=site_name)


def _plain(value: object, limit: int = 3000) -> str:
    text = _TAG.sub(" ", str(value or ""))
    return " ".join(text.split())[:limit]


def _remotive_opening(record: dict) -> Opening | None:
    job = job_or_none(
        id_value=record.get("id"),
        title=record.get("title"),
        url=record.get("url"),
        location=record.get("candidate_required_location"),
        team=record.get("company_name"),
        posted_at=clean(record.get("publication_date")) or None,
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "Remotive"),
        text=f"{job.title} {_plain(record.get('description'))}",
    )


def _remoteok_opening(record: dict) -> Opening | None:
    if not record.get("position"):
        return None
    job = job_or_none(
        id_value=record.get("id"),
        title=record.get("position"),
        url=record.get("apply_url") or record.get("url"),
        location=record.get("location"),
        team=record.get("company"),
        posted_at=epoch_ms_to_iso(_as_epoch_ms(record.get("epoch"))),
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "Remote OK"),
        text=f"{job.title} {_plain(record.get('description'))}",
    )


def _arbeitnow_opening(record: dict) -> Opening | None:
    created = record.get("created_at")
    posted = created if isinstance(created, str) and created.strip() else None
    job = job_or_none(
        id_value=record.get("slug"),
        title=record.get("title"),
        url=record.get("url"),
        location=record.get("location"),
        team=record.get("company_name"),
        posted_at=posted,
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "Arbeitnow"),
        text=f"{job.title} {_plain(record.get('description'))}",
    )


def _himalayas_opening(record: dict) -> Opening | None:
    seniority = record.get("seniority")
    stated = ""
    if isinstance(seniority, list):
        stated = " ".join(str(item) for item in seniority)
    elif isinstance(seniority, str):
        stated = seniority
    job = job_or_none(
        id_value=record.get("guid") or record.get("applicationLink"),
        title=record.get("title"),
        url=record.get("applicationLink"),
        location=_himalayas_location(record.get("locationRestrictions")),
        team=record.get("companyName"),
        posted_at=epoch_ms_to_iso(_as_epoch_ms(record.get("pubDate"))),
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "Himalayas"),
        text=f"{job.title} {_plain(record.get('description'))}",
        stated_level=stated or None,
        expired=_is_expired(record.get("expiryDate")),
    )


def _himalayas_location(value: object) -> str:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("country") or ""))
            else:
                parts.append(str(item))
        return ", ".join(part for part in parts if part.strip())
    return clean(value)


def _as_epoch_ms(value: object) -> object:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 10_000_000_000:
            return value * 1000
    return value


def _is_expired(value: object) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        seconds = value / 1000 if value > 10_000_000_000 else value
        return seconds < datetime.now(timezone.utc).timestamp()
    return False


_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_YC_SEARCH = "https://www.workatastartup.com/jobs/search?q="


def fetch_yc(client: httpx.Client, queries: list[str]) -> list[Opening]:
    """Read the public YC jobs directory, including an India search for every title."""
    openings: list[Opening] = []
    seen: set[str] = set()
    failures: list[str] = []
    for term in _yc_terms(queries):
        try:
            payload = _yc_directory_search(client, term)
        except FetchError as exc:
            failures.append(str(exc))
            continue
        for opening in parse_yc(payload, queries):
            if opening.job.id in seen:
                continue
            seen.add(opening.job.id)
            openings.append(opening)
    if failures and not openings:
        raise FetchError(failures[0])
    return openings


def parse_yc(payload: object, queries: list[str]) -> list[Opening]:
    records = None
    if isinstance(payload, dict):
        if isinstance(payload.get("jobs"), list):
            records = payload["jobs"]
        elif isinstance(payload.get("hits"), list):
            records = payload["hits"]
    if not isinstance(records, list):
        raise FetchError("YC job search returned an unexpected response.")
    return _take(_from_records(records, queries, _yc_opening))


def _yc_terms(queries: list[str]) -> list[str]:
    terms: list[str] = []
    for term in _terms(queries):
        terms.append(term)
        terms.append(f"{term} India")
    return terms


def _yc_directory_search(client: httpx.Client, term: str) -> object:
    url = f"{_YC_SEARCH}{quote(term)}"
    try:
        response = client.get(
            url,
            headers={"User-Agent": _BROWSER, "Accept": "application/json"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach {url}: {exc}") from exc
    if response.status_code >= 400:
        raise FetchError(
            f"HTTP {response.status_code} for {url}",
            status_code=response.status_code,
        )
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise FetchError("YC job search returned an unexpected response.") from exc


def _yc_opening(record: dict) -> Opening | None:
    job_id = record.get("id") or record.get("objectID")
    url = f"https://www.workatastartup.com/jobs/{job_id}" if job_id else ""
    company = record.get("companyName") or record.get("company_name") or record.get("company") or ""
    if isinstance(company, dict):
        company = company.get("name") or ""
    location = record.get("location")
    if location is None:
        location = record.get("locations")
    minimum = record.get("min_experience")
    years = ""
    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
        years = f"{int(minimum)} years"
    job = job_or_none(
        id_value=job_id,
        title=record.get("title"),
        url=url,
        location=_join_location(location),
        team=company,
    )
    if job is None:
        return None
    stated = clean(record.get("jobType")) or None
    return Opening(
        job=replace_site(job, "YC Work at a Startup"),
        text=f"{job.title} {job.location} {years} {_plain(record.get('description'))}",
        stated_level=stated,
    )


def fetch_jobicy(client: httpx.Client, queries: list[str]) -> list[Opening]:
    return _search_each(
        queries,
        lambda term: parse_jobicy(
            get_json(client, f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={quote(term)}"),
            queries,
        ),
    )


def parse_jobicy(payload: object, queries: list[str]) -> list[Opening]:
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise FetchError("Jobicy returned an unexpected response.")
    return _take(_from_records(jobs, queries, _jobicy_opening))


def _jobicy_opening(record: dict) -> Opening | None:
    job = job_or_none(
        id_value=record.get("id"),
        title=record.get("jobTitle"),
        url=record.get("url"),
        location=record.get("jobGeo"),
        team=record.get("companyName"),
        posted_at=clean(record.get("pubDate")) or None,
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "Jobicy"),
        text=f"{job.title} {_plain(record.get('jobDescription') or record.get('jobExcerpt'))}",
        stated_level=clean(record.get("jobLevel")) or None,
    )


def fetch_muse(client: httpx.Client, queries: list[str]) -> list[Opening]:
    payload = get_json(
        client,
        "https://www.themuse.com/api/public/jobs?page=1&descending=true",
    )
    return parse_muse(payload, queries)


def parse_muse(payload: object, queries: list[str]) -> list[Opening]:
    jobs = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise FetchError("The Muse returned an unexpected response.")
    return _take(_from_records(jobs, queries, _muse_opening))


def _muse_opening(record: dict) -> Opening | None:
    levels = record.get("levels") or []
    stated = ""
    if levels and isinstance(levels[0], dict):
        stated = levels[0].get("name") or ""
    company = record.get("company") if isinstance(record.get("company"), dict) else {}
    refs = record.get("refs") if isinstance(record.get("refs"), dict) else {}
    locations = record.get("locations") or []
    location = ""
    if locations and isinstance(locations[0], dict):
        location = locations[0].get("name") or ""
    job = job_or_none(
        id_value=record.get("id"),
        title=record.get("name"),
        url=refs.get("landing_page"),
        location=location,
        team=company.get("name"),
        posted_at=clean(record.get("publication_date")) or None,
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "The Muse"),
        text=f"{job.title} {_plain(record.get('contents'))}",
        stated_level=stated or None,
    )


def fetch_weworkremotely(client: httpx.Client, queries: list[str]) -> list[Opening]:
    xml_text = get_text(
        client,
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    )
    return parse_weworkremotely(xml_text, queries)


def parse_weworkremotely(xml_text: str, queries: list[str]) -> list[Opening]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FetchError("We Work Remotely returned an unexpected feed.") from exc
    records = []
    for item in root.findall("./channel/item"):
        records.append(
            {
                "title": item.findtext("title") or "",
                "link": item.findtext("link") or "",
                "description": item.findtext("description") or "",
            }
        )
    return _take(_from_records(records, queries, _wwr_opening))


def _wwr_opening(record: dict) -> Opening | None:
    raw = clean(record.get("title"))
    team = ""
    title = raw
    if ":" in raw:
        team, title = raw.split(":", 1)
    job = job_or_none(
        id_value=record.get("link"),
        title=title,
        url=record.get("link"),
        team=team,
    )
    if job is None:
        return None
    return Opening(
        job=replace_site(job, "We Work Remotely"),
        text=f"{job.title} {_plain(record.get('description'))}",
    )


def _join_location(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(clean(item) for item in value if clean(item))
    return clean(value)

