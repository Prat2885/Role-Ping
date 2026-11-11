"""Public LinkedIn job search pages for India roles and remote roles."""

import json
from urllib.parse import urlencode

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from jobalert.models import FetchError, Job
from jobalert.sources.boards import Opening, _terms, replace_site, title_matches

_SEARCH = "https://www.linkedin.com/jobs/search"
_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_linkedin(client: httpx.Client, queries: list[str]) -> list[Opening]:
    openings: list[Opening] = []
    seen: set[str] = set()
    failures: list[str] = []
    for term in _linkedin_terms(queries):
        for remote, starts in ((False, (0, 25)), (True, (0,))):
            for start in starts:
                try:
                    html = _search(client, term, remote, start)
                except FetchError as exc:
                    failures.append(str(exc))
                    return _finish(openings, failures)
                for opening in parse_linkedin(html, queries, remote):
                    if opening.job.id in seen:
                        continue
                    seen.add(opening.job.id)
                    openings.append(opening)
    return _finish(openings, failures)


def _linkedin_terms(queries: list[str]) -> list[str]:
    terms = list(_terms(queries))
    seen = {term.casefold() for term in terms}
    for term in list(terms):
        if "engineer" not in term.casefold() or term.casefold().startswith("associate"):
            continue
        associate = f"Associate {term}"
        if associate.casefold() in seen:
            continue
        seen.add(associate.casefold())
        terms.append(associate)
    return terms


def parse_linkedin(html: str, queries: list[str], remote: bool = False) -> list[Opening]:
    openings: list[Opening] = []
    tree = HTMLParser(html)
    for node in tree.css("script"):
        if "ld+json" not in (node.attributes.get("type") or "").lower():
            continue
        try:
            payload = json.loads(node.text(strip=False) or "")
        except json.JSONDecodeError:
            continue
        for item in _items(payload):
            opening = _opening(item, queries, remote)
            if opening is not None:
                openings.append(opening)
    return openings


def _items(payload: object):
    if isinstance(payload, list):
        for item in payload:
            yield from _items(item)
        return
    if not isinstance(payload, dict):
        return
    elements = payload.get("itemListElement")
    if isinstance(elements, list):
        for item in elements:
            if isinstance(item, dict):
                yield item
        return
    if payload.get("@type") == "ListItem":
        yield payload


def _opening(item: dict, queries: list[str], remote: bool) -> Opening | None:
    title = " ".join(str(item.get("name") or "").split())
    url = str(item.get("url") or "").split("?")[0]
    if not title or "linkedin.com/jobs/view/" not in url or not title_matches(title, queries):
        return None
    company = " ".join(str(item.get("disambiguatingDescription") or "").split())
    location = " ".join(str(item.get("description") or "").split())
    if remote and "remote" not in location.casefold():
        location = f"{location} · Remote".strip(" ·")
    job_id = url.rstrip("/").rsplit("-", 1)[-1]
    if not job_id.isdigit():
        job_id = url
    job = Job(
        id=job_id,
        title=title,
        url=url,
        location=location,
        team=company,
        site_name="LinkedIn",
    )
    return Opening(job=replace_site(job, "LinkedIn"), text=f"{title} {company} {location}")


def _search(client: httpx.Client, term: str, remote: bool, start: int) -> str:
    params = {
        "keywords": term,
        "sortBy": "DD",
        "f_TPR": "r86400",
        "start": str(start),
    }
    if remote:
        params["f_WT"] = "2"
    else:
        params["location"] = "India"
    url = f"{_SEARCH}?{urlencode(params)}"
    try:
        response = client.get(
            url,
            headers={"User-Agent": _BROWSER, "Accept": "text/html"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach LinkedIn job search: {exc}") from exc
    if response.status_code >= 400:
        raise FetchError(
            f"LinkedIn job search returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )
    return response.text


def _finish(openings: list[Opening], failures: list[str]) -> list[Opening]:
    if failures and not openings:
        raise FetchError(failures[0])
    return openings
