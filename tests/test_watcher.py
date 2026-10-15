from jobalert.config import AppConfig
from jobalert.models import FetchError, Job
from jobalert.store import Store
from jobalert.watcher import run_check


def _config(**extra) -> AppConfig:
    data = {
        "email": {"to": "you@example.com"},
        "sites": [{"name": "Example", "url": "https://example.com/careers"}],
    }
    data.update(extra)
    return AppConfig.model_validate(data)


def _job(job_id: str, title: str = "Engineer", location: str = "Remote") -> Job:
    return Job(
        id=job_id,
        title=title,
        url=f"https://example.com/jobs/{job_id}",
        location=location,
        team="Product",
    )


def test_first_check_records_jobs_without_email(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    sent: list[Job] = []
    report = run_check(
        _config(),
        store,
        lambda site: [_job("1"), _job("2", "Designer")],
        sent.extend,
    )
    assert report.ok
    assert sent == []
    assert report.sites[0].seeded == 2
    assert store.list_pending() == []
    store.close()


def test_later_check_emails_only_new_jobs(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    listings = [_job("1")]

    def fetch(site):
        return list(listings)

    run_check(_config(), store, fetch, lambda jobs: None)
    listings.append(_job("2", "Designer"))
    sent: list[Job] = []
    report = run_check(_config(), store, fetch, sent.extend)
    assert [job.id for job in report.emailed] == ["2"]
    assert sent[0].id == "2"
    assert store.list_pending() == []
    store.close()


def test_failed_email_is_retried(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    run_check(_config(), store, lambda site: [], lambda jobs: None)
    listings = [_job("9", "Analyst")]

    def fail(jobs):
        raise RuntimeError("smtp down")

    failed = run_check(_config(), store, lambda site: listings, fail)
    assert "smtp down" in (failed.email_error or "")
    assert [job.id for job in store.list_pending()] == ["9"]

    sent: list[Job] = []
    retried = run_check(_config(), store, lambda site: listings, sent.extend)
    assert retried.ok
    assert [job.id for job in sent] == ["9"]
    assert store.list_pending() == []
    store.close()


def test_include_existing_emails_the_first_snapshot(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    sent: list[Job] = []
    report = run_check(
        _config(),
        store,
        lambda site: [_job("1")],
        sent.extend,
        include_existing=True,
    )
    assert [job.id for job in report.emailed] == ["1"]
    assert sent[0].site_name == "Example"
    store.close()


def test_one_site_failing_does_not_seed_it(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    app = _config(
        sites=[
            {"name": "Broken", "url": "https://example.com/a"},
            {"name": "Healthy", "url": "https://example.com/b"},
        ]
    )

    def fetch(site):
        if site.name == "Broken":
            raise FetchError("board was not found")
        return [_job("1")]

    report = run_check(app, store, fetch, lambda jobs: None)
    assert report.ok is False
    assert report.sites[0].error == "board was not found"
    assert store.is_initialized("Broken") is False
    assert store.is_initialized("Healthy") is True
    assert report.emailed == []
    store.close()


def test_site_filters_override_global_filters(tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    app = _config(
        filters={"keywords": ["engineer"]},
        sites=[
            {
                "name": "Example",
                "url": "https://example.com/careers",
                "keywords": ["designer"],
            }
        ],
    )
    run_check(
        app,
        store,
        lambda site: [_job("1", "Engineer"), _job("2", "Designer")],
        lambda jobs: None,
    )
    assert store.has("Example", "2")
    assert store.has("Example", "1") is False
    store.close()
