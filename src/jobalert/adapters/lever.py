from urllib.parse import quote

import httpx

from jobalert.adapters.common import epoch_ms_to_iso, get_json, job_or_none
from jobalert.adapters.detect import BoardTarget
from jobalert.models import FetchError, Job


def lever_api_url(target: BoardTarget) -> str:
    host = "api.eu.lever.co" if target.europe else "api.lever.co"
    return f"https://{host}/v0/postings/{quote(target.token, safe='')}?mode=json"


def parse_lever(payload: object) -> list[Job]:
    if isinstance(payload, dict):
        raise FetchError("Lever returned an unexpected response.")
    if not isinstance(payload, list):
        raise FetchError("Lever returned an unexpected response.")
    jobs: list[Job] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        parsed = _one_job(item)
        if parsed is not None:
            jobs.append(parsed)
    return jobs


def fetch_lever(client: httpx.Client, target: BoardTarget) -> list[Job]:
    url = lever_api_url(target)
    try:
        payload = get_json(client, url)
    except FetchError as exc:
        if exc.status_code == 404:
            raise FetchError(f"Lever company '{target.token}' was not found.") from exc
        raise
    return parse_lever(payload)


def _one_job(item: dict) -> Job | None:
    categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
    return job_or_none(
        id_value=item.get("id"),
        title=item.get("text") or item.get("title"),
        url=item.get("hostedUrl") or item.get("applyUrl"),
        location=categories.get("location"),
        team=categories.get("team"),
        posted_at=epoch_ms_to_iso(item.get("createdAt")),
    )
