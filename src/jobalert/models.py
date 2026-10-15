from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    id: str
    title: str
    url: str
    location: str = ""
    team: str = ""
    posted_at: str | None = None
    site_name: str = ""


class ConfigError(Exception):
    """The config file or mail settings cannot be used."""


class FetchError(Exception):
    """A careers page could not be read."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
