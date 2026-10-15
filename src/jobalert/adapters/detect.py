from enum import Enum
from urllib.parse import parse_qs, urlparse
from dataclasses import dataclass


class BoardKind(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    HTML = "html"


@dataclass(frozen=True)
class BoardTarget:
    kind: BoardKind
    token: str
    europe: bool
    page_url: str


def detect_board(url: str) -> BoardTarget:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    parts = [part for part in parsed.path.split("/") if part]
    europe = ".eu." in host or host.startswith("eu.")

    greenhouse = _greenhouse_token(host, parts, parsed.query)
    if greenhouse:
        return BoardTarget(BoardKind.GREENHOUSE, greenhouse, europe, url)

    lever = _lever_token(host, parts)
    if lever:
        return BoardTarget(BoardKind.LEVER, lever, europe, url)

    ashby = _ashby_token(host, parts)
    if ashby:
        return BoardTarget(BoardKind.ASHBY, ashby, False, url)

    return BoardTarget(BoardKind.HTML, "", False, url)


def _greenhouse_token(host: str, parts: list[str], query: str) -> str | None:
    if host in {"boards-api.greenhouse.io", "boards-api.eu.greenhouse.io"}:
        if len(parts) >= 3 and parts[0] == "v1" and parts[1] == "boards":
            return parts[2]
        return None
    if not host.endswith(".greenhouse.io"):
        return None
    if parts and parts[0] == "embed":
        token = parse_qs(query).get("for", [""])[0].strip()
        return token or None
    if not parts:
        return None
    return parts[0]


def _lever_token(host: str, parts: list[str]) -> str | None:
    if host in {"api.lever.co", "api.eu.lever.co"}:
        if len(parts) >= 3 and parts[0] == "v0" and parts[1] == "postings":
            return parts[2]
        return None
    if host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        return parts[0]
    return None


def _ashby_token(host: str, parts: list[str]) -> str | None:
    if host == "jobs.ashbyhq.com" and parts:
        return parts[0]
    return None
