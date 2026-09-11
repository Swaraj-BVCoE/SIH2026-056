"""
reports/summary.py
───────────────────
Terminal report generator.
Produces rich tables of scraped fare data for a given date.
Can also export to CSV and JSON.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box
from loguru import logger

from pipeline.storage import get_daily_summary
from db.database import get_db
from db.models import FlightPrice, ScrapeRun

console = Console()


def print_daily_summary(query_date: Optional[date] = None) -> None:
    """Print a rich table summary of fares for the given date."""
    query_date = query_date or datetime.now(tz=timezone.utc).date()
    rows = get_daily_summary(query_date)

    if not rows:
        console.print(f"\n[yellow]No fare data found for {query_date}[/yellow]\n")
        return

    table = Table(
        title=f"✈  Airfare Summary — {query_date}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
    )
    table.add_column("Route", style="bold white", justify="center")
    table.add_column("Airline", style="green")
    table.add_column("Count", justify="right", style="dim")
    table.add_column("Min ₹", justify="right", style="bold green")
    table.add_column("Avg ₹", justify="right", style="yellow")
    table.add_column("Max ₹", justify="right", style="red")

    for row in rows:
        table.add_row(
            row["route"],
            row["airline"],
            str(row["count"]),
            f"{row['min_fare']:,.0f}",
            f"{row['avg_fare']:,.0f}",
            f"{row['max_fare']:,.0f}",
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Total: {len(rows)} airline-route combinations[/dim]\n")


def print_scrape_runs(limit: int = 20) -> None:
    """Print a summary of recent ScrapeRun audit records."""
    with get_db() as db:
        runs = (
            db.query(ScrapeRun)
            .order_by(ScrapeRun.started_at.desc())
            .limit(limit)
            .all()
        )

    if not runs:
        console.print("\n[yellow]No scrape runs found.[/yellow]\n")
        return

    table = Table(
        title="Recent Scrape Runs",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        border_style="bright_black",
    )
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Portal", style="cyan")
    table.add_column("Route", justify="center")
    table.add_column("Date", justify="center")
    table.add_column("Status")
    table.add_column("Records", justify="right")
    table.add_column("Duration", justify="right", style="dim")
    table.add_column("Error", style="red", no_wrap=False, max_width=40)

    for r in runs:
        status_style = {
            "SUCCESS": "[green]✓ SUCCESS[/green]",
            "FAILED": "[red]✗ FAILED[/red]",
            "RUNNING": "[yellow]⟳ RUNNING[/yellow]",
            "BLOCKED": "[orange]⊘ BLOCKED[/orange]",
        }.get(r.status, r.status)

        dur = f"{r.duration_seconds():.0f}s" if r.duration_seconds() else "-"

        table.add_row(
            str(r.id),
            r.source_portal,
            f"{r.origin}-{r.destination}",
            str(r.travel_date),
            status_style,
            str(r.records_inserted),
            dur,
            r.error_message or "",
        )

    console.print()
    console.print(table)
    console.print()


def export_csv(query_date: Optional[date] = None, output_path: Optional[Path] = None) -> Path:
    """Export all fares for a date to a CSV file."""
    query_date = query_date or datetime.now(tz=timezone.utc).date()

    with get_db() as db:
        records = (
            db.query(FlightPrice)
            .filter(FlightPrice.travel_date == query_date)
            .order_by(FlightPrice.origin, FlightPrice.destination, FlightPrice.total_fare)
            .all()
        )

    output_path = output_path or Path(f"data/fares_{query_date}.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id", "scraped_at", "travel_date", "origin", "destination",
        "airline", "flight_number", "departure_time", "arrival_time",
        "duration_minutes", "stops", "fare_class", "base_fare",
        "taxes_fees", "total_fare", "currency", "source_portal",
        "advance_days", "is_outlier",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({field: getattr(r, field, "") for field in fieldnames})

    console.print(f"[green]Exported {len(records)} records to {output_path}[/green]")
    return output_path


def export_json(query_date: Optional[date] = None, output_path: Optional[Path] = None) -> Path:
    """Export all fares for a date to a JSON file."""
    query_date = query_date or datetime.now(tz=timezone.utc).date()

    with get_db() as db:
        records = (
            db.query(FlightPrice)
            .filter(FlightPrice.travel_date == query_date)
            .order_by(FlightPrice.origin, FlightPrice.destination, FlightPrice.total_fare)
            .all()
        )

    output_path = output_path or Path(f"data/fares_{query_date}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = [
        {
            "id": r.id,
            "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            "travel_date": str(r.travel_date),
            "origin": r.origin,
            "destination": r.destination,
            "airline": r.airline,
            "flight_number": r.flight_number,
            "departure_time": str(r.departure_time) if r.departure_time else None,
            "arrival_time": str(r.arrival_time) if r.arrival_time else None,
            "duration_minutes": r.duration_minutes,
            "stops": r.stops,
            "fare_class": r.fare_class,
            "base_fare": r.base_fare,
            "taxes_fees": r.taxes_fees,
            "total_fare": r.total_fare,
            "currency": r.currency,
            "source_portal": r.source_portal,
            "advance_days": r.advance_days,
            "is_outlier": r.is_outlier,
        }
        for r in records
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    console.print(f"[green]Exported {len(records)} records to {output_path}[/green]")
    return output_path
