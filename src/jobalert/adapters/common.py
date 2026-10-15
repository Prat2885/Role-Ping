import json
from datetime import datetime, timezone
from typing import Any

import httpx

from jobalert.models import FetchError, Job


def clean(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def epoch_ms_to_iso(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def get_text(client: httpx.Client, url: str) -> str:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach {url}: {exc}") from exc
    if response.status_code >= 400:
        raise FetchError(
            f"HTTP {response.status_code} for {url}",
            status_code=response.status_code,
        )
    if len(response.content) > 5_000_000:
        raise FetchError(f"Response from {url} is larger than 5 MB")
    return response.text


def get_json(client: httpx.Client, url: str) -> Any:
    text = get_text(client, url)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"Expected JSON from {url}") from exc


def job_or_none(
    *,
    id_value: object,
    title: object,
    url: object,
    location: object = "",
    team: object = "",
    posted_at: str | None = None,
) -> Job | None:
    job_id = clean(id_value)
    job_title = clean(title)
    job_url = clean(url)
    if not job_title or not job_url:
        return None
    if not job_id:
        job_id = job_url
    return Job(
        id=job_id,
        title=job_title,
        url=job_url,
        location=clean(location),
        team=clean(team),
        posted_at=posted_at,
    )
