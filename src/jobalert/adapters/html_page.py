import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from jobalert.adapters.common import clean, get_text, job_or_none
from jobalert.models import FetchError, Job

_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gh_src",
}
_NAV_TEXT = {
    "home",
    "about",
    "blog",
    "login",
    "log in",
    "sign in",
    "sign up",
    "privacy",
    "privacy policy",
    "terms",
    "contact",
    "search",
    "careers",
    "jobs",
    "apply",
    "apply now",
    "learn more",
    "read more",
    "view all",
    "see all",
    "back",
    "next",
    "previous",
}
_JOB_HREF = re.compile(
    r"(/jobs?(?:/|$|\?))|"
    r"(/careers?/.+)|"
    r"(/positions?(?:/|$))|"
    r"(/openings?(?:/|$))|"
    r"(/opportunities(?:/|$))|"
    r"(gh_jid=)|"
    r"(lever\.co/.+/.+)|"
    r"(ashbyhq\.com/.+/.+)",
    re.IGNORECASE,
)
_MAX_LINKS = 200


def fetch_html(client: httpx.Client, page_url: str) -> list[Job]:
    html = get_text(client, page_url)
    return parse_html(page_url, html)


def parse_html(page_url: str, html: str) -> list[Job]:
    structured = _jobs_from_json_ld(page_url, html)
    if structured:
        return structured
    links = _jobs_from_links(page_url, html)
    if links:
        return links
    if _looks_blocked(html):
        raise FetchError(
            "This careers page did not include job listings in the HTML. "
            "Use a Greenhouse, Lever, or Ashby board URL, or a listings page "
            "whose jobs are present in the page source."
        )
    return []


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in _TRACKING
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def _jobs_from_json_ld(page_url: str, html: str) -> list[Job]:
    tree = HTMLParser(html)
    jobs: list[Job] = []
    seen: set[str] = set()
    for node in tree.css("script"):
        script_type = (node.attributes.get("type") or "").lower()
        if "ld+json" not in script_type:
            continue
        raw = node.text(strip=False) or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for posting in _iter_postings(payload):
            job = _posting_to_job(page_url, posting)
            if job is None or job.id in seen:
                continue
            seen.add(job.id)
            jobs.append(job)
    return jobs


def _iter_postings(payload: object):
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_postings(item)
        return
    if not isinstance(payload, dict):
        return
    types = payload.get("@type", [])
    if isinstance(types, str):
        types = [types]
    if isinstance(types, list) and "JobPosting" in types:
        yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_postings(item)


def _posting_to_job(page_url: str, posting: dict) -> Job | None:
    raw_url = posting.get("url") or posting.get("sameAs") or page_url
    absolute = urljoin(page_url, str(raw_url))
    posted = posting.get("datePosted")
    posted_at = posted.strip() if isinstance(posted, str) and posted.strip() else None
    identifier = posting.get("identifier")
    id_value = ""
    if isinstance(identifier, dict):
        id_value = identifier.get("value") or ""
    elif isinstance(identifier, str):
        id_value = identifier
    job = job_or_none(
        id_value=id_value or canonical_url(absolute),
        title=posting.get("title"),
        url=canonical_url(absolute),
        location=_location_text(posting),
        team=_team_text(posting),
        posted_at=posted_at,
    )
    return job


def _location_text(posting: dict) -> str:
    if posting.get("jobLocationType") == "TELECOMMUTE":
        remote = "Remote"
    else:
        remote = ""
    locations = posting.get("jobLocation")
    if isinstance(locations, dict):
        locations = [locations]
    names: list[str] = []
    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue
            address = location.get("address")
            if isinstance(address, str) and address.strip():
                names.append(address.strip())
                continue
            if isinstance(address, dict):
                parts = [
                    address.get("addressLocality"),
                    address.get("addressRegion"),
                    address.get("addressCountry"),
                ]
                text = ", ".join(clean(part) for part in parts if clean(part))
                if text:
                    names.append(text)
    if names:
        return "; ".join(names)
    return remote


def _team_text(posting: dict) -> str:
    organization = posting.get("hiringOrganization")
    if isinstance(organization, dict):
        department = organization.get("department")
        if isinstance(department, dict):
            return department.get("name") or ""
        if isinstance(department, str):
            return department
    return ""


def _jobs_from_links(page_url: str, html: str) -> list[Job]:
    tree = HTMLParser(html)
    jobs: list[Job] = []
    seen: set[str] = set()
    page_key = canonical_url(page_url)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if not _JOB_HREF.search(parsed.path + "?" + parsed.query):
            continue
        key = canonical_url(absolute)
        if key.rstrip("/") == page_key.rstrip("/") or key in seen:
            continue
        title = _link_title(node.text(strip=True) or "", key)
        if not title:
            continue
        seen.add(key)
        job = job_or_none(id_value=key, title=title, url=key)
        if job is not None:
            jobs.append(job)
        if len(jobs) >= _MAX_LINKS:
            break
    return jobs


def _link_title(text: str, url: str) -> str:
    title = clean(text)
    if title and title.casefold() not in _NAV_TEXT and 4 <= len(title) <= 140:
        return title
    segment = urlsplit(url).path.rstrip("/").split("/")[-1]
    segment = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", segment)
    segment = re.sub(r"[-_]+", " ", segment).strip()
    if not re.search(r"[A-Za-z]", segment) or len(segment) < 4:
        return ""
    if segment.islower() or " " in segment:
        return segment.title()
    return segment


def _looks_blocked(html: str) -> bool:
    folded = html.casefold()
    cloudflare = "attention required" in folded and "cloudflare" in folded
    if "cf-browser-verification" in folded or cloudflare:
        return True
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    if len(text) < 500 and "enable javascript" in text.casefold():
        return True
    return "just a moment" in text.casefold() and "cloudflare" in folded
