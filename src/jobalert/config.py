from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from jobalert.models import ConfigError


class EmailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    subject_prefix: str = "[Jobs]"

    @field_validator("to")
    @classmethod
    def recipient_address(cls, value: str) -> str:
        address = value.strip()
        if "@" not in address or " " in address or address.startswith("@"):
            raise ValueError("to must be an email address")
        return address

    @field_validator("subject_prefix")
    @classmethod
    def prefix_text(cls, value: str) -> str:
        text = value.strip()
        return text or "[Jobs]"


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    keywords: list[str] | None = None
    locations: list[str] | None = None

    @field_validator("name")
    @classmethod
    def site_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name cannot be empty")
        return name

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        url = value.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an http or https address")
        return url


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_minutes: int = Field(default=30, ge=1)
    database: str = "data/jobs.sqlite"
    email: EmailConfig
    filters: Filters = Field(default_factory=Filters)
    sites: list[SiteConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_site_names(self) -> "AppConfig":
        names = [site.name for site in self.sites]
        if len(names) != len(set(names)):
            raise ValueError("site names must be unique")
        return self


class LoadedConfig:
    def __init__(self, path: Path, app: AppConfig) -> None:
        self.path = path
        self.app = app

    @property
    def directory(self) -> Path:
        return self.path.parent

    def database_path(self) -> Path:
        path = Path(self.app.database)
        if not path.is_absolute():
            path = self.directory / path
        return path


class SmtpSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    @property
    def sender(self) -> str:
        return self.smtp_from.strip() or self.smtp_username.strip()


def load_config(path: Path) -> LoadedConfig:
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.yaml to config.yaml and edit it."
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a YAML mapping.")
    try:
        app = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config in {config_path}:\n{exc}") from exc
    return LoadedConfig(config_path, app)


def load_smtp(config_dir: Path) -> SmtpSettings:
    env_file = config_dir / ".env"
    if not env_file.is_file():
        env_file = Path.cwd() / ".env"
    settings = SmtpSettings(
        _env_file=str(env_file.resolve()) if env_file.is_file() else None,
        _env_file_encoding="utf-8",
    )
    problems: list[str] = []
    if not settings.smtp_host.strip():
        problems.append("SMTP_HOST")
    if not 1 <= settings.smtp_port <= 65535:
        problems.append("SMTP_PORT (use a port from 1 to 65535)")
    if settings.smtp_use_ssl and settings.smtp_use_tls:
        problems.append("choose SMTP_USE_SSL or SMTP_USE_TLS, not both")
    if settings.smtp_username.strip() and not settings.smtp_password:
        problems.append("SMTP_PASSWORD")
    if not settings.sender:
        problems.append("SMTP_FROM or SMTP_USERNAME")
    if problems:
        raise ConfigError(
            "Mail is not configured (" + ", ".join(problems) + "). "
            "Copy .env.example to .env and set the SMTP values."
        )
    return settings
