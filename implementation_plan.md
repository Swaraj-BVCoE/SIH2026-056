# AirFare Scraper — Implementation Plan
### MoSPI Problem Statement #26056 · Real-time Airfare Price Index for India

A scalable, automated web-scraping pipeline that collects public airfare price data from major Indian airlines and OTAs, normalizes it, stores it in a time-series database, and exposes it for downstream CPI-index computation.

---

## User Review Required

> [!IMPORTANT]
> This plan covers **Phase 1 only — the Scraper Engine**. Dashboards, CPI index computation, and reporting layers are out of scope for now.

> [!WARNING]
> All target websites (IndiGo, Air India, MakeMyTrip, etc.) explicitly prohibit automated scraping in their ToS. Since this is a **government statistical research project (MoSPI)**, it falls under a defensible "public interest / statistical research" use case. Please confirm with your legal/compliance team before deploying at scale. The scraper will **never bypass login walls, CAPTCHAs, or access personal user data** — only public price listings.

> [!CAUTION]
> Residential proxy infrastructure is needed for reliable data collection. You'll need a proxy provider account (Bright Data, Oxylabs, or similar). Budget for ~50–100 GB/month of proxy traffic. Alternatively, for a demo/prototype, we can use free rotating proxies with lower reliability.

---

## Open Questions

1. **Proxy Budget** — Do you have access to a residential proxy service, or should the MVP use free/no-proxy mode (will get blocked more often but works for prototyping)?
2. **Target Routes Basket** — Should we start with the standard MoSPI city-pair basket (DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-DEL, etc.) or a custom set?
3. **Database** — Should we use a local **SQLite** (zero-setup for prototype) or **PostgreSQL + TimescaleDB** (production-grade)? Or both?
4. **Scheduling Frequency** — Daily scrapes, or higher-frequency (e.g. every 6 hours)?
5. **Target Sources Priority** — Should we scrape **both airlines (IndiGo, Air India, Akasa, SpiceJet) AND OTAs (MakeMyTrip, Cleartrip, Ixigo)**, or focus on one group first?

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCRAPER ENGINE                           │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Scheduler│───▶│  Task Queue  │───▶│  Scraper Workers     │  │
│  │(APScheduler│  │  (in-memory/ │    │  ┌────────────────┐  │  │
│  │ / Cron)  │    │   Redis)     │    │  │ Playwright +   │  │  │
│  └──────────┘    └──────────────┘    │  │ Stealth Layer  │  │  │
│                                      │  └───────┬────────┘  │  │
│                                      │          │            │  │
│                                      │  ┌───────▼────────┐  │  │
│                                      │  │ Proxy Rotator  │  │  │
│                                      │  └───────┬────────┘  │  │
│                                      └──────────┼───────────┘  │
│                                                 │              │
│  ┌──────────────────────────────────────────────▼───────────┐  │
│  │                    Data Pipeline                          │  │
│  │  Raw JSON/HTML ──▶ Parser ──▶ Normalizer ──▶ Validator   │  │
│  └──────────────────────────────────────────┬───────────────┘  │
│                                             │                  │
│  ┌──────────────────────────────────────────▼───────────────┐  │
│  │                  Storage Layer                            │  │
│  │    SQLite (dev) / PostgreSQL + TimescaleDB (prod)         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes

### Component 1 — Project Scaffold & Configuration

#### [NEW] `pyproject.toml` / `requirements.txt`
Core dependencies:
- `playwright` + `playwright-stealth` — browser automation with anti-detection
- `httpx` + `curl_cffi` — for intercepting hidden JSON APIs (faster than browser for some sites)
- `beautifulsoup4` + `lxml` — HTML parsing fallback
- `pydantic` — data validation & schema enforcement
- `SQLAlchemy` + `alembic` — ORM and migrations
- `APScheduler` — cron-style job scheduling
- `python-dotenv` — config/secrets management
- `loguru` — structured logging
- `tenacity` — retry logic with exponential backoff
- `rich` — beautiful CLI output

#### [NEW] `config/settings.py`
- Route basket (city pairs), date windows (D+1 to D+60 lookahead), scrape frequency, proxy settings, DB URL

#### [NEW] `.env.example`
- `DATABASE_URL`, `PROXY_URL`, `PROXY_USERNAME`, `PROXY_PASSWORD`, `LOG_LEVEL`

#### [NEW] `config/routes.py`
- MoSPI city-pair basket: `DEL-BOM`, `DEL-BLR`, `BOM-BLR`, `DEL-CCU`, `BLR-DEL`, `CCU-BOM`, `DEL-HYD`, `BOM-HYD`, `BLR-CCU`, `DEL-MAA`

---

### Component 2 — Database Layer

#### [NEW] `db/models.py`
```python
class FlightPrice(Base):
    id: int (PK)
    scraped_at: datetime       # When collected
    travel_date: date          # Flight date
    origin: str                # IATA (e.g. DEL)
    destination: str           # IATA (e.g. BOM)
    airline: str               # IndiGo, Air India, ...
    flight_number: str
    departure_time: time
    arrival_time: time
    duration_minutes: int
    stops: int                 # 0 = nonstop
    fare_class: str            # Economy, Business
    base_fare: float
    taxes_fees: float
    total_fare: float
    currency: str              # INR
    source_portal: str         # "indigo_direct" / "makemytrip" / ...
    advance_days: int          # scraped_at → travel_date gap
    raw_json: JSON             # raw payload for reprocessing
```

#### [NEW] `db/database.py`
- SQLAlchemy engine + session factory, init_db(), get_db()

#### [NEW] `alembic/` (migrations folder)

---

### Component 3 — Core Scraper Infrastructure

#### [NEW] `scraper/browser.py`
- Playwright browser pool manager
- `playwright-stealth` integration (patch `navigator.webdriver`, WebGL, Canvas, User-Agent, etc.)
- Human-like delays (randomized 1.5–4s between actions)
- Headless mode configurable via env
- Context-level proxy injection

#### [NEW] `scraper/proxy.py`
- Rotating proxy pool manager
- Round-robin / random selection
- Health-check & blacklist failed proxies
- Fallback to direct connection in dev mode

#### [NEW] `scraper/base_scraper.py`
- Abstract `BaseScraper` class
- Methods: `search_flights(origin, dest, date)` → `List[FlightPrice]`
- Built-in retry with exponential backoff (tenacity)
- Error classification: network, blocked (429/403), parse error, rate-limit
- XHR/Fetch request interception hook (`page.on("response", ...)`)

---

### Component 4 — Airline Direct Scrapers

#### [NEW] `scraper/airlines/indigo.py`
- Strategy: **Intercept XHR API** — IndiGo's site makes background JSON API calls to fetch pricing; we intercept these via Playwright's `route()` or `on("response")` listener instead of parsing HTML.
- URL pattern: `goindigo.in` search endpoint
- Parser: extract fare segments, taxes, availability

#### [NEW] `scraper/airlines/air_india.py`
- Strategy: XHR interception + HTML fallback
- Handles Air India Express as well

#### [NEW] `scraper/airlines/akasa.py`
- Strategy: XHR interception (Akasa uses a REST API internally)

#### [NEW] `scraper/airlines/spicejet.py`
- Strategy: XHR interception / HTML parsing hybrid

---

### Component 5 — OTA Scrapers

#### [NEW] `scraper/otas/makemytrip.py`
- Strategy: Playwright stealth + XHR API interception
- MMT exposes a JSON API (`api.mmt.com`) that powers its frontend — intercept this
- Handle dynamic React rendering

#### [NEW] `scraper/otas/cleartrip.py`
- Strategy: XHR interception (Cleartrip uses a GraphQL-like API)

#### [NEW] `scraper/otas/ixigo.py`
- Strategy: HTML parsing + XHR interception hybrid

#### [NEW] `scraper/otas/easemytrip.py`
- Strategy: Playwright + HTML parsing

---

### Component 6 — Data Pipeline

#### [NEW] `pipeline/normalizer.py`
- Normalize airline names (e.g. "6E" → "IndiGo", "AI" → "Air India")
- IATA code validation
- Duration standardization (HH:MM → minutes)
- Outlier detection (flag fares outside ±3σ from 7-day mean)
- Deduplication (same flight, same search = keep cheapest)

#### [NEW] `pipeline/validator.py`
- Pydantic schema validation before DB write
- Required fields enforcement
- Fare sanity checks (base_fare > 0, total_fare >= base_fare)

#### [NEW] `pipeline/storage.py`
- Batch upsert to DB
- Duplicate detection by `(travel_date, flight_number, scraped_at_day, source_portal)`

---

### Component 7 — Scheduler & Orchestrator

#### [NEW] `orchestrator/scheduler.py`
- APScheduler-based job runner
- Job: `scrape_all_routes()` — fans out all city-pairs × lookahead dates × sources
- Configurable cron: default `0 6,12,18 * * *` (3×/day)
- Retry failed jobs up to 3 times before marking as `FAILED`

#### [NEW] `orchestrator/job_runner.py`
- Concurrent execution with `asyncio.gather()` + concurrency limits (semaphore)
- Progress tracking, ETA estimation

---

### Component 8 — CLI & Reporting

#### [NEW] `main.py`
- CLI entry point using `argparse`:
  - `python main.py scrape --route DEL-BOM --date 2026-09-15`
  - `python main.py scrape --all` (full basket)
  - `python main.py schedule` (start daemon)
  - `python main.py report --date 2026-09-01` (print summary table)

#### [NEW] `reports/summary.py`
- Print daily avg, min, max fare per route in a rich table
- Export to CSV/JSON

---

### Component 9 — Logging & Monitoring

#### [NEW] `logs/` (auto-created)
#### [NEW] `scraper/logger.py`
- Loguru-based structured logging
- Separate log files: `scrape.log`, `errors.log`, `db.log`
- Rotation: 10 MB, 7-day retention

---

## File & Folder Structure

```
AirFareScapper/
├── config/
│   ├── settings.py          # All config constants
│   └── routes.py            # City-pair basket
├── db/
│   ├── models.py            # SQLAlchemy ORM models
│   ├── database.py          # Engine + session
│   └── migrations/          # Alembic migrations
├── scraper/
│   ├── base_scraper.py      # Abstract base class
│   ├── browser.py           # Playwright pool + stealth
│   ├── proxy.py             # Proxy rotation
│   ├── airlines/
│   │   ├── indigo.py
│   │   ├── air_india.py
│   │   ├── akasa.py
│   │   └── spicejet.py
│   └── otas/
│       ├── makemytrip.py
│       ├── cleartrip.py
│       ├── ixigo.py
│       └── easemytrip.py
├── pipeline/
│   ├── normalizer.py
│   ├── validator.py
│   └── storage.py
├── orchestrator/
│   ├── scheduler.py
│   └── job_runner.py
├── reports/
│   └── summary.py
├── logs/                    # Auto-created
├── data/                    # SQLite DB (dev)
├── tests/
│   ├── test_parsers.py
│   ├── test_normalizer.py
│   └── test_db.py
├── .env.example
├── requirements.txt
├── README.md
└── main.py
```

---

## Scraping Strategy Summary

| Source | Method | Anti-Bot Risk |
|---|---|---|
| IndiGo | XHR API Interception | Medium |
| Air India | XHR + HTML fallback | Medium |
| Akasa Air | XHR API Interception | Low–Medium |
| SpiceJet | XHR + HTML hybrid | Medium |
| MakeMyTrip | XHR API Interception | High |
| Cleartrip | XHR/GraphQL Interception | High |
| Ixigo | HTML + XHR hybrid | Medium |
| EaseMyTrip | Playwright + HTML | Medium |

**Primary evasion strategy**: Intercept background JSON API calls (XHR/Fetch) that the React/Angular frontends make — these are far more stable than HTML parsing and less likely to trigger bot detection because we're not simulating complex UI interactions.

---

## Verification Plan

### Automated Tests
```bash
pytest tests/ -v
```
- `test_parsers.py` — Unit test each scraper's parser with saved HTML/JSON fixtures
- `test_normalizer.py` — Test data normalization rules
- `test_db.py` — Test DB write/read round-trips

### Manual Verification
1. Run `python main.py scrape --route DEL-BOM --date <next_week>` and verify DB rows
2. Run `python main.py report --date <today>` and check the summary table
3. Check `logs/scrape.log` for successful scrape confirmation
4. Verify scraped fares match what you see manually on the airline/OTA website (spot-check)

---

## Build Phases (Recommended Order)

| Phase | Deliverable | Est. Effort |
|---|---|---|
| **Phase 1a** | Scaffold + DB + Config | ~1 hr |
| **Phase 1b** | Browser infra + base scraper | ~2 hr |
| **Phase 1c** | IndiGo + Air India scrapers | ~3 hr |
| **Phase 1d** | MakeMyTrip + Cleartrip scrapers | ~4 hr |
| **Phase 1e** | Pipeline (normalize/validate/store) | ~2 hr |
| **Phase 1f** | Scheduler + CLI + Reports | ~2 hr |
| **Phase 1g** | Tests + README | ~1 hr |
