# AirFare Index India

Real-Time Domestic Airfare Price Monitoring — CPI Augmentation Analytics Prototype.

AirFare Index India is a local, open-source system for compliant collection, validation and economic analysis of Indian domestic airfare observations. It is designed to show how high-frequency web observations could augment CPI research by NSO/MoSPI and RBI. It is **not** an officially published MoSPI index.

## What the platform provides

- Configurable weighted Airfare Price Index (APIx), daily/weekly/monthly trends and period changes
- Route contribution, sector heatmap and route-level fare analytics
- T+1, T+7, T+15, T+30 and T+45 advance-purchase analysis
- Airline metrics separated from collection-source health
- Collection audit monitor with 45-second polling
- Data-quality pipeline, missing breakdowns, outliers and coverage reporting
- Paginated/filterable data explorer with backend CSV and JSON exports
- Route/source coverage matrix and freshness classification
- Reference CSV import with MAE, MAPE and coverage backtesting
- Swagger (`/docs`) and ReDoc (`/redoc`) analytics documentation
- Explicit loading, empty, partial-data and API-error states

No paid API, database, chart library, map, proxy, analytics SaaS or cloud service is required.

## Architecture

```text
Airline / OTA adapters
        ↓
conservative collection + scrape run audit
        ↓
normalization → validation → deduplication → outlier flagging
        ↓
SQLite flight_prices + scrape_runs
        ↓
FastAPI aggregation + configurable APIx calculator
        ↓
React / Tailwind / Recharts analytical dashboard + JSON/CSV API
```

Key folders:

```text
api/                 single FastAPI app, analytics queries, schemas and endpoints
config/              route basket, settings and configurable demo index weights
db/                  SQLAlchemy models and database/session lifecycle
index/               index calculator, weight loading and methodology disclosure
orchestrator/        APScheduler and collection job execution
pipeline/            normalization, validation and storage
scraper/             airline and OTA adapters
tests/               parser, pipeline, database, index and API tests
web/src/components/  reusable dashboard components
web/src/pages/       economic-monitoring analytical pages
```

## Technology

- React 19, Vite 8, Tailwind CSS 4, Recharts, Lucide React
- FastAPI, Pydantic, SQLAlchemy, SQLite, APScheduler
- Playwright-based source adapters
- pytest

## Setup on Windows

Python 3.11 is recommended because the repository's pinned Playwright 1.47 dependency targets its matching `greenlet` build. The analytics API and tests also run on the repaired local Python 3.13 environment, but a fresh 3.11 environment is the safest choice for live browser collection.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd web
npm install
```

Install Playwright browsers only when running live permitted scraper adapters:

```powershell
.\venv\Scripts\playwright.exe install chromium
```

## Run the application

Terminal 1, from the repository root:

```powershell
.\venv\Scripts\python.exe -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd web
npm run dev
```

If this Windows installation has a broken global npm shim, run the already-installed Vite entry point directly:

```powershell
node .\node_modules\vite\bin\vite.js
```

Open the Vite URL (normally `http://localhost:5173`). The development proxy forwards `/api` to FastAPI. For a separate API host, create `web/.env.local`:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Production frontend build:

```powershell
cd web
npm run build
```

Equivalent direct command: `node .\node_modules\vite\bin\vite.js build`.

FastAPI serves `web/dist` when that build exists.

## Scraper commands

See CLI help before starting collection:

```powershell
.\venv\Scripts\python.exe main.py --help
```

The default collection dates are the CPI-relevant lead-time windows T+1, T+7,
T+15, T+30 and T+45. They replace the previous 60-consecutive-day default,
which produced an impractically large queue.

Start with a bounded multi-route coverage run:

```powershell
.\venv\Scripts\python.exe main.py scrape --route-limit 8 --max-jobs 8 --date 2026-09-15
```

The fair queue rotates sources across routes, so early progress is not confined
to one portal or one sector. For all eight sources across four routes on one
date (32 jobs), use:

```powershell
.\venv\Scripts\python.exe main.py scrape --route-limit 4 --date 2026-09-15
```

For one route across all sources and all five lead-time windows:

```powershell
.\venv\Scripts\python.exe main.py scrape --route DEL-BOM
```

Use `--days N` only when consecutive daily observations from T+1 through T+N
are specifically required. `--max-jobs N` is available as a safety cap.

Collection is intentionally conservative. Keep concurrency low, respect site terms and robots policies, and use only permitted sources. The system does not bypass CAPTCHA or access controls; blocked portals must remain `BLOCKED`/unavailable. Official, licensed or public API feeds can replace adapters without changing downstream analytics.

Scheduled cycles process the six least-recently attempted routes by default,
then rotate to the next batch. Change `SCHEDULED_ROUTES_PER_CYCLE` in `.env`
only after considering expected run duration and source rate limits.

## API endpoints

- `GET /api/overview`
- `GET /api/index/latest`
- `GET /api/index/trend?frequency=daily&days=30`
- `GET /api/index/routes?period=weekly`
- `GET /api/index/contributions?period=weekly`
- `GET /api/routes`
- `GET /api/routes/{origin}/{destination}`
- `GET /api/lead-time`
- `GET /api/sources/status`
- `GET /api/coverage`
- `GET /api/data-quality`
- `GET /api/fares?page=1&page_size=50`
- `GET /api/fares/export?format=csv`
- `GET /api/runs/recent`
- `GET /api/runs/summary`
- `GET /api/methodology`
- `GET /api/backtesting`
- `POST /api/backtesting/import`

Interactive documentation is at `/docs`; ReDoc is at `/redoc`.

## Index methodology

For each valid collection day and route, the backend calculates an average all-inclusive fare. The earliest observed valid daily average for that route is the prototype base fare. A route price relative is:

```text
route relative = current route average / route base average × 100
APIx = Σ(route relative × normalized route weight)
```

When route coverage is partial, weights for observed routes are re-normalized and coverage is shown. Frequency views aggregate daily index observations into weekly or monthly means. Changes are calculated only when a previous comparable observation exists.

Weights live in [`config/index_weights.csv`](config/index_weights.csv). The included equal values are **DEMO / CONFIGURABLE WEIGHTS**, normalized automatically; they are not official MoSPI/PSD weights. Replace this file when an authoritative weight table is supplied.

## Fare breakdown policy

`base_fare`, `taxes_fees` and `total_fare` are preserved when a source provides them reliably. User-development fee, convenience charges and other unavailable components remain `null`. The UI shows “Breakdown unavailable”; it never estimates missing components.

## Reference backtesting

Upload a UTF-8 CSV through Validation & Backtesting:

```csv
date,route,reference_fare
2026-10-01,DEL-BOM,5400
```

The file is validated and saved as `data/reference_fares.csv`. Results compare it with collected average fares for the same travel date and route and report MAE, MAPE and match coverage. No reference dataset is bundled or fabricated.

## Database initialization and migration

SQLite remains the prototype default. Startup calls `Base.metadata.create_all`, which safely creates the additive `index_observations` and `route_index_observations` tables without deleting or rewriting `flight_prices` or `scrape_runs`; therefore no migration command is required for the current prototype.

The ORM now declares `flight_prices.scrape_run_id → scrape_runs.id`. Existing SQLite files keep their current column and are not destructively rebuilt merely to add the physical constraint; newly initialized databases receive the constraint. A future production migration should rebuild that table transactionally after validating orphan IDs.

## Testing

```powershell
.\venv\Scripts\python.exe -m pytest -q
cd web
npm run build
```

Tests use in-memory SQLite and parser fixtures; they do not contact airline websites.

## Screenshots

Add current desktop, tablet and mobile captures here after running the local dashboard. No official Government of India or MoSPI logos are bundled.

## Known limitations

- The repository does not contain authoritative MoSPI PSD route weights or an official index formula.
- Existing stored data may cover only a subset of configured routes, sources and periods; the UI reports this as partial or insufficient data.
- Fare-component availability depends on each permitted source.
- Source blocking and CAPTCHA cannot ethically be bypassed.
- Duplicate-removal counts were not historically persisted, so the quality page labels that metric “Not audited” until collection audit storage is extended.
- Materialized index tables are available for scheduled jobs, while API responses currently calculate from traceable fare observations so new records appear immediately.
#   S I H 2 0 2 6  
 