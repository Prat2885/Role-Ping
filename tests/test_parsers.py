import pytest

from jobalert.adapters.ashby import parse_ashby
from jobalert.adapters.greenhouse import parse_greenhouse
from jobalert.adapters.html_page import canonical_url, parse_html
from jobalert.adapters.lever import parse_lever
from jobalert.models import FetchError


def test_parse_greenhouse_jobs():
    jobs = parse_greenhouse(
        {
            "jobs": [
                {
                    "id": 10,
                    "title": "Backend Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/10",
                    "location": {"name": "Bengaluru"},
                    "departments": [{"name": "Engineering"}],
                },
                {"id": 11, "title": "", "absolute_url": "https://example.com/x"},
            ]
        }
    )
    assert len(jobs) == 1
    assert jobs[0].id == "10"
    assert jobs[0].location == "Bengaluru"
    assert jobs[0].team == "Engineering"


def test_parse_lever_converts_created_at():
    jobs = parse_lever(
        [
            {
                "id": "abc",
                "text": "Designer",
                "hostedUrl": "https://jobs.lever.co/acme/abc",
                "categories": {"location": "Remote", "team": "Design"},
                "createdAt": 1_700_000_000_000,
            }
        ]
    )
    assert jobs[0].title == "Designer"
    assert jobs[0].posted_at == "2023-11-14T22:13:20Z"
    assert jobs[0].team == "Design"


def test_parse_ashby_skips_unlisted_jobs():
    jobs = parse_ashby(
        {
            "jobs": [
                {
                    "id": "listed",
                    "title": "Analyst",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/listed",
                    "location": "Mumbai",
                    "department": "Finance",
                    "isListed": True,
                    "publishedAt": "2024-05-01T00:00:00.000Z",
                },
                {
                    "id": "hidden",
                    "title": "Secret",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/hidden",
                    "isListed": False,
                },
            ]
        }
    )
    assert [job.id for job in jobs] == ["listed"]
    assert jobs[0].posted_at == "2024-05-01T00:00:00.000Z"


def test_html_prefers_job_posting_json_ld():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{
        "@type": "JobPosting",
        "title": "Data Scientist",
        "url": "/jobs/data-scientist",
        "datePosted": "2024-01-02",
        "jobLocationType": "TELECOMMUTE",
        "hiringOrganization": {"@type": "Organization", "department": "Research"}
      }]}
      </script>
    </head>
    <body><a href="/jobs/ignore-me">Ignore Me Please</a></body>
    </html>
    """
    jobs = parse_html("https://example.com/careers", html)
    assert len(jobs) == 1
    assert jobs[0].title == "Data Scientist"
    assert jobs[0].url == "https://example.com/jobs/data-scientist"
    assert jobs[0].location == "Remote"
    assert jobs[0].team == "Research"


def test_html_reads_job_links_and_ignores_navigation():
    html = """
    <a href="/about">About</a>
    <a href="/jobs/senior-engineer?utm_source=homepage">Senior Engineer</a>
    <a href="https://example.com/careers">Careers</a>
    """
    jobs = parse_html("https://example.com/careers", html)
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Engineer"
    assert jobs[0].id == "https://example.com/jobs/senior-engineer"


def test_html_blocked_page_is_an_error():
    html = "<html><title>Just a moment...</title>Cloudflare</html>"
    with pytest.raises(FetchError):
        parse_html("https://example.com/careers", html)


def test_canonical_url_drops_tracking_params():
    assert (
        canonical_url("https://Example.com/jobs/Role/?utm_source=x&gh_jid=1")
        == "https://example.com/jobs/Role?gh_jid=1"
    )
