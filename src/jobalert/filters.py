from jobalert.models import Job


def _terms(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def job_matches(job: Job, keywords: list[str], locations: list[str]) -> bool:
    """Return whether a job passes the keyword and location filters.

    An empty filter list matches everything. Keywords are compared with the
    title and team. Locations are compared with the location text.
    """
    keyword_terms = _terms(keywords)
    if keyword_terms:
        haystack = f"{job.title} {job.team}".casefold()
        if not any(term.casefold() in haystack for term in keyword_terms):
            return False

    location_terms = _terms(locations)
    if location_terms:
        location = job.location.casefold()
        if not any(term.casefold() in location for term in location_terms):
            return False
    return True
