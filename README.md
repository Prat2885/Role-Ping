# Job alert agent

A local agent that watches careers pages and emails you when a new opening matches your filters.

Greenhouse, Lever, and Ashby boards are read from their public job feeds. Any other careers URL is read from the page itself. The first successful check for a site records the openings already there and does not email them. Later checks email only new matches. If sending mail fails, those openings stay queued for the next check.

## Setup

From this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
copy config.example.yaml config.yaml
copy .env.example .env
```

Edit `config.yaml` with the careers pages you want, and edit `.env` with your mail server. `config.yaml` and `.env` stay out of git.

Gmail needs an app password, not your normal account password. Use `smtp.gmail.com` and port `587`. Outlook / Microsoft 365 uses `smtp.office365.com` and port `587`.

Send a test message before the first real check:

```powershell
.\.venv\Scripts\jobalert.exe test-email
```

## Config

```yaml
schedule_minutes: 30

email:
  to: you@example.com
  subject_prefix: "[Jobs]"

filters:
  keywords: ["engineer", "python"]
  locations: ["remote", "india"]

sites:
  - name: Example
    url: https://boards.greenhouse.io/example
```

Keywords are matched against the job title and team. Locations are matched against the location text. An empty list matches everything.

A site can set its own `keywords` or `locations`. When it does, those lists replace the global ones for that site. Only matching jobs are remembered, so widening a filter later can email older openings that were skipped before.

Point Greenhouse, Lever, and Ashby entries at the board, for example `https://boards.greenhouse.io/company`. A link to one job on those boards still watches the whole board. For any other site, use the listings page. Pages that only render jobs in the browser, or that block automated reads, are reported as a failed check and are not treated as an empty board.

## Commands

```powershell
.\.venv\Scripts\jobalert.exe profile C:\path\to\cv.pdf
.\.venv\Scripts\jobalert.exe check
.\.venv\Scripts\jobalert.exe check --include-existing
.\.venv\Scripts\jobalert.exe watch
.\.venv\Scripts\jobalert.exe test-email
```

`check` runs once and exits. `watch` repeats on `schedule_minutes` until you press Ctrl+C. `--include-existing` emails the openings already posted on a company board, and it only changes that board's first successful check.

`profile` reads a PDF, DOCX, or TXT CV and saves an experience level plus related job titles to search for. A backend intern is also searched as fullstack engineer, full stack engineer intern, backend engineer, backend developer, and software engineer. Set `LLM_API_KEY` or `OPENAI_API_KEY` in `.env` to have a chat model read the CV instead; without a key, the related-title list above is used. The CV itself is not emailed. After a profile exists, `check` and `watch` search the job boards, the YC directory, public LinkedIn job posts in India and remote posts from companies elsewhere, and company careers pages. Gemini reads the CV, then keeps only the openings that are real single roles for that candidate. A role is kept when it is in India, or when it is remote and not limited to another country. Office jobs outside India are left out. A posting is emailed only when its apply page is still open. Each check reads the boards and every company careers page that is due, then sends every legitimate match in one email. A saved careers page is read again on the next check. The schedule is 120 minutes, so a role that goes live is included in a mail within three hours. `sites` in `config.yaml` can be empty. Add a company there only when you want that one careers page watched as well. LinkedIn does not offer those employee or founder posts to an automated reader, so the check does not use LinkedIn.

Seen jobs are stored in `data/jobs.sqlite` next to the config file. Delete that file if you want a site to be treated as new again. The CV profile is `data/profile.json`.

## Run it on a schedule

After `check` and `test-email` succeed, register a Windows task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1 -EveryMinutes 120
```

The task runs `jobalert check` every 2 hours, including after you sign in again. Remove it later with:

```powershell
Unregister-ScheduledTask -TaskName JobAlertAgent -Confirm:$false
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
