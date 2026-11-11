import json
import logging
import os
from pathlib import Path

import httpx

from jobalert.level import job_fits

_LEVELS = {"intern", "junior", "mid", "senior", "staff", "director"}


def scan_cv(text: str, env_file: Path | None = None) -> dict | None:
    """Ask a configured chat model for related job titles. Return None if unset."""
    settings = _settings(env_file)
    if settings is None:
        return None
    base_url, api_key, model = settings
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You read a CV and choose job searches. "
                    "Reply with JSON only, no markdown. "
                    "Keys: level, years, queries, summary. "
                    "level is one of intern, junior, mid, senior, staff, director. "
                    "years is a number. "
                    "queries is a list of at most 12 job titles to search. "
                    "Include related titles, not only the latest job title. "
                    "A backend intern also matches fullstack engineer, "
                    "full stack engineer intern, backend engineer, backend developer, "
                    "backend intern, software engineer, and software engineer intern. "
                    "Do not add senior or director titles for an intern or junior. "
                    "summary is a short description of the person's skills, projects, "
                    "education, and the roles they should be offered. "
                    "Mention that jobs may be in India or anywhere else."
                ),
            },
            {"role": "user", "content": text[:12000]},
        ],
    }
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=40,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return profile_from_llm(content)


def profile_from_llm(content: str) -> dict | None:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    level = str(raw.get("level") or "").casefold()
    if level not in _LEVELS:
        return None
    queries = []
    seen: set[str] = set()
    for item in raw.get("queries") or []:
        text = " ".join(str(item).split())
        key = text.casefold()
        if not text or len(text) > 80 or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    if not queries:
        return None
    years = raw.get("years")
    parsed_years = float(years) if isinstance(years, (int, float)) and not isinstance(years, bool) else None
    profile = {"level": level, "years": parsed_years, "queries": queries[:12]}
    summary = " ".join(str(raw.get("summary") or "").split())
    if summary:
        profile["summary"] = summary[:2000]
    return profile


def select_matching_jobs(profile: dict, jobs: list, env_file: Path | None) -> set[int] | None:
    """Return indexes Gemini accepts as real matches. None when no model is configured."""
    settings = _settings(env_file)
    summary = " ".join(str(profile.get("summary") or "").split())
    if settings is None or not summary or not jobs:
        return None if settings is None or not summary else set()
    base_url, api_key, model = settings
    chosen: set[int] = set()
    for start in range(0, len(jobs), 20):
        batch = jobs[start : start + 20]
        indexes = _select_batch(base_url, api_key, model, profile, summary, batch)
        for index in indexes:
            chosen.add(start + index)
    return chosen


def indexes_from_llm(content: str, count: int) -> list[int]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, dict):
        return []
    indexes: list[int] = []
    for item in raw.get("matches") or []:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if 0 <= item < count and item not in indexes:
            indexes.append(item)
    return indexes


def _select_batch(base_url: str, api_key: str, model: str, profile: dict, summary: str, jobs: list) -> list[int]:
    listing = []
    for index, job in enumerate(jobs):
        listing.append(
            {
                "n": index,
                "title": job.title,
                "company": job.team or job.site_name,
                "source": job.site_name,
                "location": job.location,
                "url": job.url,
            }
        )
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You match a candidate to real job openings. "
                    "Reply with JSON only: {\"matches\": [indexes]}. "
                    "Keep a job only when it is one genuine opening this person can apply to. "
                    "Reject city or role index pages, 'jobs in <city>' pages, lists of jobs, "
                    "and anything that is not a single role. "
                    "Reject senior, staff, director, principal, and lead roles when the candidate "
                    "is an intern or junior. "
                    "Keep software, backend, fullstack, and closely related engineering roles "
                    "at the candidate's level, including associate and junior titles. "
                    "Keep India roles and remote roles from YC, company careers pages, "
                    "and job boards, not only LinkedIn. "
                    "Associate and junior titles count for an intern or junior candidate. "
                    "If a careers page does not name a city, keep the role when the title fits. "
                    "Reject office jobs whose location is outside India. "
                    "When unsure the posting is legitimate, leave it out."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "candidate": {
                            "level": profile.get("level"),
                            "years": profile.get("years"),
                            "summary": summary,
                        },
                        "jobs": listing,
                    }
                ),
            },
        ],
    }
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        logging.info("Gemini match batch failed: %s", exc)
        return [
            index
            for index, job in enumerate(jobs)
            if job_fits(profile, job.title, "", None)
        ]
    return indexes_from_llm(content, len(jobs))


def _settings(env_file: Path | None) -> tuple[str, str, str] | None:
    values = dict(os.environ)
    if env_file is not None and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    api_key = values.get("LLM_API_KEY") or values.get("OPENAI_API_KEY") or ""
    if not api_key:
        return None
    base_url = values.get("LLM_BASE_URL") or "https://api.openai.com/v1"
    model = values.get("LLM_MODEL") or "gpt-4o-mini"
    return base_url, api_key, model
