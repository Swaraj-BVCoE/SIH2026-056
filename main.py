"""
main.py
────────
AirFare Scraper — CLI Entry Point

Commands:
  scrape          Run scrapers (single route or full basket)
  schedule        Start the cron daemon
  report          Print fare summary report
  export          Export data to CSV/JSON
  status          Show recent scrape run statuses
  db-init         Initialize the database
  routes          List all configured routes
  dashboard       Start the Web Analytics Dashboard
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint

# ── Logging setup ─────────────────────────────────────────────────────────────
from config.settings import settings

console = Console()

# Remove default loguru handler and add file + console handlers
logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    colorize=True,
)
logger.add(
    settings.log_dir / "scrape.log",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
)
logger.add(
    settings.log_dir / "errors.log",
    level="ERROR",
    rotation="5 MB",
    retention="14 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
)


# ── ASCII Banner ──────────────────────────────────────────────────────────────
BANNER = """
[bold cyan]
  ===================================================
  |      AirFare Scraper - MoSPI Price Index Tool   |
  |       Real-time Domestic Airfare Collection       |
  ===================================================
[/bold cyan]
"""


@click.group()
@click.version_option("1.0.0", prog_name="airfare-scraper")
def cli():
    """AirFare Scraper — Automated domestic airfare price collection for MoSPI."""
    rprint(BANNER)


# ── db-init ───────────────────────────────────────────────────────────────────
@cli.command("db-init")
def cmd_db_init():
    """Initialize the database (create tables)."""
    from db.database import init_db, health_check
    init_db()
    ok = health_check()
    if ok:
        console.print("[green]✓ Database initialized and healthy.[/green]")
    else:
        console.print("[red]✗ Database health check failed.[/red]")
        sys.exit(1)


# ── routes ────────────────────────────────────────────────────────────────────
@cli.command("routes")
def cmd_routes():
    """List all routes in the MoSPI basket."""
    from config.routes import ROUTE_BASKET, AIRPORTS
    from rich.table import Table
    from rich import box

    table = Table(title="MoSPI Route Basket", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Code", style="bold white", justify="center")
    table.add_column("Origin", style="green")
    table.add_column("Destination", style="yellow")

    for i, route in enumerate(ROUTE_BASKET, 1):
        table.add_row(
            str(i),
            route.code,
            AIRPORTS.get(route.origin, route.origin),
            AIRPORTS.get(route.destination, route.destination),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(ROUTE_BASKET)} routes[/dim]\n")


# ── scrape ────────────────────────────────────────────────────────────────────
@cli.command("scrape")
@click.option(
    "--route", "-r",
    default=None,
    help="Specific route code (e.g. DEL-BOM). Omit for full basket.",
)
@click.option(
    "--date", "-d",
    "travel_date",
    default=None,
    help="Travel date YYYY-MM-DD. Defaults to tomorrow.",
)
@click.option(
    "--days", "-n",
    default=None,
    type=int,
    help="Collect every day from T+1 through T+N. Omit to use configured T+1/T+7/T+15/T+30/T+45 windows.",
)
@click.option(
    "--portal", "-p",
    default=None,
    help="Specific portal to use (e.g. indigo_direct, makemytrip). Default: all.",
)
@click.option(
    "--airlines-only", "airlines_only",
    is_flag=True,
    default=False,
    help="Only run airline direct scrapers.",
)
@click.option(
    "--otas-only", "otas_only",
    is_flag=True,
    default=False,
    help="Only run OTA scrapers.",
)
@click.option(
    "--route-limit",
    default=None,
    type=click.IntRange(1, 34),
    help="Limit a full-basket run to the first N routes (useful for a short coverage run).",
)
@click.option(
    "--max-jobs",
    default=None,
    type=click.IntRange(1),
    help="Safety cap on source × route × date jobs.",
)
def cmd_scrape(route, travel_date, days, portal, airlines_only, otas_only, route_limit, max_jobs):
    """Run the scraper for one route or the full basket."""
    from db.database import init_db
    from orchestrator.job_runner import run_all, run_route
    from scraper import ALL_SCRAPERS, AIRLINE_SCRAPERS, OTA_SCRAPERS
    from config.routes import ROUTE_BASKET

    # Ensure DB is ready
    init_db()

    # Resolve scraper selection
    scraper_classes = ALL_SCRAPERS
    if airlines_only:
        scraper_classes = AIRLINE_SCRAPERS
    elif otas_only:
        scraper_classes = OTA_SCRAPERS
    elif portal:
        scraper_classes = [s for s in ALL_SCRAPERS if s.SOURCE_PORTAL == portal]
        if not scraper_classes:
            console.print(f"[red]Unknown portal: {portal}[/red]")
            available = [s.SOURCE_PORTAL for s in ALL_SCRAPERS]
            console.print(f"Available: {', '.join(available)}")
            sys.exit(1)

    # Resolve date(s)
    today = datetime.utcnow().date()
    if travel_date:
        travel_dates = [date.fromisoformat(travel_date)]
    elif days:
        travel_dates = [today + timedelta(days=d) for d in range(1, days + 1)]
    else:
        travel_dates = None  # Use settings default

    # Run
    console.print(f"[cyan]Starting scrape...[/cyan]")
    if route:
        results = asyncio.run(
            run_route(route, travel_dates, scraper_classes)
        )
    else:
        results = asyncio.run(
            run_all(
                scraper_classes=scraper_classes,
                routes=ROUTE_BASKET[:route_limit] if route_limit else None,
                travel_dates=travel_dates,
                max_jobs=max_jobs,
            )
        )

    # Summary
    success = sum(1 for r in results if r.get("status") == "SUCCESS")
    no_data = sum(1 for r in results if r.get("status") == "NO_DATA")
    unavailable = len(results) - success - no_data
    total_records = sum(r.get("records", 0) for r in results)
    console.print(
        f"\n[green]Done:[/green] {success} successful | {no_data} no data "
        f"| {unavailable} unavailable/failed | [bold]{total_records}[/bold] records saved\n"
    )


# ── schedule ──────────────────────────────────────────────────────────────────
@cli.command("schedule")
def cmd_schedule():
    """Start the automated scraping daemon (runs on cron schedule)."""
    from db.database import init_db
    from orchestrator.scheduler import ScrapeScheduler

    init_db()
    console.print(
        Panel(
            f"[cyan]Scheduler starting...[/cyan]\n"
            f"Cron: [yellow]{settings.scrape_cron}[/yellow] (Asia/Kolkata)\n"
            f"DB: [dim]{settings.database_url}[/dim]",
            title="AirFare Scheduler",
            border_style="cyan",
        )
    )
    scheduler = ScrapeScheduler()
    scheduler.start()


# ── report ────────────────────────────────────────────────────────────────────
@cli.command("report")
@click.option(
    "--date", "-d",
    "query_date",
    default=None,
    help="Travel date to report on (YYYY-MM-DD). Defaults to today.",
)
def cmd_report(query_date):
    """Print a fare summary report for a given travel date."""
    from db.database import init_db
    from reports.summary import print_daily_summary

    init_db()
    qd = date.fromisoformat(query_date) if query_date else None
    print_daily_summary(qd)


# ── status ────────────────────────────────────────────────────────────────────
@cli.command("status")
@click.option("--limit", "-n", default=20, help="Number of recent runs to show.")
def cmd_status(limit):
    """Show recent scrape run statuses."""
    from db.database import init_db
    from reports.summary import print_scrape_runs

    init_db()
    print_scrape_runs(limit)


# ── export ────────────────────────────────────────────────────────────────────
@cli.command("export")
@click.option(
    "--date", "-d",
    "query_date",
    default=None,
    help="Travel date YYYY-MM-DD. Defaults to today.",
)
@click.option(
    "--format", "-f",
    "fmt",
    type=click.Choice(["csv", "json", "both"]),
    default="csv",
    help="Export format.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Output file path (without extension).",
)
def cmd_export(query_date, fmt, output):
    """Export scraped fare data to CSV or JSON."""
    from db.database import init_db
    from reports.summary import export_csv, export_json

    init_db()
    qd = date.fromisoformat(query_date) if query_date else None
    out = Path(output) if output else None

    if fmt in ("csv", "both"):
        export_csv(qd, out.with_suffix(".csv") if out else None)
    if fmt in ("json", "both"):
        export_json(qd, out.with_suffix(".json") if out else None)


# ── dashboard ─────────────────────────────────────────────────────────────────
@cli.command("dashboard")
def cmd_dashboard():
    """Start the Web Analytics Dashboard (API + React UI)."""
    import subprocess
    import threading
    import webbrowser
    import time
    from db.database import init_db

    init_db()
    console.print("[cyan]Starting FastAPI Backend...[/cyan]")
    
    def run_backend():
        subprocess.run([sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"])
        
    def run_frontend():
        subprocess.run(["npm.cmd", "run", "dev"], cwd="web")

    # Start Backend
    t1 = threading.Thread(target=run_backend, daemon=True)
    t1.start()
    
    console.print("[cyan]Starting Vite React Frontend...[/cyan]")
    t2 = threading.Thread(target=run_frontend, daemon=True)
    t2.start()
    
    console.print("[green]Dashboard starting! Opening browser...[/green]")
    # Give Vite a second to start
    time.sleep(3)
    webbrowser.open("http://localhost:5173")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down dashboard...[/yellow]")
        sys.exit(0)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cli()
