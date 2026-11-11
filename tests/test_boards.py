from jobalert.sources.boards import (
    parse_arbeitnow,
    parse_himalayas,
    parse_jobicy,
    parse_muse,
    parse_remoteok,
    parse_remotive,
    parse_weworkremotely,
    parse_yc,
    title_matches,
)


def test_title_matches_every_word_of_one_query():
    assert title_matches("Backend Engineer", ["Senior Software Engineer"]) is False
    assert title_matches("Full Stack Engineer", ["Full Stack Engineer", "Backend Engineer"]) is True
    assert title_matches("Nurse", ["Senior Software Engineer"]) is False


def test_parse_remotive_keeps_the_company_and_source():
    openings = parse_remotive(
        {
            "jobs": [
                {
                    "id": 5,
                    "title": "Senior Engineer",
                    "url": "https://remotive.com/remote-jobs/senior-engineer",
                    "company_name": "Acme",
                    "candidate_required_location": "India",
                    "description": "<p>5+ years</p>",
                    "publication_date": "2026-01-01T00:00:00",
                }
            ]
        },
        ["engineer"],
    )
    assert openings[0].job.site_name == "Remotive"
    assert openings[0].job.team == "Acme"
    assert "5+ years" in openings[0].text


def test_parse_remoteok_skips_the_legal_banner():
    openings = parse_remoteok(
        [
            {"legal": "Please credit Remote OK"},
            {
                "id": 9,
                "position": "Engineer",
                "url": "https://remoteok.com/remote-jobs/engineer",
                "apply_url": "https://example.com/apply/9",
                "company": "Northwind",
                "epoch": 1_700_000_000,
            },
        ],
        ["engineer"],
    )
    assert len(openings) == 1
    assert openings[0].job.url == "https://example.com/apply/9"
    assert openings[0].job.site_name == "Remote OK"
    assert openings[0].job.posted_at == "2023-11-14T22:13:20Z"


def test_parse_himalayas_marks_expired_jobs():
    openings = parse_himalayas(
        {
            "jobs": [
                {
                    "guid": "job-1",
                    "title": "Engineer",
                    "applicationLink": "https://himalayas.app/jobs/1",
                    "companyName": "Pavago",
                    "seniority": ["Senior"],
                    "expiryDate": 1_600_000_000,
                    "locationRestrictions": ["India"],
                }
            ]
        },
        ["engineer"],
    )
    assert openings[0].expired is True
    assert openings[0].stated_level == "Senior"
    assert openings[0].job.site_name == "Himalayas"


def test_parse_arbeitnow():
    openings = parse_arbeitnow(
        {
            "data": [
                {
                    "slug": "engineer-1",
                    "title": "Engineer",
                    "url": "https://www.arbeitnow.com/jobs/engineer-1",
                    "company_name": "Sound",
                    "location": "Berlin",
                }
            ]
        },
        ["engineer"],
    )
    assert openings[0].job.id == "engineer-1"
    assert openings[0].job.site_name == "Arbeitnow"


def test_parse_yc_jobicy_muse_and_we_work_remotely():
    yc = parse_yc(
        {
            "hits": [
                {
                    "id": 42,
                    "title": "Backend Intern",
                    "company_name": "Acme",
                    "locations": ["Remote"],
                    "min_experience": 0,
                }
            ]
        },
        ["backend"],
    )
    assert yc[0].job.site_name == "YC Work at a Startup"
    assert yc[0].job.url == "https://www.workatastartup.com/jobs/42"
    assert yc[0].job.team == "Acme"

    directory = parse_yc(
        {
            "jobs": [
                {
                    "id": 75959,
                    "title": "Software Engineer - Backend",
                    "companyName": "Infinity",
                    "location": "Bengaluru, KA, IN",
                    "jobType": "Full-time",
                }
            ]
        },
        ["Backend Engineer"],
    )
    assert directory[0].job.url == "https://www.workatastartup.com/jobs/75959"
    assert directory[0].job.location == "Bengaluru, KA, IN"
    assert directory[0].job.team == "Infinity"

    jobicy = parse_jobicy(
        {
            "jobs": [
                {
                    "id": 7,
                    "jobTitle": "Backend Intern",
                    "url": "https://jobicy.com/jobs/7",
                    "companyName": "North",
                    "jobGeo": "India",
                    "jobLevel": "Entry",
                }
            ]
        },
        ["backend"],
    )
    assert jobicy[0].job.site_name == "Jobicy"
    assert jobicy[0].stated_level == "Entry"

    muse = parse_muse(
        {
            "results": [
                {
                    "id": 3,
                    "name": "Backend Intern",
                    "levels": [{"name": "Entry Level"}],
                    "company": {"name": "Muse Co"},
                    "locations": [{"name": "Pune"}],
                    "refs": {"landing_page": "https://www.themuse.com/jobs/3"},
                }
            ]
        },
        ["backend"],
    )
    assert muse[0].job.site_name == "The Muse"
    assert muse[0].job.location == "Pune"

    wwr = parse_weworkremotely(
        """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Acme: Backend Intern</title>
            <link>https://weworkremotely.com/remote-jobs/backend-intern</link>
            <description>Internship</description>
          </item>
        </channel></rss>
        """,
        ["backend"],
    )
    assert wwr[0].job.site_name == "We Work Remotely"
    assert wwr[0].job.team == "Acme"
    assert wwr[0].job.title == "Backend Intern"
