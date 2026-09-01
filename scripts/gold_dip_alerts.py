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
            "subject": "gold: Q1 seasonal dip triggered — BUY",
            "headline": "Primary buying signal fired — BUY 50-100% at market",
            "detail": (
                f"Gold pulled back {pb:.2f}% from its trailing 20-day high of "
                f"${ctx['roll_20d_high']:.0f} to today's close of ${ctx['price']:.0f}. "
                f"This is inside the Jan-Feb seasonal window where gold has "
                f"historically been ~3-5% cheaper than the yearly average, "
                f"and a -3% dip fires in most years. Combined discount vs "
                f"the typical yearly price: roughly 5-8%. This is the primary "
                f"entry point in the strategy."
            ),
            "playbook_action": "BUY at market",
            "playbook_size": "50-100% of your intended annual gold position",
            "playbook_confidence": "High",
            "playbook_why": (
                "This is the seasonal + dip combination that historically "
                "delivered the best entry each year. Deploying most of your "
                "annual budget now typically beats waiting for a deeper dip "
                "because -5% or -7% Q1 dips don't reliably show up: they "
                "happen in only 55% / 15% of years."
            ),
            "playbook_next": (
                "If a deeper -5% or -10% dip follows in Q1, the Opportunistic "
                "or Major tier will fire — save 20-50% dry powder in case it does."
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
            "subject": "gold: Q1 window closing — BUY NOW (no dip fired)",
            "headline": "Seasonal deadline — BUY 100% at market today",
            "detail": (
                f"Today is the last practical trading day of the Jan-Feb "
                f"seasonal buying window. No -3% dip triggered this year, "
                f"so the strategy defaults to buying at market to secure "
                f"the seasonal discount before Q2. Current close ${ctx['price']:.0f} "
                f"(pullback from 20d high: {pb:.2f}%)."
            ),
            "playbook_action": "BUY at market",
            "playbook_size": "100% of your intended annual gold position",
            "playbook_confidence": "High",
            "playbook_why": (
                "The seasonal window is closing. Waiting into Q2 historically "
                "costs 2-5% because gold drifts up ~1% per month on average and "
                "the seasonal edge disappears. Buy at whatever the market offers "
                "today — don't hold out for a dip that hasn't come."
            ),
            "playbook_next": (
                "If an unusual Q2-Q4 opportunity fires later (e.g. a MAJOR -10% "
                "in Q4 with STRONG BUY tag), you can add on top with dry powder."
            ),
        })

    # Tier 3 — Opportunistic dip (out of season)
    if (month not in SEASONAL_MONTHS
            and pb <= -OPPORTUNISTIC_DIP_PCT
            and days_since(year_st["last_opportunistic_date"], date) >= OPPORTUNISTIC_MIN_GAP_DAYS):
        # Quarter-conditional playbook — different quarters have different histories
        q_playbook = {
            2: {  # Q2 — dangerous
                "subject_tag": "MONITOR",
                "action": "MONITOR — do not chase",
                "size": "0-20% only if you have unallocated capital",
                "confidence": "Low",
                "why": ("Q2 -5% dips have mixed history — sometimes real buying "
                        "opportunities, sometimes the start of a longer decline "
                        "(Apr 2008 and Apr 2013 were both bear-market starts). "
                        "If you already deployed via Tier 1 or 2 in Q1, stand down."),
            },
            3: {  # Q3 — middle of road
                "subject_tag": "BUY selectively",
                "action": "BUY selectively",
                "size": "25-40% if you skipped Q1 or have dry powder",
                "confidence": "Medium",
                "why": ("Q3 -5% dips are historically middle-of-the-road — modest "
                        "positive expected return, no strong signal either way. "
                        "Reasonable catch-up entry if you missed the seasonal window."),
            },
            4: {  # Q4 — strong
                "subject_tag": "BUY",
                "action": "BUY at market",
                "size": "40-60% of any remaining annual budget",
                "confidence": "Medium-High",
                "why": ("Q4 dips are historically strong — Asian physical demand "
                        "kicks in through Q4 (Indian wedding season Oct-Dec, "
                        "Chinese New Year positioning Dec-Jan) providing a "
                        "mechanical bid. Even out-of-season Q4 dips often recover."),
            },
        }.get(q, {
            "subject_tag": "review", "action": "REVIEW",
            "size": "Use judgment", "confidence": "Unknown",
            "why": "No historical playbook for this quarter."})

        alerts.append({
            "tier": "opportunistic",
            "subject": f"gold: -{OPPORTUNISTIC_DIP_PCT:.0f}% dip Q{q} — {q_playbook['subject_tag']}",
            "headline": f"Opportunistic Q{q} dip — {q_playbook['action']}",
            "detail": (
                f"Gold pulled back {pb:.2f}% from its trailing 20-day high "
                f"of ${ctx['roll_20d_high']:.0f} to today's close of "
                f"${ctx['price']:.0f}. This is outside the primary Jan-Feb "
                f"window. Historically, out-of-season -5% dips beat waiting "
                f"for the next seasonal window in 58% of cases."
            ),
            "playbook_action": q_playbook["action"],
            "playbook_size": q_playbook["size"],
            "playbook_confidence": q_playbook["confidence"],
            "playbook_why": q_playbook["why"],
            "playbook_next": (
                "If a MAJOR -10% dip follows within a few weeks, that will "
                "fire the Major tier with quarter-specific framing."
            ),
        })

    # Tier 4 — Major dip (any time), quarter-conditional messaging
    if (pb <= -MAJOR_DIP_PCT
            and days_since(year_st["last_major_date"], date) >= MAJOR_MIN_GAP_DAYS):
        q_playbook = {
            1: {
                "tag": "STRONG BUY",
                "action": "BUY aggressively",
                "size": "75% at market, 25% held for possible follow-through",
                "confidence": "High",
                "why": ("Q1 -10% dips historically recovered in 2 of 3 events with "
                        "a median +4.6% at 90 days. Combined with Q1 seasonal "
                        "cheapness, this is one of the strongest signals the strategy "
                        "produces. Rare event — take it when it comes."),
                "next": ("Hold 25% dry powder for 2-3 weeks in case a follow-on "
                         "-15%+ dip occurs, in which case add the balance."),
            },
            2: {
                "tag": "WARNING — STAND DOWN",
                "action": "STAND DOWN — do not buy",
                "size": "0%",
                "confidence": "High that NOT buying is correct",
                "why": ("Q2 -10% dips have historically been dangerous. April 2008 "
                        "and April 2013 both marked the start of multi-year gold "
                        "bear markets. Only 2 of 4 Q2 events recovered, and the "
                        "failures were severe (-30%+ additional drawdown). The "
                        "safest play is to wait for the trend to confirm."),
                "next": ("Watch for gold to reclaim its 200-day moving average "
                         "before considering an add. Do not average down blindly."),
            },
            3: {
                "tag": "USE JUDGMENT",
                "action": "SMALL POSITION only if macro supports it",
                "size": "20-30% conservative sizing",
                "confidence": "Medium",
                "why": ("Q3 -10% dips have a small historical sample (2 events) "
                        "with mixed outcomes. No strong statistical prior. If "
                        "broader macro (real yields falling, DXY weak, credit "
                        "spreads calm) supports gold, a modest add is defensible."),
                "next": ("If a Q4 MAJOR fires within a month, that's the higher-"
                         "conviction moment to deploy more."),
            },
            4: {
                "tag": "STRONG BUY",
                "action": "BUY aggressively",
                "size": "75% at market, 25% held for possible follow-through",
                "confidence": "Very High",
                "why": ("Q4 -10% dips have recovered in 4 of 4 historical events "
                        "with a median +8.3% at 90 days. Asian physical demand "
                        "(Indian weddings Oct-Dec, Chinese New Year Dec-Jan) "
                        "typically provides a mechanical bid. This is the most "
                        "reliable buying setup in the strategy."),
                "next": ("Hold 25% dry powder for 2-3 weeks. If a further -15%+ "
                         "dip occurs, add the balance — those are extremely rare."),
            },
        }[q]
        alerts.append({
            "tier": "major",
            "subject": f"gold: MAJOR -{MAJOR_DIP_PCT:.0f}% dip Q{q} — {q_playbook['tag']}",
            "headline": f"MAJOR dip in Q{q}: {q_playbook['action']}",
            "detail": (
                f"Gold has fallen {pb:.2f}% from its trailing 20-day high "
                f"of ${ctx['roll_20d_high']:.0f} to today's close of "
                f"${ctx['price']:.0f}. Events of this magnitude fire roughly "
                f"once a year on average."
            ),
            "playbook_action": q_playbook["action"],
            "playbook_size": q_playbook["size"],
            "playbook_confidence": q_playbook["confidence"],
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
                action = "PREPARE — place buy limit order"
                size = "30-50% of your intended add for this signal"
                confidence = "High (even the optimistic end of the CI crosses the threshold)"
                why = (f"Every plausible outcome in the 80% confidence range would "
                       f"still trip the {tag} threshold. This is a high-conviction "
                       f"forecast; getting a limit order in place today lets you "
                       f"catch the entry at your target instead of chasing.")
            else:
                action = "MONITOR — do not act preemptively"
                size = "0% until reactive tier confirms"
                confidence = "Low-to-medium (probabilistic warning)"
                why = (f"The 80% confidence range spans both a {tag} dip AND no dip. "
                       f"This is a heads-up that the model thinks a dip is likely, "
                       f"not a confirmed signal. Wait for the reactive tier to "
                       f"actually fire on real prices before buying.")

            alerts.append({
                "tier": "predicted",
                "subject": f"[PREDICTED] gold: {tag} dip expected in {horizon}d — {action.split(' ')[0]}",
                "headline": f"Forecast projects a {tag} dip in ~{horizon} day(s) — {action}",
                "detail": (
                    f"Today: spot ${ctx['price']:.0f} · 20-day high ${high:.0f} · "
                    f"pullback {current_pb:.2f}%.\n\n"
                    f"The forecasting model projects gold at ~${forecast_price:.0f} "
                    f"on {proj_date} (in {horizon} trading day(s)). If that comes "
                    f"in as forecast, the pullback would deepen to {proj_pb:.2f}% "
                    f"— crossing the {tag} threshold of -{thresh_pct:.0f}%.\n\n"
                    f"Honest 80% confidence range: "
                    f"${ci_low:.0f} to ${ci_high:.0f} "
                    f"(±{(ci_high - forecast_price)/forecast_price*100:.1f}% around the "
                    f"point estimate). In pullback terms: {ci_low_pb:.2f}% to "
                    f"{ci_high_pb:.2f}%."
                ),
                "playbook_action": action,
                "playbook_size": size,
                "playbook_confidence": confidence,
                "playbook_why": why,
                "playbook_limit_target": (
                    f"${limit_target:.0f}" if is_high_conv else None),
                "playbook_next": (
                    "If the reactive tier fires within a few days on actual "
                    "prices, execute the balance of your position at market. "
                    "If gold recovers instead, cancel the limit order — this "
                    "was a false alarm and the reactive tiers will stay quiet."
                ),
            })

    return alerts


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def render_html(alert: dict, ctx: dict, recipient_name: str | None) -> str:
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
        <span style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Suggested limit order</span>
        <div style="font-size: 1.1rem; color: {accent}; font-weight: 500;">{limit_target}</div>
      </div>"""

        playbook_html = f"""
  <div style="border: 2px solid {accent}; padding: 1.1rem 1.3rem; border-radius: 4px; margin: 1.5rem 0; background: #FDFDFD;">
    <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.8px;">Playbook</div>
    <div style="font-size: 1.5rem; color: {accent}; font-weight: 600; margin: 0.3rem 0 0.9rem;">{action}</div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.7rem 1.2rem; margin-bottom: 0.9rem;">
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Size</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{size}</div>
      </div>
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Confidence</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{confidence}</div>
      </div>
    </div>
    {limit_row}

    <div style="margin-top: 0.9rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Why this size / action</div>
      <div style="font-size: 0.9rem; color: #34495E; margin-top: 0.25rem;">{why}</div>
    </div>

    <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">What to watch next</div>
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

    return f"""<!doctype html><html><body style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #2C3E50; line-height: 1.55;">
  <div style="border-left: 4px solid #1F4E79; padding: 1.25rem 1.5rem; background: #F8F9FA;">
    <div style="text-transform: uppercase; font-size: 0.75rem; color: #7F8C8D; letter-spacing: 0.5px;">Gold Dip Alert · {ctx['date']}</div>
    <h1 style="margin: 0.3rem 0 0.6rem; font-size: 1.4rem; color: #1F4E79; font-weight: 500;">{alert['headline']}</h1>
    <div style="color: #34495E; font-size: 0.95rem;">
      Spot ${ctx['price']:.0f} · 20-day high ${ctx['roll_20d_high']:.0f} · pullback {ctx['pullback_pct']:.2f}% · Q{ctx['quarter']}
    </div>
  </div>

  <p>{greeting}</p>

  <p style="font-size: 0.95rem;">{alert['detail'].replace(chr(10) + chr(10), '</p><p style="font-size: 0.95rem;">')}</p>

  {playbook_html}

  <p style="color: #7F8C8D; font-size: 0.8rem; margin-top: 2rem; border-top: 1px solid #ECF0F1; padding-top: 0.8rem;">
    This alert is generated from statistical analysis of 21 years of gold-futures history.
    It's for informational use only — not personalized investment advice. Adapt to your own
    mandate and risk budget before acting.
  </p>
</body></html>"""


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

    sent, failed = 0, 0
    for r in recipients:
        email = r.get("email")
        if not email:
            continue
        for alert in alerts_to_send:
            ctx_for_alert = zero_ctx if alert["tier"] == "test" else ctx
            try:
                send_email(smtp_host, smtp_port, sender, password,
                           email, alert["subject"],
                           render_html(alert, ctx_for_alert, r.get("name")))
                print(f"  sent [{alert['tier']}] -> {email}")
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
            print(f"ACTION: {a['action']}")
        return 0

    # Send
    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("ERROR: GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set — cannot send.")
        return 1

    sent = 0
    for r in recipients:
        email = r.get("email")
        if not email:
            continue
        name = r.get("name")
        wanted_tiers = set(r.get("tiers") or
                           ["seasonal", "deadline", "opportunistic", "major", "predicted"])
        for a in alerts:
            if a["tier"] not in wanted_tiers:
                continue
            try:
                send_email(smtp_host, smtp_port, sender, password,
                           email, a["subject"], render_html(a, ctx, name))
                print(f"  sent [{a['tier']}] -> {email}")
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
