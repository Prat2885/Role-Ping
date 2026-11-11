"""Public Ashby, Greenhouse, and Lever postings gathered from job directories."""

import html
import re
import unicodedata
from urllib.parse import urlparse

import httpx

from jobalert.adapters.common import clean, get_text
from jobalert.models import FetchError, Job
from jobalert.sources.boards import Opening, title_matches

_LISTS = (
    (
        "Simplify Internships",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md",
    ),
    (
        "Simplify New Grad",
        "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    ),
    (
        "Pitt CSC Internships",
        "https://raw.githubusercontent.com/pittcsc/Summer2026-Internships/dev/README.md",
    ),
    (
        "Community Internships",
        "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/README.md",
    ),
)

_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TD = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

_ATS_HOSTS = {
    "boards.greenhouse.io": "Greenhouse",
    "job-boards.greenhouse.io": "Greenhouse",
    "boards.eu.greenhouse.io": "Greenhouse",
    "job-boards.eu.greenhouse.io": "Greenhouse",
    "jobs.lever.co": "Lever",
    "jobs.eu.lever.co": "Lever",
    "jobs.ashbyhq.com": "Ashby",
}


def fetch_directories(client: httpx.Client, queries: list[str]) -> list[Opening]:
    openings: list[Opening] = []
    seen: set[str] = set()
    failures: list[str] = []
    for name, url in _LISTS:
        try:
            text = get_text(client, url)
        except FetchError as exc:
            failures.append(f"{name}: {exc}")
            continue
        for opening in parse_listing(text, queries):
            if opening.job.url in seen:
                continue
            seen.add(opening.job.url)
            openings.append(opening)
    if failures and not openings:
        raise FetchError(" ".join(failures))
    return openings


def parse_listing(text: str, queries: list[str]) -> list[Opening]:
    if "<tr" in text.casefold():
        return _from_html(text, queries)
    return _from_markdown(text, queries)


def canonical_apply_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(html.unescape(url.strip()))
    host = parsed.netloc.lower().split("@")[-1]
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    kind = _ATS_HOSTS.get(host)
    if kind is None:
        return None
    path = parsed.path.rstrip("/")
    if host == "jobs.ashbyhq.com" and path.endswith("/application"):
        path = path[: -len("/application")]
    if path.count("/") < 2:
        return None
    return kind, f"https://{host}{path}"


def _from_html(text: str, queries: list[str]) -> list[Opening]:
    openings: list[Opening] = []
    for row in _TR.findall(text):
        if "<del" in row.casefold():
            continue
        cells = [_plain(cell) for cell in _TD.findall(row)]
        if len(cells) < 2:
            continue
        link = _first_ats(_HREF.findall(row))
        if link is None:
            continue
        kind, apply_url = link
        company = cells[0]
        role = cells[1]
        location = cells[2] if len(cells) > 2 else ""
        opening = _opening(kind, apply_url, company, role, location, queries)
        if opening is not None:
            openings.append(opening)
    return openings


def _from_markdown(text: str, queries: list[str]) -> list[Opening]:
    openings: list[Opening] = []
    for line in text.splitlines():
        if not line.startswith("|") or "~~" in line:
            continue
        cells = [clean(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        link = _first_ats(href for _, href in _MD_LINK.findall(line))
        if link is None:
            continue
        kind, apply_url = link
        company = _plain(cells[0])
        role = _plain(cells[1])
        location = _plain(cells[2]) if len(cells) > 2 else ""
        opening = _opening(kind, apply_url, company, role, location, queries)
        if opening is not None:
            openings.append(opening)
    return openings


def _first_ats(urls) -> tuple[str, str] | None:
    for url in urls:
        parsed = canonical_apply_url(url)
        if parsed is not None:
            return parsed
    return None


def _opening(
    kind: str,
    apply_url: str,
    company: str,
    role: str,
    location: str,
    queries: list[str],
) -> Opening | None:
    if not role or not title_matches(role, queries):
        return None
    job = Job(
        id=apply_url,
        title=role,
        url=apply_url,
        location=location,
        team=company,
        site_name=kind,
    )
    return Opening(job=job, text=f"{role} {company} {location}")


def _plain(value: str) -> str:
    text = html.unescape(_TAG.sub(" ", value))
    kept = [
        char
        for char in text
        if unicodedata.category(char) not in {"So", "Sk", "Cn"}
    ]
    return clean("".join(kept))
