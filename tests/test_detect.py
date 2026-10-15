from jobalert.adapters.detect import BoardKind, detect_board


def test_greenhouse_board_and_job_urls():
    board = detect_board("https://boards.greenhouse.io/airbnb")
    job = detect_board("https://job-boards.greenhouse.io/airbnb/jobs/123")
    embed = detect_board("https://boards.greenhouse.io/embed/job_board?for=airbnb")
    api = detect_board("https://boards-api.greenhouse.io/v1/boards/airbnb/jobs")
    europe = detect_board("https://boards.eu.greenhouse.io/airbnb")

    for target in (board, job, embed, api, europe):
        assert target.kind is BoardKind.GREENHOUSE
        assert target.token == "airbnb"
    assert europe.europe is True
    assert board.europe is False


def test_lever_and_ashby_urls():
    lever = detect_board("https://jobs.lever.co/spotify/6f3c")
    lever_api = detect_board("https://api.eu.lever.co/v0/postings/spotify?mode=json")
    ashby = detect_board("https://jobs.ashbyhq.com/openai/some-job")

    assert lever.kind is BoardKind.LEVER
    assert lever.token == "spotify"
    assert lever_api.kind is BoardKind.LEVER
    assert lever_api.europe is True
    assert ashby.kind is BoardKind.ASHBY
    assert ashby.token == "openai"


def test_other_pages_use_html():
    target = detect_board("https://example.com/careers")
    assert target.kind is BoardKind.HTML
    assert target.token == ""
