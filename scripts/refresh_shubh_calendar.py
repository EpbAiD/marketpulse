#!/usr/bin/env python3
"""Shubh calendar refresher.

The Panchang (Hindu almanac) for future years is only published as those
years approach. This script inspects `configs/shubh_calendar.json`, tells
you how much forward coverage remains, and prints the refresh recipe.

There is no reliable free public API for Panchang covering all the
observances we track (Ekadashi, Amavasya, Purnima, Pushya Nakshatra,
gold-specific festivals). The calendar was built by running four
parallel research agents against drik-panchang.com, mypanchang.com, and
gold-industry sources. That process is re-run manually when coverage
drops. Instructions below.

Usage:
    python scripts/refresh_shubh_calendar.py            # status report
    python scripts/refresh_shubh_calendar.py --check    # exit 1 if <30d
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CALENDAR_PATH = BASE_DIR / "configs" / "shubh_calendar.json"

REFRESH_INSTRUCTIONS = """
To refresh configs/shubh_calendar.json:

1. Open a Claude Code session in this repo.
2. Ask: "Refresh the shubh calendar. Coverage is running low — fetch
   panchang data for {year_range} covering ekadashi, amavasya, purnima,
   pushya nakshatra, plus all gold-specific festivals (Dhanteras,
   Akshaya Tritiya, Pushya Yoga days). Merge into
   configs/shubh_calendar.json, keep existing history, replace
   coverage.end with the new farthest date."
3. Claude will dispatch parallel agents (one per year batch),
   deduplicate, and rewrite the JSON.
4. Verify with:
       python scripts/shubh_calendar.py $(date +%F)
   which prints coverage + today's shubh status.
5. Commit configs/shubh_calendar.json.

No API keys or scraping infra required — the research agents handle
source triangulation. Expected time: 3-5 minutes.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if forward coverage is under 30 days.")
    args = parser.parse_args()

    if not CALENDAR_PATH.exists():
        print(f"configs/shubh_calendar.json not found — cultural boost is off.")
        return 1

    payload = json.loads(CALENDAR_PATH.read_text())
    cov = payload.get("coverage", {})
    end_iso = cov.get("end")
    start_iso = cov.get("start")
    n = payload.get("n_events", len(payload.get("events", [])))

    today = date.today()
    if end_iso:
        end = datetime.fromisoformat(end_iso).date()
        days_left = (end - today).days
    else:
        days_left = -1

    print(f"Calendar file:     {CALENDAR_PATH}")
    print(f"Coverage:          {start_iso} → {end_iso}")
    print(f"Events tracked:    {n}")
    print(f"Today:             {today}")
    print(f"Forward coverage:  {days_left} days")

    if days_left < 30:
        print("\nSTATUS: LOW — refresh needed within a few weeks.")
        next_year = today.year + 1
        year_range = f"{today.year} through {next_year + 1}"
        print(REFRESH_INSTRUCTIONS.format(year_range=year_range))
        if args.check:
            return 1
    elif days_left < 120:
        print("\nSTATUS: OK for now, refresh within the next few months.")
    else:
        print("\nSTATUS: fine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
