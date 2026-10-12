# LC Dallas Troopers

A Streamlit app for LC Troopers (T20, team 4043) and LC Dallas Troopers (T40, team 3885).

## Open in VS Code and run on your Mac

1. In VS Code, choose **File → Open Folder** and open this `dallas-troopers` folder.
2. Open **Terminal → New Terminal** and run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed in the terminal (normally http://localhost:8501). Keep the terminal running. Press Control+C to stop. Later, double-click `Start Troopers.command` to run with the installed environment.

Players do not need accounts or passwords: choose T20 or T40, enter a name, and save Available, Maybe, or Unavailable for a game or umpiring duty. Entering the same name updates its response. Names are matched without case or extra spaces. Use distinct names if two players share a name. This intentionally uses a trust-based team workflow: anyone with access can submit or change a response under a name.

## Features

- Separate T20 and T40 schedules, match selection, availability and results.
- Upcoming and historical games, ground, start time and CricClubs scorecard links.
- Name-only availability, optional team-visible notes and response counts.
- Umpiring duties with captain-entered player assignments and duty availability.
- Result totals and match scores, with separate official batting, bowling and fielding links.
- Captain tools: edit fixtures, cancel/postpone, record results, assign umpires, preview imports and export CSV.
- Transactional shared storage: local SQLite by default; PostgreSQL via DATABASE_URL for hosting.

## Data included and freshness

`fixtures.csv` contains a real browser-verified snapshot captured October 11, 2026:

- T20: 4 upcoming games, 3 upcoming umpiring duties and 3 results.
- T40: 2 upcoming games, 2 upcoming umpiring duties and 12 results (2 wins, 8 losses, 2 abandoned).

It includes the upcoming umpiring schedule, not the historical umpiring archive. Source team labels are retained. Player-level batting/bowling/fielding tables open on CricClubs; the app itself shows game scores and result totals.

The source pages were accessible in a browser but returned HTTP 403 to direct requests. **This is a saved snapshot, not a live feed.** The app never treats a blocked request as an empty schedule. The captain can attempt a direct fetch, import a browser-saved HTML schedule, import the app's CSV format, or edit a fixture manually. Review changes against CricClubs before saving. No CAPTCHA bypass is implemented.

Sources:
- https://cricclubs.com/NTCA/teamSchedule.do?teamId=4043&clubId=343
- https://cricclubs.com/NTCA/teamUmpiringSchedule.do?teamId=4043&clubId=343
- https://cricclubs.com/NTCA/teamResults.do?teamId=4043&clubId=343
- https://cricclubs.com/NTCA/teamSchedule.do?teamId=3885&clubId=343
- https://cricclubs.com/NTCA/teamUmpiringSchedule.do?teamId=3885&clubId=343
- https://cricclubs.com/NTCA/teamResults.do?teamId=3885&clubId=343

## Captain setup

Run `python setup_captain.py` in the activated environment and enter a password with at least 12 characters. It writes a local, git-ignored `.streamlit/secrets.toml`. Alternatively copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and set `ADMIN_PASSWORD` there. Restart the app, open **Captain**, and enter that password. Players can use availability before this setup.

## Sharing a public team link

The local URL is only on your Mac. The app has not been deployed publicly.

For Streamlit Community Cloud:

1. Create a GitHub repository and upload this project (exclude `.venv`, `data`, and `.streamlit/secrets.toml`).
2. Provision a PostgreSQL database with a provider you choose. Obtain its connection URL; use TLS.
3. In Streamlit Community Cloud, create an app from that repository with entrypoint `app.py`.
4. In its secrets settings, set:

```toml
ADMIN_PASSWORD = "your-long-captain-password"
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DB?sslmode=require"
```

5. Deploy, open the resulting HTTPS link, submit one test reply and verify it from another browser before sharing it with the team.

Do not rely on the default SQLite file on Community Cloud: local files there are not guaranteed to persist. The PostgreSQL adapter is included but has not been integration-tested against your hosting provider. Local replies do not automatically migrate to a new database. Export fixtures and availability before moving hosts; arrange a database migration if preserving those replies is necessary.

If using a persistent server instead, mount durable storage for `data/troopers.db` and run one application instance. Do not expose this development server directly as your production site.

Official references: [Streamlit data storage](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data), [deployment secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

## Imports

Download the CSV template from **Captain → Import / refresh CricClubs**. Required columns are `id`, `starts`, `home`, `away`. `starts` uses Dallas local time: `2026-10-17T13:00`. Optional columns: `venue`, `competition`, `status`, `result`, `score`, `url`, `assignees`.

- Status: Scheduled, Completed, Cancelled or Postponed.
- Result: empty, Won, Lost, Tied or No result (completed games only).
- Use stable CricClubs **fixture IDs**, not match IDs. IDs are scoped by format and Game/Umpiring.
- Import one format and fixture type at a time. Exported CSVs with both kinds must be split first.
- Matching IDs update fixtures without removing replies. Imports do not delete absent fixtures.
- Schedule refresh preserves recorded results and captain assignments. Explicitly edit status when rescheduling a postponed fixture.
- Native CricClubs CSV columns differ: map them to the provided app template, or import a saved schedule HTML page.

## Backend sync and GitHub deploy

Use the repo-backed sync script to pull the latest CricClubs schedule, update the tracked CSV, and push the new snapshot to GitHub when you want a fresh deployment.

```bash
python3 sync_schedule.py
```

The script refreshes both T20 and T40 Game and Umpiring fixtures, writes the latest data into `fixtures.csv`, and then runs `git add`, `git commit`, and `git push` if the schedule changed. Set `AUTO_SCHEDULE_REFRESH=false` in the app environment to keep the streamlit app from attempting its own live refresh while the backend handles sync.

## Tests

```sh
python -m unittest -v test_app.py
```

Tests cover duplicate reply updates, concurrent player writes, format/type separation, invalid imports, blocked HTML, parsing, and Streamlit navigation and submission. Test data uses temporary databases, not real team replies.
