from urllib.parse import quote

import httpx

from jobalert.adapters.common import get_json, job_or_none
from jobalert.adapters.detect import BoardTarget
from jobalert.models import FetchError, Job


def ashby_api_url(target: BoardTarget) -> str:
    return (
        "https://api.ashbyhq.com/posting-api/job-board/"
        f"{quote(target.token, safe='')}"
    )


def parse_ashby(payload: object) -> list[Job]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FetchError("Ashby returned an unexpected response.")
    jobs: list[Job] = []
    for item in payload["jobs"]:
        if not isinstance(item, dict):
            continue
        if item.get("isListed") is False:
            continue
        parsed = _one_job(item)
        if parsed is not None:
            jobs.append(parsed)
    return jobs


def fetch_ashby(client: httpx.Client, target: BoardTarget) -> list[Job]:
    url = ashby_api_url(target)
    try:
        payload = get_json(client, url)
    except FetchError as exc:
        if exc.status_code == 404:
            raise FetchError(f"Ashby board '{target.token}' was not found.") from exc
        raise
    return parse_ashby(payload)


def _one_job(item: dict) -> Job | None:
    location = item.get("location") or ""
    if item.get("isRemote") and not str(location).strip():
        location = "Remote"
    team = item.get("department") or item.get("team") or ""
    posted = item.get("publishedAt")
    posted_at = posted.strip() if isinstance(posted, str) and posted.strip() else None
    return job_or_none(
        id_value=item.get("id"),
        title=item.get("title"),
        url=item.get("jobUrl") or item.get("applyUrl"),
        location=location,
        team=team,
        posted_at=posted_at,
    )
