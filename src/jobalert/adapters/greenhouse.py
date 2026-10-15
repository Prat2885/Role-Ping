from urllib.parse import quote

import httpx

from jobalert.adapters.common import get_json, job_or_none
from jobalert.adapters.detect import BoardTarget
from jobalert.models import FetchError, Job


def greenhouse_api_url(target: BoardTarget) -> str:
    host = "boards-api.eu.greenhouse.io" if target.europe else "boards-api.greenhouse.io"
    return f"https://{host}/v1/boards/{quote(target.token, safe='')}/jobs"


def parse_greenhouse(payload: object) -> list[Job]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FetchError("Greenhouse returned an unexpected response.")
    jobs: list[Job] = []
    for item in payload["jobs"]:
        if not isinstance(item, dict):
            continue
        parsed = _one_job(item)
        if parsed is not None:
            jobs.append(parsed)
    return jobs


def fetch_greenhouse(client: httpx.Client, target: BoardTarget) -> list[Job]:
    url = greenhouse_api_url(target)
    try:
        payload = get_json(client, url)
    except FetchError as exc:
        if exc.status_code == 404:
            raise FetchError(f"Greenhouse board '{target.token}' was not found.") from exc
        raise
    return parse_greenhouse(payload)


def _one_job(item: dict) -> Job | None:
    location = ""
    raw_location = item.get("location")
    if isinstance(raw_location, dict):
        location = raw_location.get("name") or ""
    if not str(location).strip():
        offices = item.get("offices") or []
        names = [
            office.get("name", "")
            for office in offices
            if isinstance(office, dict)
        ]
        location = ", ".join(name for name in names if str(name).strip())

    team = ""
    departments = item.get("departments") or []
    if departments and isinstance(departments[0], dict):
        team = departments[0].get("name") or ""

    return job_or_none(
        id_value=item.get("id"),
        title=item.get("title"),
        url=item.get("absolute_url"),
        location=location,
        team=team,
    )
