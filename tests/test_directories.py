from jobalert.sources.directories import canonical_apply_url, parse_listing

LISTING = """
<table>
<tr>
<td>DoorDash</td>
<td>Operations Research Intern</td>
<td>Sunnyvale, CA</td>
<td><a href="https://job-boards.greenhouse.io/doordashusa/jobs/8273965?utm_source=Simplify">Apply</a></td>
</tr>
<tr>
<td>TELUS Digital</td>
<td>Software Engineering Intern Co-op</td>
<td>Vancouver, BC, Canada</td>
<td><a href="https://jobs.ashbyhq.com/telus-digital/63b0654a-9849-4d74-bc3f-94b2ccceb2c2/application?embed=true">Apply</a></td>
</tr>
<tr>
<td><del>Old Co</del></td>
<td><del>Software Engineer Intern</del></td>
<td>Remote</td>
<td><a href="https://jobs.lever.co/oldco/11111111-1111-1111-1111-111111111111">Apply</a></td>
</tr>
</table>
"""


def test_directory_keeps_related_ats_roles_and_drops_closed_rows():
    openings = parse_listing(LISTING, ["Software Engineer Intern", "Backend Intern"])
    assert len(openings) == 1
    job = openings[0].job
    assert job.site_name == "Ashby"
    assert job.title == "Software Engineering Intern Co-op"
    assert job.team == "TELUS Digital"
    assert job.url == "https://jobs.ashbyhq.com/telus-digital/63b0654a-9849-4d74-bc3f-94b2ccceb2c2"


def test_markdown_row_uses_the_greenhouse_apply_link():
    text = (
        "| DoorDash | Backend Engineer Intern | SF | "
        "[Apply](https://boards.greenhouse.io/doordashusa/jobs/10) |"
    )
    openings = parse_listing(text, ["Backend Engineer Intern"])
    assert openings[0].job.site_name == "Greenhouse"
    assert openings[0].job.url == "https://boards.greenhouse.io/doordashusa/jobs/10"


def test_board_home_page_is_not_a_job():
    assert canonical_apply_url("https://jobs.ashbyhq.com/airwallex") is None
