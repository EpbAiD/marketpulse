#!/usr/bin/env python3
"""
Gold Dip Alert System — 4-tier email notifications.

Runs once daily (typically after US market close via GitHub Actions).
Evaluates the current gold-futures price against four historically-validated
dip-buying triggers and sends an email to every recipient listed in
`configs/gold_alert_recipients.yaml`.

Tiers (all thresholds anchored to `scripts/diagnostics/gold_dip_threshold_research.py`):
  1. SEASONAL BUY (Jan-Feb only, -3% dip from 20d high)
     - Primary buy signal; combines seasonal cheapness with dip confirmation
     - Fires ~1.5x/year on average
  2. SEASONAL DEADLINE (Feb 28 if #1 never fired)
     - Prevents missing the seasonal window because no dip was steep enough
     - Fires only in years without a Q1 -3% dip
  3. OPPORTUNISTIC DIP (Mar-Dec, -5% dip from 20d high)
     - Out-of-season entry; historically beats waiting for next Q1 in 58% of cases
     - Fires ~3x/year
  4. MAJOR DIP (any time, -10% dip)
     - Quarter-conditional messaging (Q1/Q4 = strong buy, Q2 = warning, Q3 = judgment)
     - Fires ~0.7x/year

Deduplication state is tracked in `outputs/alerts/gold_alert_state.json`;
the workflow commits any changes back to the repo so tomorrow's run won't
re-fire the same alert.

Dry-run mode: pass --dry-run to compute alerts without sending emails or
mutating state — used in local testing.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
from currency_utils import (  # noqa: E402
    make_price_formatter, fx_footer_line, build_multi_currency_table_html,
)

RECIPIENTS_FILE = BASE_DIR / "configs" / "gold_alert_recipients.yaml"
STATE_FILE = BASE_DIR / "outputs" / "alerts" / "gold_alert_state.json"

GOLD_TICKER = "GC=F"
SEASONAL_MONTHS = (1, 2)
SEASONAL_DEADLINE_MONTH = 2
SEASONAL_DEADLINE_DAY = 28

SEASONAL_DIP_PCT = 3.0
OPPORTUNISTIC_DIP_PCT = 5.0
MAJOR_DIP_PCT = 10.0

# Minimum spacing between opportunistic / major alerts so we don't spam
# on consecutive down days.
OPPORTUNISTIC_MIN_GAP_DAYS = 30
MAJOR_MIN_GAP_DAYS = 30

# ---------------- Predictive tier (Tier 5) ----------------
# Uses MarketPulse's gold price forecast (if available locally) to predict
# dips 1-5 days ahead. Optional — the tier silently skips if forecast data
# is missing. Design principles:
#   - Conservative: fire only when the bias-corrected MEAN forecast crosses
#     a threshold (not the low end of the confidence band)
#   - Only look 1-5 days out (longer horizons are too noisy: ~3.5% MAE at 10d)
#   - Only fire if the projected pullback is DEEPER than today's actual pullback
#     (otherwise it's not "predictive", it's just delayed reactive)
#   - Cooldown of 5 days so we don't spam if the projection persists
PREDICTED_MAX_HORIZON_DAYS = 5
PREDICTED_MIN_GAP_DAYS = 5

# Forecast confidence gate: if the Day+1 raw forecast differs from current
# spot by more than this %, the model hasn't absorbed a recent shock and
# Tier 5 should skip. This is more robust than bias-correcting — an
# empirical out-of-sample test showed rolling-median bias correction
# doesn't reduce forecast error for this model (the model is already
# well-calibrated on average; errors are noise, not systematic drift).
# What we CAN do honestly is quantify per-forecast uncertainty via a
# confidence interval derived from the recent error distribution.
FORECAST_CONFIDENCE_GAP_PCT = 3.0
ERROR_STATS_LOOKBACK_DAYS = 60  # rolling window for computing forecast std

# Fallback error std (dollars) per horizon when we lack enough history.
# Values from ~5 months of historical forecast validation (May-Aug 2026).
GOLD_FORECAST_STD_FALLBACK_BY_HORIZON = {
    1: 88.0, 2: 102.0, 3: 112.0, 4: 121.0, 5: 138.0,
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def fetch_recent_gold() -> pd.DataFrame:
    """Fetch the last 60 trading days of gold futures. Enough for a 20d high."""
    df = yf.download(GOLD_TICKER, period="90d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()[["Date", "Close"]]
    df.columns = ["ds", "price"]
    df["ds"] = pd.to_datetime(df["ds"])
    return df.sort_values("ds").reset_index(drop=True)


def load_gold_forecast() -> list[dict] | None:
    """Load MarketPulse's most recent GOLD forecast if present.

    Reads outputs/inference/raw_forecasts_*.parquet (produced by the daily
    MarketPulse pipeline). Returns a list of {horizon_days, forecast_value}
    sorted by horizon (1..N), or None if no forecast is available.

    This is the one place the gold alert system touches MarketPulse. It's a
    one-way read — if the file is missing or stale, the predictive tier
    silently skips and the reactive tiers keep working as normal.
    """
    fc_dir = BASE_DIR / "outputs" / "inference"
    if not fc_dir.exists():
        return None
    files = sorted(fc_dir.glob("raw_forecasts_*.parquet"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        df = pd.read_parquet(files[0])
    except Exception:
        return None
    if "feature" not in df.columns or "ds" not in df.columns \
            or "forecast_value" not in df.columns:
        return None
    g = df[df["feature"] == "GOLD"].copy()
    if len(g) == 0:
        return None
    g["ds"] = pd.to_datetime(g["ds"])
    g = g.sort_values("ds").reset_index(drop=True)

    # Skip stale forecasts (>7 days old) — a stale forecast is worse than none.
    import re
    m = re.search(r"raw_forecasts_(\d{8})", files[0].name)
    if m:
        fc_date = datetime.strptime(m.group(1), "%Y%m%d").date()
        age = (datetime.utcnow().date() - fc_date).days
        if age > 7:
            return None

    # Filter out zero-value contamination and only keep future days
    today = pd.Timestamp(datetime.utcnow().date())
    g = g[(g["forecast_value"] > 100) & (g["ds"] > today)]
    if len(g) == 0:
        return None

    out = []
    for i, row in g.reset_index(drop=True).iterrows():
        horizon = (row["ds"].date() - datetime.utcnow().date()).days
        if 1 <= horizon <= PREDICTED_MAX_HORIZON_DAYS:
            out.append({
                "horizon_days": horizon,
                "date": row["ds"].date().isoformat(),
                "forecast_value": float(row["forecast_value"]),
            })
    return out or None


def compute_recent_error_stats() -> dict[int, float]:
    """Compute the standard deviation of forecast errors (in dollars) per
    horizon from the last ERROR_STATS_LOOKBACK_DAYS of historical forecasts
    vs actual gold closes.

    Used to construct honest confidence intervals around each forecast day:
    the 80% CI half-width is 1.28 * std, the 95% CI half-width is 1.96 * std.

    Returns {horizon_days: std_dollar}. Falls back to hardcoded values
    when history is too thin.
    """
    import glob, re
    files = sorted(glob.glob(str(BASE_DIR / "outputs" / "inference"
                                  / "raw_forecasts_*.parquet")))
    if len(files) < 10:
        return dict(GOLD_FORECAST_STD_FALLBACK_BY_HORIZON)

    cutoff = datetime.utcnow().date() - pd.Timedelta(days=ERROR_STATS_LOOKBACK_DAYS).to_pytimedelta()
    rows = []
    for f in files:
        m = re.search(r"raw_forecasts_(\d{8})", f)
        if not m:
            continue
        issue = datetime.strptime(m.group(1), "%Y%m%d").date()
        if issue < cutoff:
            continue
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        g = df[df["feature"] == "GOLD"].copy()
        if len(g) == 0:
            continue
        g["ds"] = pd.to_datetime(g["ds"])
        g = g[g["forecast_value"] > 100]
        g["horizon"] = (g["ds"].dt.date - issue).apply(lambda x: x.days)
        g = g[(g["horizon"] >= 1) & (g["horizon"] <= PREDICTED_MAX_HORIZON_DAYS)]
        rows.append(g[["ds", "horizon", "forecast_value"]])

    if not rows:
        return dict(GOLD_FORECAST_STD_FALLBACK_BY_HORIZON)

    fc = pd.concat(rows, ignore_index=True)
    start = fc["ds"].min().strftime("%Y-%m-%d")
    end = (fc["ds"].max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        actuals = yf.download(GOLD_TICKER, start=start, end=end,
                              progress=False, auto_adjust=True)
    except Exception:
        return dict(GOLD_FORECAST_STD_FALLBACK_BY_HORIZON)
    if isinstance(actuals.columns, pd.MultiIndex):
        actuals.columns = [c[0] if isinstance(c, tuple) else c for c in actuals.columns]
    actuals = (actuals.reset_index()[["Date", "Close"]]
               .rename(columns={"Date": "ds", "Close": "actual"}))
    actuals["ds"] = pd.to_datetime(actuals["ds"])
    merged = fc.merge(actuals, on="ds", how="inner")
    if len(merged) == 0:
        return dict(GOLD_FORECAST_STD_FALLBACK_BY_HORIZON)
    merged["error_dollar"] = merged["forecast_value"] - merged["actual"]

    stats = {}
    for h in range(1, PREDICTED_MAX_HORIZON_DAYS + 1):
        sub = merged[merged["horizon"] == h]
        if len(sub) < 5:
            stats[h] = GOLD_FORECAST_STD_FALLBACK_BY_HORIZON.get(h, 100.0)
        else:
            stats[h] = float(sub["error_dollar"].std())
    return stats


def confidence_interval(raw_forecast: float, horizon_days: int,
                        std_table: dict[int, float],
                        confidence: float = 0.80) -> tuple[float, float]:
    """Return (low, high) confidence interval around a raw forecast.

    Uses the historical std of forecast errors at the given horizon to
    construct a symmetric CI. Default 80% confidence uses z=1.28.
    """
    z = 1.96 if confidence >= 0.95 else 1.28  # 95% or 80% (simple two-level table)
    std = std_table.get(horizon_days,
                        GOLD_FORECAST_STD_FALLBACK_BY_HORIZON.get(horizon_days, 100.0))
    half_width = z * std
    return (raw_forecast - half_width, raw_forecast + half_width)


def compute_current_pullback(df: pd.DataFrame) -> dict:
    """Return today's close, 20d high, and pullback pct."""
    if len(df) < 20:
        raise ValueError(f"Need at least 20 trading days, got {len(df)}")
    latest = df.iloc[-1]
    roll_20d_high = df["price"].tail(20).max()
    pullback = (latest["price"] / roll_20d_high - 1) * 100
    return {
        "date": latest["ds"].date().isoformat(),
        "price": float(latest["price"]),
        "roll_20d_high": float(roll_20d_high),
        "pullback_pct": float(pullback),
        "quarter": (latest["ds"].month - 1) // 3 + 1,
        "month": int(latest["ds"].month),
    }


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def year_state(state: dict, year: int) -> dict:
    key = str(year)
    if key not in state:
        state[key] = {
            "seasonal_buy_fired": False,
            "seasonal_deadline_fired": False,
            "last_opportunistic_date": None,
            "last_major_date": None,
            "last_predicted_date": None,
        }
    # Backfill new keys on old state files so upgrades don't KeyError
    state[key].setdefault("last_predicted_date", None)
    return state[key]


def days_since(state_date_str: str | None, today_iso: str) -> int:
    if not state_date_str:
        return 10**6
    d1 = datetime.fromisoformat(state_date_str).date()
    d2 = datetime.fromisoformat(today_iso).date()
    return (d2 - d1).days


# --------------------------------------------------------------------------
# Tier evaluation
# --------------------------------------------------------------------------

def evaluate_tiers(ctx: dict, year_st: dict,
                   forecast: list[dict] | None = None,
                   std_table: dict[int, float] | None = None) -> list[dict]:
    """Return the list of alerts that should fire today (0-3 typically).

    `forecast`: optional MarketPulse gold forecast list from load_gold_forecast().
    When provided, Tier 5 (PREDICTED DIP) is evaluated in addition to the
    four reactive tiers. When None, Tier 5 silently skips.

    `std_table`: optional dict {horizon_days: std_dollar} for constructing
    honest confidence intervals around each forecast. Computed at runtime
    by main() from the last 60 days of forecasts vs actuals.
    """
    if std_table is None:
        std_table = GOLD_FORECAST_STD_FALLBACK_BY_HORIZON
    alerts = []
    month = ctx["month"]
    q = ctx["quarter"]
    pb = ctx["pullback_pct"]
    date = ctx["date"]

    # Tier 1 — Seasonal buy
    if (month in SEASONAL_MONTHS and pb <= -SEASONAL_DIP_PCT
            and not year_st["seasonal_buy_fired"]):
        alerts.append({
            "tier": "seasonal",
            "subject": "gold: good time to buy",
            "headline": "Good time to buy gold — BUY today",
            "detail": (
                f"Gold's price today is ${ctx['price']:.0f}. Its highest price "
                f"in the last 20 trading days was ${ctx['roll_20d_high']:.0f}, "
                f"so it's dropped {abs(pb):.1f}% from that recent peak.\n\n"
                f"On top of that, January and February are historically the "
                f"cheapest months of the year to buy gold — usually 3-5% "
                f"below the year's average price. So today you're getting "
                f"a double discount: cheap-time-of-year plus a recent dip."
            ),
            "playbook_action": "BUY today",
            "playbook_size": "About half to all of what you planned to spend on gold this year",
            "playbook_confidence": "High — this is one of the best signals I watch for",
            "playbook_odds": (
                "In the last 22 years, this exact situation has happened 134 "
                "times. About 66 out of every 100 times, gold was higher 3 "
                "months later — typical gain about 5%. Worst case: down 22% "
                "(Feb 2013)."
            ),
            "playbook_why": (
                "January and February are the historical low-price months for "
                "gold. A drop on top of that low-price season is unusually good. "
                "If you wait for a bigger drop, it often doesn't come — a 5% "
                "drop only happens about half of years, and a 7% drop only "
                "happens 15% of years. So don't hold out for perfect."
            ),
            "playbook_next": (
                "If gold keeps dropping (another 5% or 10% from here), I'll "
                "send you a bigger alert. Keep a little money aside just in "
                "case that happens."
            ),
        })

    # Tier 2 — Seasonal deadline (only fires on Feb 28 if Tier 1 never did)
    is_deadline_day = (month == SEASONAL_DEADLINE_MONTH
                       and datetime.fromisoformat(date).day >= SEASONAL_DEADLINE_DAY)
    if (is_deadline_day
            and not year_st["seasonal_buy_fired"]
            and not year_st["seasonal_deadline_fired"]):
        alerts.append({
            "tier": "deadline",
            "subject": "gold: last chance — buy today",
            "headline": "Cheap-buying season is ending — BUY TODAY",
            "detail": (
                f"Gold's price today is ${ctx['price']:.0f}. It's only down "
                f"{abs(pb):.1f}% from its recent high — no big dip happened "
                f"this year during the cheap buying months.\n\n"
                f"Today is the last practical trading day of February, the "
                f"end of gold's historical cheap-price season. If you wait "
                f"any longer, gold usually drifts higher through the rest "
                f"of the year, and you'd end up paying more."
            ),
            "playbook_action": "BUY TODAY",
            "playbook_size": "All of what you planned to spend on gold this year",
            "playbook_confidence": "High",
            "playbook_odds": (
                "Buying at the end of February has historically gotten you "
                "a price cheaper than about 73% of the days in the year. "
                "Waiting into spring/summer/fall usually costs an extra 3-11%."
            ),
            "playbook_why": (
                "The cheap months (January-February) are ending. Gold usually "
                "drifts up by about 1% per month for the rest of the year. So "
                "waiting for a better price rarely works — just buy today and "
                "lock in the seasonal discount."
            ),
            "playbook_next": (
                "If gold has an unusual big drop later in the year "
                "(especially October-December), I'll send another alert."
            ),
        })

    # Tier 3 — Opportunistic dip (out of season)
    if (month not in SEASONAL_MONTHS
            and pb <= -OPPORTUNISTIC_DIP_PCT
            and days_since(year_st["last_opportunistic_date"], date) >= OPPORTUNISTIC_MIN_GAP_DAYS):
        # Quarter-conditional playbook — different quarters have different histories
        q_playbook = {
            2: {  # April-June — dangerous
                "subject_tag": "risky drop — wait",
                "action": "WAIT — don't buy yet",
                "size": "Zero, or a very small amount only if you have extra money set aside",
                "confidence": "Low — this drop looks risky",
                "odds": ("About 55% of similar drops turned into a buying "
                         "opportunity. But the ones that failed (April 2008, "
                         "April 2013) kept falling much further and took "
                         "years to come back — so the risk of getting it "
                         "wrong is high."),
                "why": ("Drops in April-June have historically been unreliable — "
                        "sometimes they're a chance to buy cheap, sometimes "
                        "they're the start of a big decline that lasts years. "
                        "Not worth risking a big purchase here. If you already "
                        "bought earlier in the year, sit this one out."),
            },
            3: {  # July-September — middle of road
                "subject_tag": "buy a small amount",
                "action": "BUY a small amount",
                "size": "About a quarter to a third of what you planned to spend on gold this year",
                "confidence": "Medium — decent but not great",
                "odds": ("About 6 out of every 10 similar drops in July-September "
                         "turned profitable within 3 months. When they worked, "
                         "you'd have made about 3-5% back."),
                "why": ("July-September drops are middle-of-the-road — not the "
                        "best time to buy, not the worst. If you didn't buy "
                        "earlier in the year (January-February) and have money "
                        "set aside, this is a reasonable chance to get in."),
            },
            4: {  # October-December — strong
                "subject_tag": "buy today",
                "action": "BUY today",
                "size": "About 40-60% of whatever gold-buying money you have left this year",
                "confidence": "Medium-High — reliable time of year",
                "odds": ("About 7-8 out of every 10 similar drops in "
                         "October-December turned profitable within 3 months. "
                         "Typical gain when they worked: 5-8%."),
                "why": ("October-December is when gold demand is highest globally "
                        "— Indian wedding season and Chinese New Year buying "
                        "push demand up. Prices in this window tend to bounce "
                        "back quickly."),
            },
        }.get(q, {
            "subject_tag": "review", "action": "REVIEW",
            "size": "Use your judgment", "confidence": "Unknown",
            "odds": "Not enough historical data for this quarter.",
            "why": "Not enough historical data for this quarter."})

        # Plain-English name for the quarter
        q_name = {2: "April-June", 3: "July-September", 4: "October-December"}.get(q, "")
        alerts.append({
            "tier": "opportunistic",
            "subject": f"gold: bigger drop — {q_playbook['subject_tag']}",
            "headline": f"Gold dropped more than usual — {q_playbook['action']}",
            "detail": (
                f"Gold's price today is ${ctx['price']:.0f}. Its highest price "
                f"in the last 20 trading days was ${ctx['roll_20d_high']:.0f}, "
                f"so it's dropped {abs(pb):.1f}% from that recent peak.\n\n"
                f"This isn't the historically cheap buying season "
                f"(January-February). It's happening in {q_name}. What that "
                f"means for you depends on the time of year — see the "
                f"recommendation below."
            ),
            "playbook_action": q_playbook["action"],
            "playbook_size": q_playbook["size"],
            "playbook_confidence": q_playbook["confidence"],
            "playbook_odds": q_playbook["odds"],
            "playbook_why": q_playbook["why"],
            "playbook_next": (
                "If gold keeps falling and drops another 5% or more (10% total "
                "from the recent peak), you'll get a bigger alert with a "
                "stronger recommendation."
            ),
        })

    # Tier 4 — Major dip (any time), quarter-conditional messaging
    if (pb <= -MAJOR_DIP_PCT
            and days_since(year_st["last_major_date"], date) >= MAJOR_MIN_GAP_DAYS):
        q_playbook = {
            1: {
                "tag": "big drop in cheap season — BUY BIG",
                "action": "BUY A LOT today",
                "size": "About 75% of what you planned to spend on gold this year. Keep 25% aside in case it drops even more.",
                "confidence": "High — this is a rare opportunity",
                "odds": ("This size of drop in January-March happens only rarely "
                         "(3 times in 22 years). 2 out of 3 times, gold was "
                         "higher 3 months later — typical gain about 5%."),
                "why": ("A 10% drop in gold is uncommon — it happens roughly "
                        "once a year on average. When it happens during "
                        "January-February (already the cheap season), it's "
                        "historically one of the very best times to buy. "
                        "This kind of opportunity is worth acting on."),
                "next": ("Keep 25% aside for 2-3 weeks. If gold drops another "
                         "5%+ from here, use that money too. If it starts "
                         "rising, you can add it later or hold for another year."),
            },
            2: {
                "tag": "DANGER — DO NOT BUY",
                "action": "DO NOT BUY today",
                "size": "Zero — sit this one out",
                "confidence": "High that skipping this is the right call",
                "odds": ("Only 2 out of 4 similar drops in April-June recovered. "
                         "The 2 that failed (April 2008, April 2013) kept "
                         "dropping another 30% and took years to come back."),
                "why": ("Big drops in April-June have historically been "
                        "dangerous. The two most famous ones (April 2008 and "
                        "April 2013) both marked the start of gold bear markets "
                        "that lasted years. Trying to catch this dip is like "
                        "trying to catch a falling knife — even if you're "
                        "sometimes right, when you're wrong it hurts a lot."),
                "next": ("Wait until gold has clearly stopped falling and starts "
                         "recovering (specifically: gold trading above its "
                         "average price over the last 200 days) before "
                         "considering any buy."),
            },
            3: {
                "tag": "unclear — use judgment",
                "action": "MAYBE BUY a small amount — use your own judgment",
                "size": "At most 20-30%, and only if the overall economy looks stable",
                "confidence": "Medium — not much history to go on",
                "odds": ("Only 2 similar drops in July-September in 22 years. "
                         "1 recovered, 1 didn't. Not enough data to make a "
                         "strong statistical call."),
                "why": ("Big drops in July-September are so rare (only 2 in 22 "
                        "years) that I can't give you a confident recommendation "
                        "either way. If the broader economy looks calm (interest "
                        "rates falling, dollar weakening, stock markets steady), "
                        "gold usually benefits. If things look shaky, sit it out."),
                "next": ("If a similar big drop happens later in October-December, "
                         "that's a much more reliable buy signal — save your "
                         "money for that."),
            },
            4: {
                "tag": "STRONG BUY — historically works every time",
                "action": "BUY A LOT today",
                "size": "About 75% of what you planned to spend on gold this year. Keep 25% aside in case it drops even more.",
                "confidence": "Very High — historically the strongest signal",
                "odds": ("All 4 similar drops in October-December in the last 22 "
                         "years turned profitable within 3 months. Typical gain "
                         "was 8%. Worst outcome was still up 3.6% (Dec 2011)."),
                "why": ("October-December drops of this size have a perfect "
                        "historical track record (4 for 4). This is because "
                        "Asian gold demand (Indian weddings, Chinese New Year) "
                        "is highest right now, so sellers hit a wall of buyers "
                        "and prices bounce back quickly. This is the most "
                        "reliable buy signal I watch for."),
                "next": ("Keep 25% aside for 2-3 weeks. If gold drops another "
                         "5%+ (extremely rare — hasn't happened in 22 years), "
                         "use that money too."),
            },
        }[q]
        q_name = {1: "January-March", 2: "April-June",
                  3: "July-September", 4: "October-December"}.get(q, "")
        alerts.append({
            "tier": "major",
            "subject": f"gold: BIG drop — {q_playbook['tag']}",
            "headline": f"Gold has dropped a lot — {q_playbook['action']}",
            "detail": (
                f"Gold's price today is ${ctx['price']:.0f}. Its highest price "
                f"in the last 20 trading days was ${ctx['roll_20d_high']:.0f}, "
                f"so it's dropped {abs(pb):.1f}% from that recent peak — a "
                f"big move.\n\n"
                f"This is happening in {q_name}, which matters a lot: "
                f"different times of year have very different track records "
                f"for how this kind of drop plays out. See the recommendation."
            ),
            "playbook_action": q_playbook["action"],
            "playbook_size": q_playbook["size"],
            "playbook_confidence": q_playbook["confidence"],
            "playbook_odds": q_playbook["odds"],
            "playbook_why": q_playbook["why"],
            "playbook_next": q_playbook["next"],
        })

    # Tier 5 — Predicted dip advance warning (conservative)
    # Fires only when the raw point-estimate forecast for one of the next
    # 1-5 days projects a pullback that:
    #   (a) crosses one of the reactive tier thresholds
    #   (b) is DEEPER than today's actual pullback (otherwise it's not
    #       genuinely predictive — just reactive with delay)
    #   (c) hasn't been alerted on within the last PREDICTED_MIN_GAP_DAYS
    #   (d) the model's Day+1 forecast is within FORECAST_CONFIDENCE_GAP_PCT
    #       of current spot — otherwise the model hasn't absorbed a recent
    #       shock and its projections are untrustworthy
    #
    # The alert email includes 80% confidence intervals around each
    # projected day so recipients see the real uncertainty, not just the
    # point estimate. We use the RAW forecast (no bias correction) after
    # empirically confirming that rolling-median correction doesn't reduce
    # error for this model — it's already well-calibrated.
    if (forecast is not None
            and days_since(year_st.get("last_predicted_date"), date) >= PREDICTED_MIN_GAP_DAYS):
        # Forecast-confidence gate: is the model close enough to current spot
        # for its projections to be trustworthy?
        day1 = next((f for f in forecast if f["horizon_days"] == 1), None)
        if day1 is not None:
            confidence_gap_pct = abs(day1["forecast_value"] / ctx["price"] - 1) * 100
        else:
            confidence_gap_pct = 0.0
        if confidence_gap_pct > FORECAST_CONFIDENCE_GAP_PCT:
            # Skip Tier 5 — the model is out of sync with current spot; its
            # projections aren't reliable enough to base an advance-warning
            # alert on. Reactive tiers keep working.
            return alerts

        high = ctx["roll_20d_high"]
        current_pb = pb
        best = None  # (projected_pb, horizon, forecast_price, tier_tag, ci_low, ci_high)
        for f in forecast:
            raw = f["forecast_value"]
            proj_pb = (raw / high - 1) * 100
            # Must be deeper than today AND cross a threshold
            if proj_pb >= current_pb:
                continue
            if proj_pb <= -MAJOR_DIP_PCT:
                tag = "MAJOR"
                thresh_pct = MAJOR_DIP_PCT
            elif proj_pb <= -OPPORTUNISTIC_DIP_PCT:
                tag = "OPPORTUNISTIC"
                thresh_pct = OPPORTUNISTIC_DIP_PCT
            elif proj_pb <= -SEASONAL_DIP_PCT and month in SEASONAL_MONTHS:
                tag = "SEASONAL"
                thresh_pct = SEASONAL_DIP_PCT
            else:
                continue
            # Keep the deepest / soonest projection
            if best is None or proj_pb < best[0]:
                best = (proj_pb, f["horizon_days"], raw, tag, thresh_pct, f["date"])

        if best is not None:
            proj_pb, horizon, forecast_price, tag, thresh_pct, proj_date = best
            # Honest 80% confidence interval around the point forecast
            ci_low, ci_high = confidence_interval(forecast_price, horizon,
                                                  std_table, confidence=0.80)
            ci_low_pb = (ci_low / high - 1) * 100
            ci_high_pb = (ci_high / high - 1) * 100
            is_high_conv = ci_high_pb <= -thresh_pct

            # Suggested limit-order target: place a buy order at the FORECAST
            # price (not the deeper CI low), so if actual arrives above
            # forecast we still catch it, and if it drops further we let
            # the reactive tier handle it.
            limit_target = forecast_price

            if is_high_conv:
                action = f"SET UP an automatic buy order at ${forecast_price:.0f}"
                size = "About a third to half of what you'd normally buy on this signal"
                confidence = "High — the model is quite sure a drop is coming"
                odds = ("When the model is this confident, about 7-8 out of 10 "
                        "predictions actually come true within a few days.")
                why = (f"The model expects gold to drop to about ${forecast_price:.0f} "
                       f"in the next {horizon} days. Setting up an automatic buy "
                       f"order at that price now means you catch the dip if it "
                       f"happens, without having to watch the price all day.")
            else:
                action = "WAIT — just a heads-up, don't buy yet"
                size = "Zero for now"
                confidence = "Low-to-Medium — the model isn't fully sure"
                odds = ("About 5-6 out of 10 predictions like this actually come "
                        "true. Not reliable enough to act on by itself.")
                why = (f"The model thinks a drop might happen but it's not confident. "
                       f"Rather than buying based on a maybe, wait to see if the "
                       f"drop actually happens. If it does, you'll get a real "
                       f"alert with a real recommendation.")

            alerts.append({
                "tier": "predicted",
                "subject": f"gold: heads-up — a drop is likely in {horizon} days",
                "headline": f"Heads-up: a drop is likely in about {horizon} days",
                "detail": (
                    f"Gold's price today is ${ctx['price']:.0f} (down "
                    f"{abs(current_pb):.1f}% from its recent peak of ${high:.0f}).\n\n"
                    f"The model that predicts gold prices thinks gold will "
                    f"drop to about ${forecast_price:.0f} in {horizon} trading "
                    f"days. If that actually happens, gold would be down "
                    f"{abs(proj_pb):.1f}% from its recent peak — a bigger drop "
                    f"than today.\n\n"
                    f"The model isn't perfect. Based on how it's done before, "
                    f"there's a good chance (80%) that gold will land somewhere "
                    f"between ${ci_low:.0f} and ${ci_high:.0f} on that day. "
                    f"That's a range of about ±{(ci_high - forecast_price)/forecast_price*100:.1f}% "
                    f"around the guess."
                ),
                "playbook_action": action,
                "playbook_size": size,
                "playbook_confidence": confidence,
                "playbook_odds": odds,
                "playbook_why": why,
                "playbook_limit_target": (
                    f"${limit_target:.0f}" if is_high_conv else None),
                "playbook_next": (
                    "If gold actually drops as predicted in the next few days, "
                    "you'll get a real buy alert with a real recommendation. "
                    "If it goes up instead, cancel any limit order you set — "
                    "this prediction turned out to be a false alarm."
                ),
            })

    return alerts


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def _localize_prices(html: str, price_fmt, fx_line: str) -> str:
    """Substitute every $NNN[.NN] price mention in the email with the
    equivalent in the recipient's currency. Adds an FX footer line at
    the bottom of the disclaimer paragraph so the reader knows the rate."""
    import re
    def _sub(m):
        raw = m.group(1).replace(",", "")
        try:
            usd = float(raw)
        except ValueError:
            return m.group(0)
        return price_fmt(usd)
    # Match $1234, $1,234, $1234.56, $1,234.56 (with or without commas / decimals)
    out = re.sub(r"\$([\d]{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)", _sub, html)
    if fx_line:
        # Insert FX-rate note into the closing disclaimer paragraph
        out = out.replace(
            "Nothing here is personal financial advice",
            f"{fx_line}<br>Nothing here is personal financial advice",
        )
    return out


def render_html(alert: dict, ctx: dict, recipient_name: str | None,
                price_fmt=None, fx_line: str = "",
                multi_currency_table: str = "") -> str:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"

    # Build the prominent playbook box if the alert carries prescriptive fields
    playbook_html = ""
    action = alert.get("playbook_action")
    if action:
        size = alert.get("playbook_size", "")
        confidence = alert.get("playbook_confidence", "")
        why = alert.get("playbook_why", "")
        limit_target = alert.get("playbook_limit_target")
        next_step = alert.get("playbook_next", "")

        # Colored border by action type
        action_upper = action.upper()
        if "STAND DOWN" in action_upper or "DO NOT" in action_upper:
            accent = "#C0392B"  # red
        elif "BUY" in action_upper and "SELECTIVELY" not in action_upper:
            accent = "#27AE60"  # green
        elif "MONITOR" in action_upper or "PREPARE" in action_upper:
            accent = "#E67E22"  # amber
        else:
            accent = "#1F4E79"  # blue

        limit_row = ""
        if limit_target:
            limit_row = f"""
      <div style="margin-top: 0.5rem;">
        <span style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Suggested automatic buy price</span>
        <div style="font-size: 1.1rem; color: {accent}; font-weight: 500;">{limit_target}</div>
      </div>"""

        odds = alert.get("playbook_odds", "")
        odds_row = ""
        if odds:
            odds_row = f"""
    <div style="margin-top: 0.9rem; padding: 0.75rem 0.9rem; background: #F8F9FA; border-left: 3px solid {accent}; border-radius: 2px;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px; margin-bottom: 0.25rem;">How often this has worked before</div>
      <div style="font-size: 0.9rem; color: #2C3E50; font-weight: 500;">{odds}</div>
    </div>"""

        playbook_html = f"""
  <div style="border: 2px solid {accent}; padding: 1.1rem 1.3rem; border-radius: 4px; margin: 1.5rem 0; background: #FDFDFD;">
    <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.8px;">What to do</div>
    <div style="font-size: 1.5rem; color: {accent}; font-weight: 600; margin: 0.3rem 0 0.9rem;">{action}</div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.7rem 1.2rem; margin-bottom: 0.9rem;">
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">How much to buy</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{size}</div>
      </div>
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">How sure I am</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{confidence}</div>
      </div>
    </div>
    {limit_row}
    {odds_row}

    <div style="margin-top: 0.9rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Why this recommendation</div>
      <div style="font-size: 0.9rem; color: #34495E; margin-top: 0.25rem;">{why}</div>
    </div>

    <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">What might happen next</div>
      <div style="font-size: 0.9rem; color: #34495E; margin-top: 0.25rem;">{next_step}</div>
    </div>
  </div>"""
    else:
        # Legacy alerts (test-email etc) still have a simple action field
        legacy_action = alert.get("action", "")
        if legacy_action:
            playbook_html = f"""
  <div style="background: #F8F9FA; padding: 0.9rem 1.1rem; border-radius: 3px; margin: 1.25rem 0;">
    <div style="text-transform: uppercase; font-size: 0.7rem; color: #7F8C8D; margin-bottom: 0.3rem;">Suggested framing</div>
    <div style="font-size: 0.95rem; color: #34495E;">{legacy_action}</div>
  </div>"""

    html = f"""<!doctype html><html><body style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #2C3E50; line-height: 1.55;">
  <div style="border-left: 4px solid #1F4E79; padding: 1.25rem 1.5rem; background: #F8F9FA;">
    <div style="text-transform: uppercase; font-size: 0.75rem; color: #7F8C8D; letter-spacing: 0.5px;">Gold Dip Alert · {ctx['date']}</div>
    <h1 style="margin: 0.3rem 0 0.6rem; font-size: 1.4rem; color: #1F4E79; font-weight: 500;">{alert['headline']}</h1>
    <div style="color: #34495E; font-size: 0.95rem;">
      Gold today: ${ctx['price']:.0f} · Recent 20-day peak: ${ctx['roll_20d_high']:.0f} · Down {abs(ctx['pullback_pct']):.1f}% from that peak
    </div>
  </div>

  <p>{greeting}</p>

  <p style="font-size: 0.95rem;">{alert['detail'].replace(chr(10) + chr(10), '</p><p style="font-size: 0.95rem;">')}</p>

  {multi_currency_table}

  {playbook_html}

  <p style="color: #7F8C8D; font-size: 0.8rem; margin-top: 2rem; border-top: 1px solid #ECF0F1; padding-top: 0.8rem;">
    These recommendations come from studying how gold has behaved over the last 21 years.
    Nothing here is personal financial advice — just a guide based on historical patterns.
    Only spend money you can afford to hold for years, and never bet more than you're
    comfortable losing.
  </p>
</body></html>"""

    if price_fmt is not None:
        html = _localize_prices(html, price_fmt, fx_line)
    return html


def send_email(smtp_host: str, smtp_port: int, sender: str, password: str,
               recipient: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def _run_test_email() -> int:
    """Send synthetic sample alerts to every recipient so they can see what
    real production alerts will look like — including the Tier 5 predictive
    alert with its confidence-interval framing.

    Sends two emails per recipient:
      1. A canned delivery-test alert
      2. A synthetic Tier 5 predictive alert built with realistic numbers,
         so recipients see the CI + auto-conviction classification format
         they'll get on real predicted dips.

    Doesn't touch state or evaluate real market conditions.
    """
    with open(RECIPIENTS_FILE) as f:
        cfg = yaml.safe_load(f)
    recipients = cfg.get("recipients", [])
    if not recipients:
        print("No recipients configured — nothing to test.")
        return 0

    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("ERROR: GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set.")
        return 1

    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
    today = datetime.utcnow().date().isoformat()

    # Alert 1: canned delivery-test
    delivery_test = {
        "tier": "test",
        "subject": "gold: test alert #1/2 — delivery check",
        "headline": "Delivery test — you can ignore",
        "detail": (
            "This is a one-time delivery test. Alert #2 (arriving next) "
            "is a synthetic sample of the new Tier 5 predictive-dip alert "
            "with confidence-interval framing, so you can see the format "
            "before any real one fires."
        ),
        "action": "No action needed. Confirms the pipeline works.",
    }
    zero_ctx = {"date": today, "price": 0.0, "roll_20d_high": 0.0,
                "pullback_pct": 0.0, "quarter": 0, "month": 0}

    # Alert 2: synthetic Tier 5 with realistic numbers. Uses the SAME
    # evaluate_tiers() logic that runs in production — so what recipients
    # see is exactly the real alert format, not a hand-written mock.
    try:
        df = fetch_recent_gold()
        ctx = compute_current_pullback(df)
    except Exception:
        # Fallback: hardcoded realistic context
        ctx = {"date": today, "price": 4481.0, "roll_20d_high": 4641.0,
               "pullback_pct": -3.44, "quarter": 3, "month": 9}
    ctx["date"] = today
    ctx["quarter"] = 3  # force Q3 so the synthetic alert framing makes sense

    try:
        std_table = compute_recent_error_stats()
    except Exception:
        std_table = dict(GOLD_FORECAST_STD_FALLBACK_BY_HORIZON)

    # Force a synthetic forecast that will trigger Tier 5 OPPORTUNISTIC:
    # Day+1 close to spot (passes confidence gate), Day+3 projects a -6% dip
    # from the 20d high.
    synth_forecast = [
        {"horizon_days": 1, "date": today,
         "forecast_value": ctx["price"] * 1.002},   # ~0.2% off spot — passes gate
        {"horizon_days": 3, "date": today,
         "forecast_value": ctx["roll_20d_high"] * 0.937},  # -6.3% pullback
    ]
    empty_yr_st = {"seasonal_buy_fired": True,  # suppress Tier 1
                   "seasonal_deadline_fired": False,
                   "last_opportunistic_date": None,
                   "last_major_date": None,
                   "last_predicted_date": None}
    real_tier5 = evaluate_tiers(ctx, empty_yr_st, forecast=synth_forecast,
                                std_table=std_table)
    # Filter to just the Tier 5 alert and relabel as a test
    sample_predicted = None
    for a in real_tier5:
        if a["tier"] == "predicted":
            sample_predicted = {
                **a,
                "subject": "gold: test alert #2/2 — sample predictive-tier alert",
                "headline": "SAMPLE: " + a["headline"],
                "detail": (
                    "This is a SYNTHETIC test alert showing the format of a "
                    "real predictive-tier email. The numbers below are real "
                    "current market data with a fabricated forecast that "
                    "would trigger the OPPORTUNISTIC threshold.\n\n"
                    + a["detail"]
                ),
            }
            break

    alerts_to_send = [delivery_test]
    if sample_predicted:
        alerts_to_send.append(sample_predicted)

    fx_cache: dict[str, tuple] = {}
    def get_fx(code: str):
        code = (code or "USD").upper()
        if code not in fx_cache:
            fx_cache[code] = make_price_formatter(code)
        return fx_cache[code]

    sent, failed = 0, 0
    for r in recipients:
        email = r.get("email")
        if not email:
            continue

        currencies_list = r.get("currencies")
        if currencies_list:
            currencies_list = [c.upper() for c in currencies_list]
            price_fmt = None
            fx_line = ""
            label = f"multi:{','.join(currencies_list)}"
        else:
            currency = r.get("currency", "USD")
            price_fmt, rate, _ = get_fx(currency)
            fx_line = fx_footer_line(currency, rate)
            currencies_list = None
            label = currency

        for alert in alerts_to_send:
            ctx_for_alert = zero_ctx if alert["tier"] == "test" else ctx
            if currencies_list:
                multi_table = build_multi_currency_table_html(
                    {"Gold today": ctx_for_alert["price"],
                     "20-day peak": ctx_for_alert["roll_20d_high"]},
                    currencies_list,
                ) if ctx_for_alert["price"] > 0 else ""
            else:
                multi_table = ""
            try:
                send_email(smtp_host, smtp_port, sender, password,
                           email, alert["subject"],
                           render_html(alert, ctx_for_alert, r.get("name"),
                                       price_fmt=price_fmt, fx_line=fx_line,
                                       multi_currency_table=multi_table))
                print(f"  sent [{alert['tier']}] -> {email} ({label})")
                sent += 1
            except Exception as e:
                print(f"  FAILED [{alert['tier']}] -> {email}: {type(e).__name__}: {e}")
                failed += 1
    print(f"\nTest delivery: {sent} sent, {failed} failed "
          f"({len(alerts_to_send)} emails per recipient).")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate alerts and print, but do not send email or mutate state.")
    parser.add_argument("--test-email", action="store_true",
                        help="Send a canned test alert to every recipient to verify "
                             "delivery end-to-end. Does not touch state or evaluate "
                             "real market conditions.")
    args = parser.parse_args()

    # Test-email mode short-circuits everything else
    if args.test_email:
        return _run_test_email()

    # Load recipients
    with open(RECIPIENTS_FILE) as f:
        cfg = yaml.safe_load(f)
    recipients = cfg.get("recipients", [])
    if not recipients:
        print("No recipients configured in gold_alert_recipients.yaml — nothing to do.")
        return 0

    # Fetch and evaluate
    df = fetch_recent_gold()
    ctx = compute_current_pullback(df)
    print(f"Current gold: ${ctx['price']:.2f} on {ctx['date']} "
          f"(pullback {ctx['pullback_pct']:.2f}% from 20d high ${ctx['roll_20d_high']:.0f}) · Q{ctx['quarter']}")

    # Optional MarketPulse forecast for Tier 5 (predictive)
    forecast = load_gold_forecast()
    if forecast:
        print(f"MarketPulse gold forecast loaded: {len(forecast)} horizon days available "
              f"(range: {forecast[0]['date']} .. {forecast[-1]['date']})")
    else:
        print("MarketPulse gold forecast not available — predictive tier will be skipped.")

    # Compute honest per-horizon std of forecast errors from the last
    # ERROR_STATS_LOOKBACK_DAYS. Used to build 80% confidence intervals
    # in the predictive-tier alert email.
    std_table = None
    if forecast is not None:
        std_table = compute_recent_error_stats()
        print(f"Forecast error std (from last {ERROR_STATS_LOOKBACK_DAYS}d): "
              + " ".join(f"D+{h}=±${v:.0f}" for h, v in sorted(std_table.items())))

    state = load_state()
    yr = datetime.fromisoformat(ctx["date"]).year
    yr_st = year_state(state, yr)

    alerts = evaluate_tiers(ctx, yr_st, forecast=forecast, std_table=std_table)

    if not alerts:
        print("No alerts triggered today.")
        return 0

    print(f"{len(alerts)} alert(s) triggered:")
    for a in alerts:
        print(f"  - [{a['tier']}] {a['subject']}")

    if args.dry_run:
        print("\n--- DRY RUN: would send the following ---")
        for a in alerts:
            print(f"\n=== SUBJECT: {a['subject']} ===")
            print(f"HEADLINE: {a['headline']}")
            print(f"DETAIL: {a['detail']}")
            print(f"ACTION: {a.get('playbook_action') or a.get('action', '')}")
            if a.get('playbook_size'):
                print(f"SIZE:   {a['playbook_size']}")
            if a.get('playbook_odds'):
                print(f"ODDS:   {a['playbook_odds']}")
        return 0

    # Send
    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("ERROR: GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set — cannot send.")
        return 1

    # Cache per-currency formatter so we only fetch each FX rate once
    fx_cache: dict[str, tuple] = {}
    def get_fx(code: str):
        code = (code or "USD").upper()
        if code not in fx_cache:
            fx_cache[code] = make_price_formatter(code)
        return fx_cache[code]

    sent = 0
    for r in recipients:
        email = r.get("email")
        if not email:
            continue
        name = r.get("name")
        wanted_tiers = set(r.get("tiers") or
                           ["seasonal", "deadline", "opportunistic", "major", "predicted"])

        # Two modes: `currencies: [list]` shows all in one email as a
        # comparison table; `currency: SINGLE` localizes the body.
        currencies_list = r.get("currencies")
        if currencies_list:
            currencies_list = [c.upper() for c in currencies_list]
            price_fmt = None   # body stays in USD; table shows all currencies
            fx_line = ""
            multi_table = build_multi_currency_table_html(
                {"Gold today": ctx["price"], "20-day peak": ctx["roll_20d_high"]},
                currencies_list,
            )
            label = f"multi:{','.join(currencies_list)}"
        else:
            currency = r.get("currency", "USD")
            price_fmt, rate, _ = get_fx(currency)
            fx_line = fx_footer_line(currency, rate)
            multi_table = ""
            label = currency

        for a in alerts:
            if a["tier"] not in wanted_tiers:
                continue
            try:
                send_email(smtp_host, smtp_port, sender, password,
                           email, a["subject"],
                           render_html(a, ctx, name,
                                       price_fmt=price_fmt, fx_line=fx_line,
                                       multi_currency_table=multi_table))
                print(f"  sent [{a['tier']}] -> {email} ({label})")
                sent += 1
            except Exception as e:
                print(f"  FAILED [{a['tier']}] -> {email}: {type(e).__name__}: {e}")

    # Update state to prevent re-firing
    for a in alerts:
        if a["tier"] == "seasonal":
            yr_st["seasonal_buy_fired"] = True
        elif a["tier"] == "deadline":
            yr_st["seasonal_deadline_fired"] = True
        elif a["tier"] == "opportunistic":
            yr_st["last_opportunistic_date"] = ctx["date"]
        elif a["tier"] == "major":
            yr_st["last_major_date"] = ctx["date"]
        elif a["tier"] == "predicted":
            yr_st["last_predicted_date"] = ctx["date"]
    save_state(state)
    print(f"State updated → {STATE_FILE}")

    return 0 if sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
