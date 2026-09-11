# AirFare Index India — Local Setup Guide

This guide is based on the manifests, configuration, source entry points, and documentation currently in this repository. Run commands from the repository root unless a step says otherwise.

## 1. Project Overview

AirFare Index India is a local analytics prototype that collects Indian domestic airfare observations, validates and stores them, calculates an experimental airfare price index, and presents the results through a web dashboard and REST API. It is not an official MoSPI index.

The repository uses:

- Python for the scraper, data pipeline, scheduler, reporting CLI, and backend
- FastAPI and Uvicorn for the HTTP API
- SQLAlchemy with a local SQLite database
- Playwright with Chromium for live airline and OTA collection
- APScheduler for scheduled collection
- Pandas and Pydantic for processing, validation, and configuration
- React 19, Vite 8, Tailwind CSS 4, Recharts, and Lucide React for the dashboard
- pytest for backend tests and Oxlint for frontend linting

No Docker files are present. The supported default setup does not require PostgreSQL, MongoDB, Redis, or another external database/service.

## 2. Prerequisites

Install the following software before setup:

| Software | Version | Why it is needed |
| --- | --- | --- |
| Git | Any current version | Clone the repository and collaborate with the team |
| Python | **3.11 recommended** | Run the backend, scraper, CLI, scheduler, and tests. The repository README recommends 3.11 for compatibility with the pinned Playwright 1.47.0 dependency. No formal Python version constraint file is present. |
| Node.js | **20.19.0 or newer in the 20.x line, or 22.12.0+** | Run Vite 8 and the React dashboard; this engine requirement is recorded in `web/package-lock.json` |
| npm | Included with Node.js | Install the locked frontend dependencies and run frontend scripts |

The SQLite library is used through Python/SQLAlchemy; a separate SQLite server is not required. Chromium is installed through Playwright during the installation steps.

Confirm the tools are available:

```text
git --version
python --version
node --version
npm --version
```

On Windows, use `py -3.11` instead of `python` in the commands below if that is how Python 3.11 is installed.

## 3. Clone the Repository

1. Clone the GitHub repository, replacing the placeholder with its Git URL:

   ```bash
   git clone <repository-url>
   ```

2. Enter the directory created by Git:

   ```bash
   cd <repository-directory>
   ```

   The current Git remote is named `origin`, and the team branch is `main`. The local directory name may differ from the repository name, so use the directory that `git clone` created.

## 4. Project Structure

| Path | Purpose |
| --- | --- |
| `main.py` | Click-based CLI for database setup, scraping, scheduling, reports, exports, status, and dashboard startup |
| `api/` | FastAPI application, REST routes, schemas, and analytics queries |
| `config/` | Pydantic settings, route basket, and index weights |
| `db/` | SQLAlchemy models, engine, sessions, and table initialization |
| `scraper/` | Shared Playwright browser/proxy code plus airline and OTA adapters |
| `orchestrator/` | Collection job runner and APScheduler daemon |
| `pipeline/` | Fare normalization, validation, deduplication, and storage |
| `index/` | Airfare index calculation, weighting, and methodology |
| `reports/` | Terminal summaries and CSV/JSON export helpers |
| `web/` | React/Vite dashboard; reusable UI is in `web/src/components/` and pages are in `web/src/pages/` |
| `tests/` | API, database, index, pipeline, parser, page-health, and orchestrator tests |
| `tools/` | Optional proxy import/fetch utilities |
| `data/` | SQLite data, fare CSVs, and browser session state generated/used by the application |
| `logs/` | Scraper and error logs |

## 5. Installation Steps

### 5.1 Create and activate a Python virtual environment

From the repository root:

**Windows PowerShell**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**macOS/Linux**

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` pins all Python packages, including FastAPI, SQLAlchemy, Playwright 1.47.0, pytest, and the scraper dependencies.

### 5.2 Install the Playwright browser

The live scraper launches Chromium, so install the matching browser binary after the Python packages:

```bash
python -m playwright install chromium
```

This step is not required if a team member will only run the API/dashboard against existing SQLite data, but it is required to run live collection.

### 5.3 Install frontend dependencies

The repository contains `web/package-lock.json`, so use the locked dependency installation:

```bash
cd web
npm ci
cd ..
```

## 6. Environment Variables

### Create the local environment files

The backend reads `<repository-root>/.env` through `config/settings.py`. Create it from the committed template so no credentials from another machine are reused:

**Windows PowerShell**

```powershell
Copy-Item .env.example .env -Force
```

**macOS/Linux**

```bash
cp .env.example .env
```

The default local configuration has no required secret values. All backend settings have code defaults, but using the template makes the active configuration explicit.

The frontend reads `VITE_API_BASE_URL`. For normal Vite development, no frontend file is required: the value remains blank and Vite proxies `/api` to `http://127.0.0.1:8000`. If the API runs elsewhere, create `web/.env.local` from `web/.env.example` and set the full API origin:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Do not append `/api`; frontend requests already include that prefix.

### Backend variables

None of these variables is mandatory for the default local SQLite/direct-connection setup. The values shown are the repository defaults or template values.

| Variable | Default/template value | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/airfare.db` | SQLAlchemy database URL |
| `PROXY_ENABLED` | `false` | Enables the optional proxy pool |
| `PROXY_URL` | blank | Optional single proxy server URL |
| `PROXY_USERNAME` | blank | Optional proxy username |
| `PROXY_PASSWORD` | blank | Optional proxy password |
| `HEADLESS` | `true` | Runs Chromium without a visible window |
| `MAX_CONCURRENT_SCRAPERS` | `1` | Maximum simultaneous browser jobs |
| `REQUEST_DELAY_MIN` | `3.0` | Minimum delay between page actions, in seconds |
| `REQUEST_DELAY_MAX` | `7.0` | Maximum delay between page actions, in seconds |
| `SCRAPE_RETRY_ATTEMPTS` | `2` | Retry count for failed scrape attempts |
| `SCRAPE_RETRY_DELAY` | `30` | Delay between retries, in seconds |
| `SCRAPE_CRON` | `0 6,12,18 * * *` | Scheduler cron expression, evaluated in `Asia/Kolkata` |
| `LOOKAHEAD_DAYS_MIN` | `1` | Earliest allowed travel lead time |
| `LOOKAHEAD_DAYS_MAX` | `60` | Latest allowed travel lead time |
| `ADVANCE_PURCHASE_WINDOWS` | `1,7,15,30,45` | Default lead-time days collected when no date range is supplied |
| `SCHEDULED_ROUTES_PER_CYCLE` | `6` | Number of routes selected for each scheduled cycle |
| `STALE_RUN_HOURS` | `6` | Age at which unfinished collection runs are treated as stale |
| `FRESHNESS_FRESH_HOURS` | `6` | Threshold for fresh dashboard data |
| `FRESHNESS_DELAYED_HOURS` | `24` | Threshold for delayed dashboard data |
| `INDEX_BASE_PERIOD` | `earliest-observed-period` | Index base-period selection |
| `INDEX_WEIGHTS_FILE` | `config/index_weights.csv` | Index weight CSV path |
| `LOG_LEVEL` | `INFO` | Console logging level |
| `LOG_DIR` | `logs` | Log output directory |

If a permitted proxy is needed, use placeholders rather than real values in shared documentation or examples:

```dotenv
PROXY_ENABLED=true
PROXY_URL=http://proxy-host:port
PROXY_USERNAME=your_proxy_username_here
PROXY_PASSWORD=your_proxy_password_here
```

`proxies.txt` is another supported proxy source, with one full proxy URL per line. Treat it as a secret when its URLs contain credentials.

## 7. Database Setup

The default database is SQLite at `data/airfare.db`. It requires no server, database user, or password.

1. Keep `DATABASE_URL=sqlite:///./data/airfare.db` in `.env`.
2. From the repository root, with the virtual environment active, create or verify the tables:

   ```bash
   python main.py db-init
   ```

3. A successful check prints `Database initialized and healthy.`

The FastAPI startup and scraper commands also call the same idempotent table initializer. Although Alembic is listed as a Python dependency, this repository currently contains no Alembic configuration or migration directory, so there is no migration command to run. There is also no seed command. The committed SQLite/CSV files may already contain sample observations for the dashboard.

The `.env.example` mentions PostgreSQL only as a production illustration. The repository does not include the PostgreSQL driver or a PostgreSQL setup/migration path, so SQLite is the documented local configuration.

## 8. How to Run the Project

The two-terminal development setup gives the clearest logs and shutdown behavior.

### Terminal 1 – Backend

Activate the Python virtual environment, remain in the repository root, and run:

```bash
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```
or 

" 
.\venv\Scripts\Activate.ps1
>> python -m uvicorn api.main:app  --host 127.0.0.1 --port 8000
"

The API is available at `http://127.0.0.1:8000/api`, with interactive documentation at `http://127.0.0.1:8000/docs` and ReDoc at `http://127.0.0.1:8000/redoc`.

### Terminal 2 – Frontend

From the repository root:

```bash
cd web
npm run dev
```
or
"
 cd web
>> $env:VITE_API_BASE_URL="http://127.0.0.1:8012"
>> node .\node_modules\vite\bin\vite.js

"

Vite serves the dashboard at `http://localhost:5173` by default and forwards `/api` requests to the backend on port 8000.

### Terminal 3 – Scraper or Scheduler (optional)

Live collection is not a continuously required web process. Run it on demand in a third terminal from the repository root. Inspect the available options first:

```bash
.\venv\Scripts\Activate.ps1
python main.py scrape --help
```

A small, bounded example using one configured route, one source, and tomorrow's travel date is:

```bash
.\venv\Scripts\Activate.ps1
python main.py scrape --route DEL-BOM --portal indigo_direct --days 1
```

This uses the configured lead-time windows unless `--date YYYY-MM-DD` or `--days N` is supplied. Live sources may block automation or return no data; use only permitted sources and respect their terms and access controls.

To keep the configured APScheduler daemon running instead:

```bash
python main.py schedule
```

It uses `SCRAPE_CRON` in the `Asia/Kolkata` timezone and runs until stopped with Ctrl+C.

### Optional one-command dashboard launcher

On Windows, the CLI can start both development processes and open the browser:

```powershell
python main.py dashboard
```

This launcher explicitly invokes `npm.cmd`, so the separate-terminal method above is the portable method for macOS/Linux.

### Optional production-style frontend build

```bash
cd web
npm run build
cd ..
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

When `web/dist` exists, FastAPI mounts the built dashboard at `http://127.0.0.1:8000/`.

## 9. Expected Output

After a successful development startup:

- The backend terminal reports that Uvicorn is running on `http://127.0.0.1:8000` and logs that database tables were created or verified.
- Opening `http://127.0.0.1:8000/docs` displays the AirFare Index India API endpoints.
- The frontend terminal reports Vite's local URL, normally `http://localhost:5173`.
- Opening the Vite URL displays the AirFare Index India analytical dashboard. With the committed/sample database, pages can show index, route, source-health, collection, and data-quality observations; with an empty database, the UI should show its empty-data states rather than fabricated results.
- A scraper run prints a completion summary and writes collection audit/data rows to SQLite when a source returns valid observations. Logs are written under `logs/`.

## 10. Common Errors and Solutions

### `python` is not found or the wrong Python is used

Install Python 3.11 and recreate the environment with that interpreter. On Windows, use `py -3.11 -m venv venv`. Confirm the active interpreter with `python --version`.

### PowerShell refuses to activate the virtual environment

Allow local script execution for the current PowerShell process, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Alternatively, call executables directly, such as `.\venv\Scripts\python.exe main.py db-init`.

### `ModuleNotFoundError` or dependency installation errors

Confirm the virtual environment is active, upgrade pip, and reinstall the pinned requirements:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Python 3.11 is the recommended fallback if the pinned Playwright/`greenlet` packages do not install on a newer Python release.

### Node/Vite reports an unsupported engine

Vite 8 requires Node `^20.19.0` or `>=22.12.0`. Upgrade Node, delete no project files, and rerun `npm ci` inside `web/`.

### Playwright says the Chromium executable is missing

With the Python virtual environment active, run:

```bash
python -m playwright install chromium
```

On Linux, if Playwright reports missing system libraries, install the browser and its OS dependencies with:

```bash
python -m playwright install --with-deps chromium
```

### `.env` is missing or settings appear incorrect

Recreate it from `.env.example`, run commands from the repository root, and restart the backend/scraper because settings are loaded when Python imports `config.settings`.

### SQLite cannot open the database or reports that it is locked

Run from the repository root, confirm that `data/` is writable, and stop other backend/scraper processes using the same database before retrying `python main.py db-init`. SQLite WAL mode permits normal concurrent reads, but stale processes or copied `airfare.db-wal`/`airfare.db-shm` runtime files can still cause problems.

### The frontend loads but API panels fail

Confirm Terminal 1 is running on `127.0.0.1:8000`. In normal development, leave `VITE_API_BASE_URL` blank so Vite uses the configured `/api` proxy. If the backend port changes, set `web/.env.local` to that backend origin and restart Vite.

### Port 8000 or 5173 is already in use

Stop the process using the port, or choose matching alternate settings. For example, run the backend on 8001:

```bash
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8001
```

Then set `VITE_API_BASE_URL=http://127.0.0.1:8001` in `web/.env.local` and restart the frontend. To choose another Vite port, run `npm run dev -- --port 5174` inside `web/`.

### A scraper returns `BLOCKED`, `NO_DATA`, timeouts, or browser errors

First confirm Chromium is installed. Set `HEADLESS=false` temporarily to observe the browser, keep `MAX_CONCURRENT_SCRAPERS=1`, and inspect `logs/scrape.log` and `logs/errors.log`. A portal may legitimately block automation; the project intentionally does not bypass CAPTCHA or access controls. Only configure a proxy when its use is authorized, and never commit its credentials.

### Validate the installation

Run the backend tests from the repository root:

```bash
python -m pytest
```

Run frontend checks from `web/`:

```bash
npm run lint
npm run build
```

## 11. How to Get Latest Changes

Save or commit local work first, switch to `main`, and pull:

```bash
git checkout main
git pull origin main
```

If dependency manifests changed, rerun `python -m pip install -r requirements.txt` from the root and `npm ci` from `web/`.

## 12. Git Workflow for Team Members

Use a short-lived feature branch rather than committing unfinished work directly to `main`:

```bash
git checkout main
git pull origin main
git checkout -b feature/feature-name
```

Make and test the changes, then commit and push the branch:

```bash
git add .
git commit -m "Description of changes"
git push origin feature/feature-name
```

Prefer opening a pull request for review and automated checks. Do not push unfinished changes directly to `main`.

Before `git add .`, always inspect `git status` to ensure local databases, logs, browser sessions, `.env` files, exports, and credentials are not being staged.

## 13. Security Notes

- Never commit `.env`, `web/.env.local`, passwords, API keys, access tokens, proxy credentials, or private configuration.
- Treat `proxies.txt` and `data/browser_state.json`/`data/browser_states/` as sensitive because they can contain proxy credentials, cookies, or browser session data.
- Do not commit generated SQLite runtime files (`*.db`, `*.db-wal`, `*.db-shm`), logs, virtual environments, `web/node_modules/`, or frontend build output unless the team has explicitly decided a sanitized data artifact belongs in version control.
- At the time this guide was written, the repository had **no root `.gitignore`**, and `.env`, `proxies.txt`, browser-state files, logs, and SQLite files were tracked. Maintainers should add appropriate ignore rules, remove these local/runtime files from tracking, and rotate any credential or session value that may ever have been committed. Do not assume a file is safe merely because it is already in Git history.
- Check `git status` and `git diff --cached` before every commit.
- Keep `PROXY_ENABLED=false` unless an approved proxy has been configured, and never paste real credentials into documentation, issues, chat, or pull requests.
