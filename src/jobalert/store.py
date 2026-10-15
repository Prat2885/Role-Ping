import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobalert.models import Job


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """Remember which openings have been seen, seeded, or emailed."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                site_name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                team TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                posted_at TEXT,
                alert_status TEXT NOT NULL CHECK (
                    alert_status IN ('seeded', 'pending', 'sent')
                ),
                first_seen_at TEXT NOT NULL,
                PRIMARY KEY (site_name, job_id)
            );

            CREATE TABLE IF NOT EXISTS sites (
                site_name TEXT PRIMARY KEY,
                initialized INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT
            );
            """
        )
        self._conn.commit()

    def is_initialized(self, site_name: str) -> bool:
        row = self._conn.execute(
            "SELECT initialized FROM sites WHERE site_name = ?",
            (site_name,),
        ).fetchone()
        return bool(row and row["initialized"])

    def mark_initialized(self, site_name: str) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO sites (site_name, initialized, last_checked_at)
            VALUES (?, 1, ?)
            ON CONFLICT(site_name) DO UPDATE SET
                initialized = 1,
                last_checked_at = excluded.last_checked_at
            """,
            (site_name, now),
        )
        self._conn.commit()

    def touch(self, site_name: str) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO sites (site_name, initialized, last_checked_at)
            VALUES (?, 0, ?)
            ON CONFLICT(site_name) DO UPDATE SET last_checked_at = excluded.last_checked_at
            """,
            (site_name, now),
        )
        self._conn.commit()

    def has(self, site_name: str, job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jobs WHERE site_name = ? AND job_id = ?",
            (site_name, job_id),
        ).fetchone()
        return row is not None

    def insert(self, job: Job, status: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO jobs (
                site_name, job_id, title, location, team, url, posted_at,
                alert_status, first_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.site_name,
                job.id,
                job.title,
                job.location,
                job.team,
                job.url,
                job.posted_at,
                status,
                _utc_now(),
            ),
        )
        self._conn.commit()

    def list_pending(self) -> list[Job]:
        rows = self._conn.execute(
            """
            SELECT site_name, job_id, title, location, team, url, posted_at
            FROM jobs
            WHERE alert_status = 'pending'
            ORDER BY site_name, title
            """
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def mark_sent(self, keys: list[tuple[str, str]]) -> None:
        self._conn.executemany(
            """
            UPDATE jobs
            SET alert_status = 'sent'
            WHERE site_name = ? AND job_id = ? AND alert_status = 'pending'
            """,
            keys,
        )
        self._conn.commit()


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["job_id"],
        title=row["title"],
        url=row["url"],
        location=row["location"],
        team=row["team"],
        posted_at=row["posted_at"],
        site_name=row["site_name"],
    )
