from jobalert.filters import job_matches
from jobalert.models import Job


def _job() -> Job:
    return Job(
        id="1",
        title="Senior Python Engineer",
        url="https://example.com/jobs/1",
        location="Bengaluru, India",
        team="Platform",
    )


def test_empty_filters_match_everything():
    assert job_matches(_job(), [], []) is True


def test_keywords_match_title_or_team_without_case():
    job = _job()
    assert job_matches(job, ["python"], []) is True
    assert job_matches(job, ["platform"], []) is True
    assert job_matches(job, ["designer"], []) is False


def test_locations_match_part_of_the_location():
    job = _job()
    assert job_matches(job, [], ["india"]) is True
    assert job_matches(job, ["python"], ["remote"]) is False
