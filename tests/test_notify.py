from jobalert.models import Job
from jobalert.notify import build_message


def _job(title: str, site: str) -> Job:
    return Job(
        id=title,
        title=title,
        url=f"https://example.com/{title}",
        location="Pune",
        team="Engineering",
        site_name=site,
    )


def test_single_job_subject_names_the_role():
    subject, body = build_message("[Jobs]", [_job("Writer", "Acme")])
    assert subject == "[Jobs] Writer — Acme"
    assert "Location: Pune" in body
    assert "https://example.com/Writer" in body


def test_several_jobs_use_a_count_subject():
    subject, body = build_message(
        "[Jobs]",
        [_job("Writer", "Acme"), _job("Editor", "Acme")],
    )
    assert subject == "[Jobs] 2 new openings"
    assert body.startswith("2 new job openings:")
