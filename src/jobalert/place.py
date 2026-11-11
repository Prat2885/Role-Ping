"""Keep jobs in India, and remote jobs that are not locked to another country."""

import re

_INDIA = (
    "india",
    "bengaluru",
    "bangalore",
    "mumbai",
    "bombay",
    "delhi",
    "noida",
    "gurgaon",
    "gurugram",
    "hyderabad",
    "pune",
    "chennai",
    "kolkata",
    "calcutta",
    "ahmedabad",
    "jaipur",
    "kochi",
    "cochin",
    "indore",
    "chandigarh",
    "lucknow",
    "goa",
    "mysuru",
    "mysore",
    "thiruvananthapuram",
    "trivandrum",
    "coimbatore",
    "nagpur",
    "surat",
    "vadodara",
    "bhopal",
    "bhubaneswar",
    "visakhapatnam",
    "faridabad",
    "navi mumbai",
)
_INDIA_CODE = re.compile(
    r"\b(?:ka|mh|dl|tn|ts|tg|wb|gj|rj|kl|up|hr|pb|ga|mp|ap|od|uk|hp|jh|cg|br),?\s+in\b",
    re.IGNORECASE,
)
_OPEN_REMOTE = ("worldwide", "anywhere", "global", "international", "work from anywhere")
_REMOTE = ("remote", "work from home", "work-from-home", "wfh", "distributed")
_RESTRICTED = re.compile(
    r"remote\s*\([^)]*\b(?:us|u\.s\.?|usa|uk|eu|europe|canada|ca)\b[^)]*\)|"
    r"\b(?:us|u\.s\.?|usa|uk|eu|canada)\s+only\b|"
    r"\bwithin the (?:us|u\.s\.?|usa|uk|united states|united kingdom|eu|canada)\b|"
    r"\beurope only\b",
    re.IGNORECASE,
)


def place_fits(title: str, location: str = "", text: str = "") -> bool:
    """True for India, for remote work from India, or when the posting names no place.

    An office outside India is rejected. A careers link that does not name a city
    is kept so the later match can still read it.
    """
    blob = " ".join(part for part in (title, location, text) if part).casefold()
    if not blob.strip():
        return True
    if _in_india(blob):
        return True
    if any(phrase in blob for phrase in _OPEN_REMOTE):
        return True
    remote = any(phrase in blob for phrase in _REMOTE)
    if remote and _RESTRICTED.search(blob) is None:
        return True
    if remote:
        return False
    if _abroad(blob):
        return False
    return True


_ABROAD = (
    "united states",
    "united kingdom",
    "u.s.a",
    "u.s.",
    "usa",
    "san francisco",
    "palo alto",
    "new york",
    "los angeles",
    "boston",
    "seattle",
    "austin",
    "london",
    "singapore",
    "toronto",
    "sydney",
    "shanghai",
    "beijing",
    "berlin",
    "paris",
    "amsterdam",
    "dublin",
    "munich",
    "zurich",
    "tel aviv",
    "dubai",
    "redwood",
)


def _abroad(blob: str) -> bool:
    return any(re.search(rf"\b{re.escape(name)}\b", blob) for name in _ABROAD)


def _in_india(blob: str) -> bool:
    if _INDIA_CODE.search(blob):
        return True
    return any(re.search(rf"\b{re.escape(name)}\b", blob) for name in _INDIA)
