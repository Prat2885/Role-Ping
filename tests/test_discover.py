from jobalert.discover import choose_openings
from jobalert.models import Job
from jobalert.sources.boards import Opening
from jobalert.store import Store


def _opening(job_id: str, title: str, expired: bool = False) -> Opening:
    return Opening(
        job=Job(
            id=job_id,
            title=title,
            url=f"https://example.com/{job_id}",
            team="Acme",
            site_name="Remotive",
        ),
        text=title,
        expired=expired,
    )


def test_choose_openings_keeps_only_live_matches_at_the_right_level():
    profile = {"level": "senior", "years": 7}
    openings = [
        _opening("intern", "Intern Engineer"),
        _opening("closed", "Senior Engineer"),
        _opening("live", "Senior Engineer"),
        _opening("old", "Senior Engineer", expired=True),
    ]
    states = {"https://example.com/closed": "closed", "https://example.com/live": "live"}
    chosen, closed = choose_openings(
        profile,
        openings,
        seen=lambda site, job_id: False,
        is_live=lambda job: states.get(job.url, "unknown"),
    )
    assert [job.id for job in chosen] == ["live"]
    assert ("Remotive", "closed") in closed
    assert ("Remotive", "old") in closed


def test_choose_openings_includes_every_live_match():
    profile = {"level": "intern", "years": 0.3}
    openings = [_opening(str(number), "Software Engineer Intern") for number in range(25)]
    chosen, closed = choose_openings(
        profile,
        openings,
        seen=lambda site, job_id: False,
        is_live=lambda job: "live",
    )
    assert len(chosen) == 25
    assert closed == []


def test_choose_openings_skips_jobs_already_known():
    chosen, closed = choose_openings(
        {"level": "senior", "years": 7},
        [_opening("live", "Senior Engineer")],
        seen=lambda site, job_id: True,
        is_live=lambda job: "live",
    )
    assert chosen == []
    assert closed == []


def test_closed_jobs_are_remembered(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    store.mark_closed("Remotive", "closed")
    assert store.is_known("Remotive", "closed") is True
    assert store.is_known("Remotive", "other") is False
    store.close()
