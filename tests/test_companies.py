import httpx

from jobalert.models import Job
from jobalert.sources.companies import _is_opening, find_board_url, resolve_board
from jobalert.store import Store


def test_ashby_link_is_the_company_board():
    html = """
    <a href="/about">About</a>
    <a href="https://jobs.ashbyhq.com/acme">Open roles</a>
    <a href="/careers">Careers</a>
    """
    assert find_board_url("https://acme.test", html) == "https://jobs.ashbyhq.com/acme"


def test_own_site_form_page_is_kept():
    html = """
    <a href="/blog">Blog</a>
    <script type="application/ld+json">
    {"@type":"JobPosting","title":"Backend Engineer","url":"https://acme.test/apply"}
    </script>
    """
    assert find_board_url("https://acme.test", html) == "https://acme.test"


def test_careers_link_is_used_when_there_is_no_ats():
    html = '<a href="/company/careers">Join us</a>'
    assert find_board_url("https://acme.test", html) == "https://acme.test/company/careers"


def test_resolve_tries_a_careers_path_when_the_home_page_has_no_link():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/careers":
            return httpx.Response(200, text="<html><body>Open roles</body></html>")
        return httpx.Response(404, text="missing")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert resolve_board(client, "https://acme.test") == "https://acme.test/careers"


def test_role_index_pages_are_not_openings():
    index = Job(
        id="index",
        title="Software Engineer Jobs in New York",
        url="https://www.ycombinator.com/jobs/role/software-engineer/new-york",
    )
    role = Job(
        id="role",
        title="Software Engineer",
        url="https://www.ycombinator.com/companies/candid-health/jobs/WIMeHdk-software-engineer",
    )
    assert _is_opening(index) is False
    assert _is_opening(role) is True


def test_a_known_careers_page_is_reread_and_a_missing_one_waits(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    store.upsert_companies(
        [
            {"company_key": "yc:new", "name": "New", "website": "https://new.test", "source": "YC"},
            {"company_key": "yc:found", "name": "Found", "website": "https://found.test", "source": "YC"},
            {"company_key": "yc:none", "name": "None", "website": "https://none.test", "source": "YC"},
        ]
    )
    store.mark_company("yc:found", "https://found.test/careers", "found")
    store.mark_company("yc:none", "", "none")
    keys = {row["company_key"] for row in store.companies_to_scan()}
    assert keys == {"yc:new", "yc:found"}
    store.close()
