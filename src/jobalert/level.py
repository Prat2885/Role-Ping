import re

_ORDER = ("intern", "junior", "mid", "senior", "staff", "director")
_STATED = (
    ("intern", "intern"),
    ("entry", "junior"),
    ("junior", "junior"),
    ("mid", "mid"),
    ("senior", "senior"),
    ("staff", "staff"),
    ("principal", "staff"),
    ("director", "director"),
    ("executive", "director"),
)
_MIN_YEARS = re.compile(
    r"(?:at least\s+)?(\d{1,2})\s*\+?\s*(?:years|yrs)\b",
    re.IGNORECASE,
)
_YEAR_RANGE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years|yrs)\b",
    re.IGNORECASE,
)


def job_fits(profile: dict, title: str, text: str = "", stated_level: str | None = None) -> bool:
    """Return whether a posting is close to the CV seniority band."""
    profile_level = str(profile.get("level") or "mid")
    job_level = _job_level(title, stated_level)
    if job_level is not None and abs(_rank(job_level) - _rank(profile_level)) > 1:
        return False
    years = profile.get("years")
    minimum = _minimum_years(text)
    if years is not None and minimum is not None and float(years) + 0.5 < minimum:
        return False
    return True


def level_distance(profile: dict, title: str, stated_level: str | None = None) -> int:
    job_level = _job_level(title, stated_level)
    if job_level is None:
        return 1
    return abs(_rank(job_level) - _rank(str(profile.get("level") or "mid")))


def _job_level(title: str, stated_level: str | None) -> str | None:
    from jobalert.cvtext import level_in_text

    found = level_in_text(title)
    if found:
        return found
    if not stated_level:
        return None
    folded = stated_level.casefold()
    for phrase, level in _STATED:
        if phrase in folded:
            return level
    return None


def _rank(level: str) -> int:
    try:
        return _ORDER.index(level)
    except ValueError:
        return _ORDER.index("mid")


def _minimum_years(text: str) -> int | None:
    ranged = _YEAR_RANGE.search(text)
    if ranged:
        return int(ranged.group(1))
    match = _MIN_YEARS.search(text)
    if match:
        return int(match.group(1))
    return None
