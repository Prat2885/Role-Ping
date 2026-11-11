import re
from datetime import date
from pathlib import Path

from jobalert.models import ConfigError
from jobalert.related import related_queries

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_RANGE = re.compile(
    r"(?P<start>(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}/\d{4})"
    r"\s*(?:-|–|—|\bto\b)\s*"
    r"(?P<end>present|current|now|(?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{1,2}/\d{4})",
    re.IGNORECASE,
)
_YEARS_PHRASE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s+years\b", re.IGNORECASE)
_ROLE_WORDS = (
    "engineer",
    "developer",
    "designer",
    "manager",
    "analyst",
    "scientist",
    "accountant",
    "consultant",
    "architect",
    "recruiter",
    "marketer",
    "marketing",
    "specialist",
    "director",
    "officer",
    "associate",
    "executive",
    "lawyer",
    "nurse",
    "teacher",
    "product",
    "programmer",
    "administrator",
)
_LEVEL_PHRASES = (
    ("head of", "director"),
    ("entry-level", "junior"),
    ("entry level", "junior"),
    ("mid-level", "mid"),
    ("mid level", "mid"),
    ("principal", "staff"),
    ("director", "director"),
    ("staff", "staff"),
    ("senior", "senior"),
    ("junior", "junior"),
    ("intern", "intern"),
    ("lead", "senior"),
)


class ProfileError(ConfigError):
    """The CV could not be turned into a search profile."""


def read_cv(path: Path) -> str:
    if not path.is_file():
        raise ProfileError(f"CV file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix == ".docx":
        text = _read_docx(path)
    elif suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ProfileError("Upload a PDF, DOCX, or TXT CV.")
    if len(text.strip()) < 40:
        raise ProfileError("Could not read enough text from that CV.")
    return text


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def level_in_text(text: str) -> str | None:
    folded = text.casefold()
    for phrase, level in _LEVEL_PHRASES:
        if phrase in folded:
            return level
    return None


def strip_level_words(title: str) -> str:
    cleaned = title
    for phrase, _level in _LEVEL_PHRASES:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def build_queries(title: str) -> list[str]:
    title = _clean_title(title)
    family = strip_level_words(title)
    queries: list[str] = []
    for item in (title, family):
        if item and item.casefold() not in {query.casefold() for query in queries}:
            queries.append(item)
    return queries[:2]


def infer_profile(text: str, source_name: str) -> dict:
    roles = _roles(text)
    titles = [role[0] for role in roles if role[0]]
    if not titles:
        titles = _title_lines(text)
    years = _years(roles)
    if years is None:
        phrase = _YEARS_PHRASE.search(text)
        if phrase:
            years = float(phrase.group(1))
    if not titles and years is None:
        raise ProfileError(
            "Could not find roles or dates in this CV. "
            "Include job titles and dates, then upload it again."
        )
    latest = titles[0] if titles else ""
    level = level_in_text(latest) if latest else None
    if level is None and years is not None:
        level = _level_from_years(years)
    if level is None:
        level = "mid"
    if not latest:
        raise ProfileError(
            "Could not find a job title in this CV. "
            "Include a title such as Software Engineer, then upload it again."
        )
    return {
        "source_file": source_name,
        "years": None if years is None else round(years, 1),
        "level": level,
        "titles": titles[:5],
        "queries": related_queries(latest, level),
    }


_SKIP_SECTIONS = {"education", "projects", "skills", "certifications", "coursework"}


def _roles(text: str) -> list[tuple[str, date, date]]:
    lines = [line.strip() for line in text.splitlines()]
    found: list[tuple[str, date, date]] = []
    for index, line in enumerate(lines):
        if _section(lines, index) in _SKIP_SECTIONS:
            continue
        for match in _RANGE.finditer(line):
            start = _to_date(match.group("start"), end=False)
            end = _to_date(match.group("end"), end=True)
            if start is None or end is None or end < start:
                continue
            prefix = _clean_title(line[: match.start()])
            if prefix and len(prefix.split()) <= 8:
                title = prefix
            else:
                title = _title_before(lines, index)
            found.append((title, start, end))
    found.sort(key=lambda role: role[2], reverse=True)
    return found


def _section(lines: list[str], index: int) -> str:
    for back in range(index, -1, -1):
        key = " ".join(lines[back].split()).casefold().strip(":")
        if key in _SKIP_SECTIONS or key in {"experience", "work experience", "professional experience"}:
            return key
    return ""


def _title_before(lines: list[str], index: int) -> str:
    candidates: list[str] = []
    for back in range(index - 1, max(-1, index - 4), -1):
        line = _clean_title(lines[back])
        if not line or _RANGE.search(line):
            continue
        candidates.append(line)
    for line in candidates:
        if _looks_like_title(line):
            return line
    return candidates[0] if candidates else ""


def _title_lines(text: str) -> list[str]:
    titles: list[str] = []
    for raw in text.splitlines():
        line = _clean_title(raw)
        if line and _looks_like_title(line) and len(line) <= 80:
            titles.append(line)
    return titles


def _looks_like_title(line: str) -> bool:
    folded = line.casefold()
    return any(re.search(rf"\b{re.escape(word)}\b", folded) for word in _ROLE_WORDS)


def _clean_title(line: str) -> str:
    line = re.split(r"[|•]", line)[0]
    return " ".join(line.split())


def _to_date(token: str, end: bool) -> date | None:
    token = token.strip().casefold().rstrip(".")
    if token in {"present", "current", "now"}:
        today = date.today()
        return date(today.year, today.month, 1)
    slash = re.fullmatch(r"(\d{1,2})/(\d{4})", token)
    if slash:
        month, year = int(slash.group(1)), int(slash.group(2))
        if 1 <= month <= 12:
            return date(year, month, 1)
        return None
    named = re.fullmatch(r"([a-z]+)\.?\s+(\d{4})", token)
    if named:
        month = _MONTHS.get(named.group(1)[:3])
        if month is None:
            return None
        return date(int(named.group(2)), month, 1)
    year_only = re.fullmatch(r"(\d{4})", token)
    if year_only:
        return date(int(year_only.group(1)), 12 if end else 1, 1)
    return None


def _years(roles: list[tuple[str, date, date]]) -> float | None:
    if not roles:
        return None
    intervals = sorted((start.toordinal(), end.toordinal()) for _title, start, end in roles)
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    days = sum(end - start for start, end in merged)
    return days / 365.25


def _level_from_years(years: float) -> str:
    if years < 1:
        return "intern"
    if years < 3:
        return "junior"
    if years < 6:
        return "mid"
    if years < 10:
        return "senior"
    return "staff"
