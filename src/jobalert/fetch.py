import httpx

from jobalert.adapters.ashby import fetch_ashby
from jobalert.adapters.detect import BoardKind, detect_board
from jobalert.adapters.greenhouse import fetch_greenhouse
from jobalert.adapters.html_page import fetch_html
from jobalert.adapters.lever import fetch_lever
from jobalert.config import SiteConfig
from jobalert.models import Job

USER_AGENT = "job-alert-agent/0.1 (personal careers watcher)"


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        },
    )


def fetch_site(client: httpx.Client, site: SiteConfig) -> list[Job]:
    target = detect_board(site.url)
    if target.kind is BoardKind.GREENHOUSE:
        return fetch_greenhouse(client, target)
    if target.kind is BoardKind.LEVER:
        return fetch_lever(client, target)
    if target.kind is BoardKind.ASHBY:
        return fetch_ashby(client, target)
    return fetch_html(client, target.page_url)
