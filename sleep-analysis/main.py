#!/usr/bin/env python3
"""
Baby Sleep Cycle Analyzer
Usage:
  python main.py                        # uses sample data
  python main.py --file path/to/export.json
  BT_EMAIL=x BT_PASSWORD=y python main.py --api
  python main.py --days 7               # analyze last 7 days
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

load_dotenv()

from baby_tracker import BabyTrackerClient
from analysis import SleepAnalyzer, PatternDetector
from recommendations import RecommendationEngine

console = Console()

SEVERITY_COLOR = {"info": "blue", "warning": "yellow", "concern": "red"}
PRIORITY_COLOR = {1: "red", 2: "yellow", 3: "cyan"}


def parse_args():
    parser = argparse.ArgumentParser(description="Baby Sleep Cycle Analyzer")
    parser.add_argument("--file", help="Path to Baby Tracker JSON export")
    parser.add_argument("--api", action="store_true", help="Fetch from Baby Tracker API")
    parser.add_argument("--days", type=int, default=14, help="Analysis window in days (default 14)")
    parser.add_argument("--baby", help="Baby name or ID (if account has multiple babies)")
    return parser.parse_args()


def build_client(args) -> BabyTrackerClient:
    if args.api:
        return BabyTrackerClient(
            email=os.getenv("BT_EMAIL"),
            password=os.getenv("BT_PASSWORD"),
        )
    data_file = args.file or os.getenv("BT_DATA_FILE")
    if not data_file:
        # Fall back to sample data
        sample = Path(__file__).parent / "sample_data" / "sample_sleep.json"
        data_file = str(sample)
        console.print(f"[dim]No data source specified. Using sample data: {sample.name}[/dim]\n")
    return BabyTrackerClient(data_file=data_file)


def select_baby(client, name_filter=None):
    babies = client.get_babies()
    if not babies:
        console.print("[red]No babies found in data source.[/red]")
        sys.exit(1)
    if name_filter:
        matches = [b for b in babies if name_filter.lower() in b.name.lower()]
        if matches:
            return matches[0]
    return babies[0]


def print_header(baby, days):
    console.print(Panel(
        f"[bold cyan]Baby Sleep Cycle Analyzer[/bold cyan]\n"
        f"Baby: [bold]{baby.name}[/bold]  |  Age: [bold]{baby.age_label}[/bold]  |  "
        f"Analyzing last [bold]{days} days[/bold]",
        box=box.DOUBLE_EDGE,
    ))


def print_daily_table(summaries):
    table = Table(title="Daily Sleep Summary", box=box.SIMPLE_HEAVY, show_lines=False)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Bedtime", width=10)
    table.add_column("Wake", width=10)
    table.add_column("Night (h)", justify="right", width=10)
    table.add_column("Naps (h)", justify="right", width=10)
    table.add_column("Total (h)", justify="right", width=10)
    table.add_column("Nap #", justify="right", width=7)

    for s in summaries[-10:]:
        bedtime_str = s.bedtime.strftime("%H:%M") if s.bedtime else "—"
        wake_str = s.first_morning_wake.strftime("%H:%M") if s.first_morning_wake else "—"
        total_color = "green" if s.total_sleep_hours >= 11 else ("yellow" if s.total_sleep_hours >= 9 else "red")
        wake_color = "red" if (s.wake_hour is not None and s.wake_hour < 6) else "white"
        table.add_row(
            str(s.date),
            bedtime_str,
            f"[{wake_color}]{wake_str}[/{wake_color}]",
            f"{s.night_sleep_hours:.1f}",
            f"{s.nap_sleep_hours:.1f}",
            f"[{total_color}]{s.total_sleep_hours:.1f}[/{total_color}]",
            str(s.nap_count),
        )
    console.print(table)


def print_stats(stats):
    table = Table(title="Averages", box=box.MINIMAL, show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    target_color = "green" if stats.avg_total_sleep >= stats.target_min else "red"
    table.add_row("Avg total sleep", f"[{target_color}]{stats.avg_total_sleep:.1f}h[/{target_color}] (target {stats.target_min}–{stats.target_max}h)")
    table.add_row("Avg night sleep", f"{stats.avg_night_sleep:.1f}h")
    table.add_row("Avg naps/day", f"{stats.avg_nap_count:.1f}")

    avg_wake_h = int(stats.avg_wake_hour)
    avg_wake_m = int((stats.avg_wake_hour % 1) * 60)
    wake_color = "red" if stats.avg_wake_hour < 6 else "green"
    table.add_row("Avg wake time", f"[{wake_color}]{avg_wake_h:02d}:{avg_wake_m:02d}[/{wake_color}]")

    console.print(table)


def print_patterns(patterns):
    if not patterns:
        console.print("[green]No concerning patterns detected.[/green]")
        return
    console.print("\n[bold]Detected Patterns[/bold]")
    for p in patterns:
        color = SEVERITY_COLOR[p.severity]
        console.print(
            Panel(
                f"[{color}][bold]{p.name}[/bold][/{color}] [{p.severity.upper()}]\n{p.description}",
                expand=False,
            )
        )


def print_recommendations(recs):
    console.print("\n[bold]Recommendations[/bold]")
    for i, r in enumerate(recs, 1):
        color = PRIORITY_COLOR[r.priority]
        steps = "\n".join(f"  {j+1}. {s}" for j, s in enumerate(r.action_steps))
        console.print(Panel(
            f"[{color}][bold]{r.priority_label}[/bold][/{color}]  {r.title}\n\n"
            f"[dim]{r.summary}[/dim]\n\n"
            f"[bold]Steps:[/bold]\n{steps}",
            title=f"#{i}",
            expand=False,
        ))


def main():
    args = parse_args()
    client = build_client(args)
    baby = select_baby(client, args.baby)
    records = client.get_sleep_records(baby.baby_id, days_back=args.days + 7)

    if not records:
        console.print("[red]No sleep records found for this period.[/red]")
        sys.exit(1)

    analyzer = SleepAnalyzer(baby, records)
    summaries = analyzer.daily_summaries(args.days)
    stats = analyzer.stats(args.days)

    print_header(baby, args.days)
    print_daily_table(summaries)
    print_stats(stats)

    detector = PatternDetector(summaries, stats)
    patterns = detector.detect_all()
    print_patterns(patterns)

    engine = RecommendationEngine(patterns, stats)
    recs = engine.generate()
    print_recommendations(recs)

    early_streak = analyzer.early_wake_streak()
    if early_streak >= 3:
        console.print(
            Panel(
                f"[bold red]Early wake streak: {early_streak} days in a row before 6 AM.[/bold red]\n"
                "See recommendations above — start with bedtime and wake window adjustments.",
                title="Key Finding",
                border_style="red",
            )
        )


if __name__ == "__main__":
    main()
