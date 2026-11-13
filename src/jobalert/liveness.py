import httpx
from selectolax.lexbor import LexborHTMLParser

_CLOSED = (
    "no longer accepting",
    "no longer available",
    "no longer exists",
    "position has been filled",
    "this position has been filled",
    "job has expired",
    "this job has expired",
    "posting has expired",
    "this job is closed",
    "job is no longer",
    "applications are closed",
    "not accepting applications",
    "vacancy has been filled",
    "page not found",
    "job not found",
)
_APPLY = ("apply", "application", "submit your")
_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def assess_page(status_code: int, html: str) -> str:
    """Return live, closed, or unknown for an apply page."""
    if status_code in {404, 410, 451}:
        return "closed"
    if status_code >= 400:
        return "unknown"
    folded_html = html.casefold()
    if "cf-browser-verification" in folded_html or (
        "just a moment" in folded_html and "cloudflare" in folded_html
    ):
        return "unknown"
    text = _visible_text(html).casefold()
    if any(phrase in text for phrase in _CLOSED):
        return "closed"
    if any(phrase in text for phrase in _APPLY):
        return "live"
    return "unknown"


def page_is_live(client: httpx.Client, url: str) -> str:
    state, _text = read_apply_page(client, url)
    return state


def read_apply_page(client: httpx.Client, url: str) -> tuple[str, str]:
    """Return whether the apply page is open, and the visible text."""
    try:
        response = client.get(
            url,
            timeout=15,
            headers={"User-Agent": _BROWSER, "Accept": "text/html"},
        )
    except httpx.HTTPError:
        return "unknown", ""
    body = response.text[:1_000_000] if response.text else ""
    state = listing_state(response.status_code, body, str(response.url))
    return state, _visible_text(body)[:8000]


def listing_state(status_code: int, html: str, url: str = "") -> str:
    """Return live, closed, or unknown. A page that loads and is not closed is live."""
    del url
    if status_code in {404, 410, 451}:
        return "closed"
    if status_code >= 400:
        return "unknown"
    folded_html = html.casefold()
    if "cf-browser-verification" in folded_html or (
        "just a moment" in folded_html and "cloudflare" in folded_html
    ):
        return "unknown"
    text = _visible_text(html).casefold()
    if any(phrase in text for phrase in _CLOSED):
        return "closed"
    return "live"


def _visible_text(html: str) -> str:
    tree = LexborHTMLParser(html)
    if tree.body is not None:
        return tree.body.text(separator=" ", strip=True)
    return tree.text(separator=" ", strip=True)
