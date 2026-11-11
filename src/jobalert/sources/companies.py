"""Find each company's careers page once, then reread that page for openings.

Ashby, Greenhouse, and Lever links are stored as the company's board. A company
that only lists roles on its own site keeps that careers URL, form and all.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from jobalert.adapters.common import clean, get_json
from jobalert.adapters.detect import BoardKind, detect_board
from jobalert.adapters.html_page import _jobs_from_json_ld, parse_html
from jobalert.config import SiteConfig
from jobalert.fetch import fetch_site
from jobalert.models import FetchError
from jobalert.sources.boards import Opening, replace_site, title_matches
from jobalert.store import Store

_WORKERS = 12
_YC_HIRING = "https://yc-oss.github.io/api/companies/hiring.json"
_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com")
_CAREER_PATHS = ("/careers", "/jobs", "/join", "/openings")
_CAREER_TEXT = ("career", "we're hiring", "were hiring", "join us", "open roles", "view jobs", "see jobs")
_SKIP_HOSTS = (
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "medium.com",
    "github.com",
)


def fetch_company_openings(
    client: httpx.Client,
    store: Store,
    queries: list[str],
) -> list[Opening]:
    _sync_yc_companies(client, store)
    due = store.companies_to_scan()
    total, waiting = store.company_counts()
    if not due:
        return []
    logging.info(
        "Reading %s company careers pages (%s of %s not visited yet).",
        len(due),
        waiting,
        total,
    )
    openings: list[Opening] = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = [pool.submit(_inspect_company, company, queries) for company in due]
        for future in as_completed(futures):
            company_key, board_url, status, found, note = future.result()
            store.mark_company(company_key, board_url, status)
            if note:
                logging.debug("%s", note)
            openings.extend(found)
    return openings


def find_board_url(page_url: str, html: str) -> str | None:
    """Return an ATS board or this site's careers page, if the HTML points at one."""
    ats: list[str] = []
    careers: list[str] = []
    tree = HTMLParser(html)
    for node in tree.css("a[href]")[:400]:
        href = node.attributes.get("href") or ""
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        if any(host == skip or host.endswith("." + skip) for skip in _SKIP_HOSTS):
            continue
        target = detect_board(absolute)
        if target.kind is not BoardKind.HTML and any(part in host for part in _ATS_HOSTS):
            ats.append(absolute.split("#", 1)[0])
            continue
        text = (node.text(strip=True) or "").casefold()
        path = parsed.path.casefold()
        if any(piece in path for piece in _CAREER_PATHS) or any(phrase in text for phrase in _CAREER_TEXT):
            if path not in {"", "/"}:
                careers.append(absolute.split("#", 1)[0])
    if ats:
        return ats[0]
    if _jobs_from_json_ld(page_url, html):
        return page_url
    if careers:
        return careers[0]
    return None


def resolve_board(client: httpx.Client, website: str) -> str | None:
    """Open the company site and return the careers or ATS URL."""
    home = _absolute_website(website)
    page = _get(client, home)
    if page is not None and page.status_code < 400:
        found = find_board_url(str(page.url), page.text)
        if found:
            return found
    root = home.rstrip("/")
    for suffix in _CAREER_PATHS:
        candidate = root + suffix
        response = _get(client, candidate)
        if response is None or response.status_code >= 400:
            continue
        path = urlparse(str(response.url)).path
        if path in {"", "/"}:
            continue
        return str(response.url).split("#", 1)[0]
    return None


def _inspect_company(company: dict, queries: list[str]):
    with httpx.Client(follow_redirects=True, timeout=12) as client:
        try:
            return _collect_company(client, company, queries)
        except Exception as exc:
            return (
                company["company_key"],
                company.get("board_url") or "",
                "error",
                [],
                f"{company['name']}: {exc}",
            )


def _collect_company(client: httpx.Client, company: dict, queries: list[str]):
    board_url = company.get("board_url") or ""
    if company.get("status") != "found" or not board_url:
        board_url = resolve_board(client, company["website"]) or ""
    if not board_url:
        return company["company_key"], "", "none", [], f"{company['name']}: no public careers page."
    try:
        jobs = _read_board(client, company["name"], board_url)
    except FetchError as exc:
        return company["company_key"], board_url, "error", [], f"{company['name']}: {exc}"
    openings: list[Opening] = []
    for job in jobs:
        if not _could_match(job.title, queries):
            continue
        named = replace_site(job, company["name"])
        if not _is_opening(named):
            continue
        if not named.team:
            named = replace(named, team=company["name"])
        openings.append(Opening(job=named, text=f"{named.title} {named.location} {named.team}"))
    note = f"{company['name']}: {len(openings)} candidate role(s) at {board_url}."
    return company["company_key"], board_url, "found", openings, note


def _could_match(title: str, queries: list[str]) -> bool:
    if title_matches(title, queries):
        return True
    folded = title.casefold()
    hints = (
        "engineer",
        "developer",
        "intern",
        "fullstack",
        "full stack",
        "full-stack",
        "backend",
        "back end",
        "software",
        "sde",
    )
    return any(hint in folded for hint in hints)


def _is_opening(job) -> bool:
    path = urlparse(job.url).path.casefold()
    if "/jobs/role/" in path:
        return False
    title = job.title.casefold()
    if title.endswith(" jobs") or " jobs in " in title:
        return False
    return True


def _read_board(client: httpx.Client, name: str, board_url: str) -> list:
    target = detect_board(board_url)
    if target.kind is BoardKind.HTML:
        response = _get(client, board_url)
        if response is None or response.status_code >= 400:
            raise FetchError(f"Could not read {board_url}")
        return parse_html(str(response.url), response.text)
    return fetch_site(client, SiteConfig(name=name, url=board_url))


def _sync_yc_companies(client: httpx.Client, store: Store) -> None:
    try:
        payload = get_json(client, _YC_HIRING)
    except FetchError as exc:
        logging.info("YC company list was not refreshed: %s", exc)
        return
    if not isinstance(payload, list):
        logging.info("YC company list was not a list of companies.")
        return
    companies: list[dict] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        website = _absolute_website(item.get("website") or "")
        slug = clean(item.get("slug") or item.get("name"))
        name = clean(item.get("name")) or slug
        if not website or not slug or not name:
            continue
        key = f"yc:{slug.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        companies.append(
            {
                "company_key": key,
                "name": name,
                "website": website,
                "source": "YC",
            }
        )
    store.upsert_companies(companies)


def _absolute_website(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return text.split("#", 1)[0]


def _get(client: httpx.Client, url: str) -> httpx.Response | None:
    try:
        return client.get(
            url,
            headers={"User-Agent": _BROWSER, "Accept": "text/html"},
            timeout=12,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None
