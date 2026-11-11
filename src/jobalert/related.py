"""Turn one job title into the related titles worth searching."""

_ENGINEERING = (
    "Backend Intern",
    "Backend Engineer",
    "Backend Developer",
    "Full Stack Engineer",
    "Full Stack Engineer Intern",
    "Fullstack Engineer",
    "Software Engineer",
    "Software Engineer Intern",
    "Software Developer",
)


def related_queries(title: str, level: str) -> list[str]:
    """Return search titles near this role, including the original title."""
    family = _family(title)
    if family == "engineering":
        candidates = [title, *_ENGINEERING]
    else:
        from jobalert.cvtext import strip_level_words

        broader = strip_level_words(title)
        candidates = [title, broader]
    if level not in {"intern", "junior"}:
        candidates = [item for item in candidates if "intern" not in item.casefold()]
    queries: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = " ".join(str(item).split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        queries.append(text)
    return queries[:12]


def _family(title: str) -> str:
    folded = title.casefold().replace("-", " ")
    tokens = (
        "backend",
        "back end",
        "fullstack",
        "full stack",
        "frontend",
        "front end",
        "software",
        "developer",
        "engineer",
    )
    if any(token in folded for token in tokens):
        return "engineering"
    return "other"
