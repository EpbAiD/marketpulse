#!/usr/bin/env python3
"""
Historical backtest for the gold dip alert system.

Replays every trading day from 2005 to present, running the exact same
evaluate_tiers() logic that runs in production, and records every alert
that would have fired. Confirms the alert frequency and timing match the
design expectations before we deploy.

Reuses the production alert code directly — this is not a reimplementation.
Any drift between design intent and implementation shows up here.

Output:
  - Summary table: alerts by year, by tier
  - Frequency check: alerts per year vs expected frequency
  - Sample alert timings for each tier
  - Quarter breakdown of major alerts (should match the pattern that
    justified the quarter-conditional messaging)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE))

from scripts.gold_dip_alerts import evaluate_tiers, year_state, days_since  # noqa


def fetch_full_history() -> pd.DataFrame:
    """Load 21+ years of gold-futures daily closes."""
    df = yf.download("GC=F", start="2005-01-01", end="2026-07-14",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()[["Date", "Close"]]
    df.columns = ["ds", "price"]
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.sort_values("ds").reset_index(drop=True)
    df["roll_20d_high"] = df["price"].rolling(20).max()
    df["pullback_pct"] = (df["price"] / df["roll_20d_high"] - 1) * 100
    df["quarter"] = ((df["ds"].dt.month - 1) // 3 + 1).astype(int)
    df["month"] = df["ds"].dt.month.astype(int)
    return df


def replay(df: pd.DataFrame) -> list[dict]:
    """Iterate day-by-day; run the production alert evaluator; record fires."""
    state: dict = {}
    fired: list[dict] = []

    for i, row in df.iterrows():
        if pd.isna(row["roll_20d_high"]):
            continue  # not enough history yet
        ctx = {
            "date": row["ds"].date().isoformat(),
            "price": float(row["price"]),
            "roll_20d_high": float(row["roll_20d_high"]),
            "pullback_pct": float(row["pullback_pct"]),
            "quarter": int(row["quarter"]),
            "month": int(row["month"]),
        }
        yr = row["ds"].year
        yr_st = year_state(state, yr)
        alerts = evaluate_tiers(ctx, yr_st)
        for a in alerts:
            fired.append({
                "date": ctx["date"], "year": yr, "quarter": ctx["quarter"],
                "month": ctx["month"], "tier": a["tier"],
                "price": ctx["price"], "pullback_pct": ctx["pullback_pct"],
                "subject": a["subject"],
            })
        # Advance state exactly as production would
        for a in alerts:
            if a["tier"] == "seasonal":
                yr_st["seasonal_buy_fired"] = True
            elif a["tier"] == "deadline":
                yr_st["seasonal_deadline_fired"] = True
            elif a["tier"] == "opportunistic":
                yr_st["last_opportunistic_date"] = ctx["date"]
            elif a["tier"] == "major":
                yr_st["last_major_date"] = ctx["date"]

    return fired


def summarize(fired: list[dict], years: int) -> None:
    if not fired:
        print("NO ALERTS FIRED ACROSS FULL HISTORY — something is wrong.")
        return
    df = pd.DataFrame(fired)

    print(f"Total alerts fired across {years} years: {len(df)}\n")

    # By tier — frequency check
    counts = df["tier"].value_counts()
    expected = {"seasonal": 1.5, "deadline": 0.2, "opportunistic": 3.0, "major": 0.7}
    print(f"{'Tier':<15} {'Total':>7} {'/year':>8} {'expected':>10} {'status':>10}")
    print("-" * 60)
    for tier in ["seasonal", "deadline", "opportunistic", "major"]:
        n = int(counts.get(tier, 0))
        per_year = n / years
        exp = expected[tier]
        # "OK" if within a factor of 2 either way — expected is approximate
        status = "OK" if 0.5 * exp <= per_year <= 2.0 * exp else "REVIEW"
        print(f"{tier:<15} {n:>7} {per_year:>7.2f} {exp:>10.2f}   {status:>8}")

    # By year — every year covered
    print(f"\nAlerts per calendar year:")
    per_year = df.groupby("year").size()
    for yr in sorted(per_year.index):
        marker = "" if per_year[yr] > 0 else "  ← empty year"
        print(f"  {yr}: {per_year[yr]}{marker}")

    # MAJOR alerts by quarter (validates the quarter-conditional design)
    print(f"\nMAJOR alerts by quarter (validates the quarter-conditional framing):")
    major_df = df[df["tier"] == "major"]
    for q in [1, 2, 3, 4]:
        q_events = major_df[major_df["quarter"] == q]
        print(f"  Q{q}: {len(q_events)} major-tier events")
        for _, row in q_events.iterrows():
            print(f"     {row['date']}  ${row['price']:.0f}  pullback {row['pullback_pct']:.2f}%")

    # Sample recent seasonal alerts (last 5)
    print(f"\nMost recent Tier 1 (SEASONAL) alerts:")
    seasonal = df[df["tier"] == "seasonal"].tail(5)
    for _, row in seasonal.iterrows():
        print(f"  {row['date']}  ${row['price']:.0f}  pullback {row['pullback_pct']:.2f}%")

    # Years where the DEADLINE tier fired (seasonal never triggered)
    print(f"\nYears where seasonal deadline fired (no -3% Q1 dip that year):")
    deadline_years = df[df["tier"] == "deadline"]["year"].tolist()
    if deadline_years:
        for yr in deadline_years:
            print(f"  {yr}")
    else:
        print("  (none — every year had a Q1 -3% dip)")


def main():
    print("Loading 21 years of gold-futures history...")
    df = fetch_full_history()
    print(f"Loaded {len(df)} trading days from {df['ds'].min().date()} to {df['ds'].max().date()}\n")
    print("Replaying alert system day-by-day using production evaluate_tiers()...\n")
    fired = replay(df)
    years = df["ds"].dt.year.nunique()
    summarize(fired, years)


if __name__ == "__main__":
    main()
