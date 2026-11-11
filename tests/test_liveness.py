from jobalert.liveness import assess_page, listing_state


def test_missing_page_is_closed():
    assert assess_page(404, "not found") == "closed"


def test_open_apply_page_is_live():
    html = "<html><body><h1>Backend Engineer</h1><a>Apply now</a></body></html>"
    assert assess_page(200, html) == "live"


def test_filled_role_is_closed():
    html = "<html><body>This position has been filled.</body></html>"
    assert assess_page(200, html) == "closed"


def test_loaded_job_page_without_the_word_apply_is_live():
    html = "<html><body><h1>Software Engineer</h1><p>Bengaluru</p></body></html>"
    assert listing_state(200, html, "https://example.com/careers/software-engineer") == "live"
    html = "<html><body><h1>Software Engineer</h1></body></html>"
    assert listing_state(200, html, "https://www.workatastartup.com/jobs/75959") == "live"


def test_blocked_page_is_unknown():
    html = "<html><title>Just a moment...</title>Cloudflare cf-browser-verification</html>"
    assert assess_page(200, html) == "unknown"
