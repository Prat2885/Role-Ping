import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobalert.models import Job


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _should_scan(status: str, checked: str | None, now: datetime) -> bool:
    if not checked:
        return True
    seen = datetime.strptime(checked, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age = now - seen
    if status == "found":
        return True
    if status == "error":
        return age >= timedelta(hours=3)
    if status == "none":
        return age >= timedelta(hours=24)
    return True


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

            CREATE TABLE IF NOT EXISTS closed_jobs (
                site_name TEXT NOT NULL,
                job_id TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                PRIMARY KEY (site_name, job_id)
            );

            CREATE TABLE IF NOT EXISTS company_boards (
                company_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                website TEXT NOT NULL,
                source TEXT NOT NULL,
                board_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '' CHECK (
                    status IN ('', 'found', 'none', 'error')
                ),
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

    def is_closed(self, site_name: str, job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM closed_jobs WHERE site_name = ? AND job_id = ?",
            (site_name, job_id),
        ).fetchone()
        return row is not None

    def mark_closed(self, site_name: str, job_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO closed_jobs (site_name, job_id, closed_at)
            VALUES (?, ?, ?)
            """,
            (site_name, job_id, _utc_now()),
        )
        self._conn.commit()

    def is_known(self, site_name: str, job_id: str) -> bool:
        return self.has(site_name, job_id) or self.is_closed(site_name, job_id)

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

    def upsert_companies(self, companies: list[dict]) -> None:
        self._conn.executemany(
            """
            INSERT INTO company_boards (company_key, name, website, source)
            VALUES (:company_key, :name, :website, :source)
            ON CONFLICT(company_key) DO UPDATE SET
                name = excluded.name,
                website = excluded.website
            """,
            companies,
        )
        self._conn.commit()

    def companies_due(self, limit: int) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT company_key, name, website, board_url, status
            FROM company_boards
            ORDER BY last_checked_at IS NOT NULL, last_checked_at
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def companies_to_scan(self) -> list[dict]:
        """Every company this check should read.

        Unvisited companies are included so one check finishes the directory.
        A found careers page is reread every check. A missing page is left
        alone for a day. A failed read is tried again after three hours.
        """
        rows = self._conn.execute(
            """
            SELECT company_key, name, website, board_url, status, last_checked_at
            FROM company_boards
            """
        ).fetchall()
        now = datetime.now(timezone.utc)
        chosen = [dict(row) for row in rows if _should_scan(row["status"], row["last_checked_at"], now)]
        chosen.sort(key=lambda item: (item["last_checked_at"] is not None, item["last_checked_at"] or ""))
        return chosen

    def company_counts(self) -> tuple[int, int]:
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN last_checked_at IS NULL THEN 1 ELSE 0 END) AS waiting
            FROM company_boards
            """
        ).fetchone()
        return int(row["total"] or 0), int(row["waiting"] or 0)

    def mark_company(self, company_key: str, board_url: str, status: str) -> None:
        self._conn.execute(
            """
            UPDATE company_boards
            SET board_url = ?, status = ?, last_checked_at = ?
            WHERE company_key = ?
            """,
            (board_url, status, _utc_now(), company_key),
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
