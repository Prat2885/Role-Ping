from pathlib import Path

import pytest
from typer.testing import CliRunner

from jobalert.cli import app
from jobalert.config import load_config, load_smtp
from jobalert.models import ConfigError

runner = CliRunner()


def _write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_database_path_follows_the_config_file(tmp_path):
    path = tmp_path / "config.yaml"
    _write_config(
        path,
        """
email:
  to: you@example.com
sites:
  - name: Example
    url: https://example.com/careers
""",
    )
    loaded = load_config(path)
    assert loaded.database_path() == (tmp_path / "data" / "jobs.sqlite").resolve()


def test_invalid_site_url_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    _write_config(
        path,
        """
email:
  to: you@example.com
sites:
  - name: Example
    url: not-a-url
""",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_smtp_reads_dotenv(tmp_path, monkeypatch):
    for key in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_USE_TLS",
        "SMTP_USE_SSL",
    ):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "SMTP_HOST=smtp.example.com",
                "SMTP_PORT=2525",
                "SMTP_USERNAME=a@b.c",
                "SMTP_PASSWORD=secret",
                "SMTP_FROM=a@b.c",
                "SMTP_USE_TLS=true",
                "SMTP_USE_SSL=false",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_smtp(tmp_path)
    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 2525
    assert settings.sender == "a@b.c"


def test_check_reports_a_missing_config(tmp_path, caplog):
    result = runner.invoke(app, ["check", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1
    assert "Config file not found" in caplog.text
