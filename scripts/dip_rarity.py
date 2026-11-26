"""Historical dip rarity analyzer.

Given the current drawdown from a recent peak, this answers two questions
by looking at the full 22-year gold history:

  1. HOW RARE is a dip of this depth? (percentile across all trading days)
  2. OF THE TIMES this happened, did gold keep falling or recover?
     (conditional probability of a further X% drop within N days)

The output feeds the alert email so the reader doesn't have to guess
whether to act now or wait for a deeper dip. The core finding over 22
years is that gold's upward trend means deep dips recover fast —
waiting usually misses the entry.

Why a 90-day drawdown base (not 20 like the alert tier):
  - The alert tier (compute_current_pullback) uses a 20-day peak to
    CATCH dips as they form. Rarity asks a different question: "is this
    a once-a-year or once-in-a-decade event?" That requires a longer
    reference peak so a shallow 20-day noise doesn't look rare.
  - 90 days captures the recent bull run of a cycle without going so
    long that two separate cycles get blended.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = BASE_DIR / "outputs" / "alerts" / "gold_rarity_cache.parquet"
RARITY_LOOKBACK_DAYS = 90       # peak reference for drawdown
RARITY_HISTORY_YEARS = 22


def _ensure_dir() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _fetch_gold_history() -> pd.DataFrame:
    """Fetch 22 years of daily gold close prices, cache to parquet.

    Refreshes the cache if older than 7 days — stale data is fine for
    distribution shape but we don't want to drift forever. The alert's
    current drawdown is computed from the live fetch in gold_dip_alerts.py,
    not from this cache, so cache staleness only affects the historical
    distribution (which is slow-moving).
    """
    _ensure_dir()
    if CACHE_FILE.exists():
        age_days = (datetime.utcnow() - datetime.utcfromtimestamp(
            CACHE_FILE.stat().st_mtime)).days
        if age_days < 7:
            return pd.read_parquet(CACHE_FILE)
    start = (datetime.utcnow().date() - pd.Timedelta(days=365*RARITY_HISTORY_YEARS + 30)).isoformat()
    g = yf.download("GC=F", start=start, progress=False, auto_adjust=True)
    if isinstance(g.columns, pd.MultiIndex):
        g.columns = [c[0] if isinstance(c, tuple) else c for c in g.columns]
    df = g.reset_index()[["Date", "Close"]].rename(columns={"Date": "ds", "Close": "price"})
    df["ds"] = pd.to_datetime(df["ds"])
    df.to_parquet(CACHE_FILE, index=False)
    return df


@lru_cache(maxsize=4)
def _precompute_drawdown_distribution(lookback: int = RARITY_LOOKBACK_DAYS) -> pd.DataFrame:
    """For every historical day, compute drawdown from its trailing
    `lookback`-day peak. Returned frame has columns (ds, price,
    peak, drawdown_pct). Cached in-process."""
    df = _fetch_gold_history().copy().sort_values("ds").reset_index(drop=True)
    df["peak"] = df["price"].rolling(lookback, min_periods=1).max()
    df["drawdown_pct"] = (df["price"] / df["peak"] - 1) * 100
    return df


def rarity_analysis(current_drawdown_pct: float,
                    forward_windows: tuple = (30, 90),
                    additional_drops: tuple = (3, 5, 10),
                    lookback: int = RARITY_LOOKBACK_DAYS) -> dict:
    """Answer the two headline questions about today's dip.

    Args:
      current_drawdown_pct: today's drawdown from the 20-day peak,
        expressed as a NEGATIVE number (e.g. -8.5 for an 8.5% dip).
      forward_windows: look this many trading days ahead to see if gold
        dropped further.
      additional_drops: thresholds for the forward look (in percent).

    Returns a dict:
      {
        'current_dd_pct': float,
        'observations': int,         # historical days analyzed
        'as_deep_count': int,        # historical days at least this deep
        'as_deep_pct': float,        # percentile: smaller = rarer
        'conditional': {
            '30d': {'3': prob_of_3pct_further, '5': ..., '10': ...},
            '90d': {...},
        },
        'verdict': 'ACT NOW' | 'CONSIDER' | 'PATIENT WAIT',
        'verdict_reason': str,
      }
    """
    if current_drawdown_pct >= 0:
        # Not a dip — no analysis
        return {
            "current_dd_pct": current_drawdown_pct,
            "observations": 0,
            "as_deep_count": 0,
            "as_deep_pct": 100.0,
            "conditional": {},
            "verdict": "NO DIP",
            "verdict_reason": "Price is at or above its recent peak.",
        }

    hist = _precompute_drawdown_distribution(lookback=lookback)
    hist = hist.dropna(subset=["drawdown_pct"])
    total = len(hist)
    # Days that were AT LEAST as deep as today (more negative drawdown)
    as_deep = hist[hist["drawdown_pct"] <= current_drawdown_pct]
    as_deep_count = len(as_deep)
    as_deep_pct = as_deep_count / total * 100 if total else 100.0

    # Conditional: of those as-deep historical days, how often did gold
    # drop ANOTHER X% within N days?
    prices = hist.set_index("ds")["price"]
    conditional = {}
    for horizon in forward_windows:
        row = {}
        for drop in additional_drops:
            target = 1 - drop / 100
            further = 0
            for ds_val, p in zip(as_deep["ds"], as_deep["price"]):
                # Forward window of `horizon` TRADING days
                fwd = prices.loc[ds_val:].iloc[1:horizon + 1]
                if len(fwd) == 0:
                    continue
                min_fwd = fwd.min()
                if min_fwd / p <= target:
                    further += 1
            denom = sum(1 for ds_val, p in zip(as_deep["ds"], as_deep["price"])
                        if len(prices.loc[ds_val:].iloc[1:horizon + 1]) > 0)
            row[str(drop)] = (further / denom * 100) if denom else None
        conditional[f"{horizon}d"] = row

    # Verdict — act now / consider / patient wait
    verdict, reason = _verdict(current_drawdown_pct, as_deep_pct, conditional)
    return {
        "current_dd_pct": current_drawdown_pct,
        "observations": total,
        "as_deep_count": as_deep_count,
        "as_deep_pct": as_deep_pct,
        "conditional": conditional,
        "verdict": verdict,
        "verdict_reason": reason,
    }


def _verdict(dd_pct: float, as_deep_pct: float, conditional: dict) -> tuple[str, str]:
    """Turn the numbers into one of three actionable labels, grounded in
    22 years of gold's actual behavior.

    Key observation: gold's long-run trend is upward, so a rare dip is a
    rare entry. Even when there's a 25-30% chance of a further 5% drop,
    that still means 70-75% of the time this was the right entry — and
    the DEPTH of the dip itself is the dominant signal.

      ACT NOW      — top 15% rare dip (deeper than 85% of all days ever)
      PATIENT WAIT — common dip (not in top 30%) AND further drops likely
      CONSIDER     — between
    """
    cond_30 = conditional.get("30d", {})
    prob_further_5 = cond_30.get("5")
    if prob_further_5 is None:
        return ("CONSIDER", "Not enough historical data to score this dip precisely.")

    # Rank: "top X%" where lower X = rarer. A dip in top 1% of history is
    # once-in-two-years or rarer.
    rank_text = f"top {as_deep_pct:.1f}%" if as_deep_pct >= 1 else f"top {as_deep_pct:.2f}%"
    cheaper_than = 100 - as_deep_pct
    cheaper_text = (f"{cheaper_than:.1f}%" if cheaper_than >= 99
                    else f"{cheaper_than:.0f}%")

    if as_deep_pct <= 15.0:
        reason = (f"This dip is in the {rank_text} of 22 years of history — deeper than "
                  f"{cheaper_text} of all trading days ever. Of the times it happened, "
                  f"gold dropped another 5% within 30 days only {prob_further_5:.0f}% of "
                  f"the time ({100 - prob_further_5:.0f}% of the time it was the bottom "
                  f"or close). Waiting for a deeper dip historically missed the entry.")
        return "ACT NOW", reason

    if as_deep_pct <= 30.0:
        reason = (f"Moderately rare dip ({rank_text}). Further 5% drops within 30 days "
                  f"happened {prob_further_5:.0f}% of the time, so "
                  f"{100 - prob_further_5:.0f}% of the time this was close to the bottom. "
                  f"Lean toward buying; waiting for a deeper dip is often disappointed.")
        return "LEAN BUY", reason

    if prob_further_5 > 40:
        reason = (f"This dip is common ({as_deep_pct:.0f}% of days were this deep or deeper). "
                  f"Further 5% drops within 30 days happened {prob_further_5:.0f}% of the "
                  f"time — waiting for a deeper entry is historically justified.")
        return "PATIENT WAIT", reason

    reason = (f"Common dip ({as_deep_pct:.0f}% of days were this deep or deeper). "
              f"Further 5% drops happened {prob_further_5:.0f}% of the time — "
              f"not strong enough either way. Your call.")
    return "CONSIDER", reason


def format_rarity_block(analysis: dict) -> str:
    """One-paragraph plain-English block for the alert email."""
    if analysis.get("observations", 0) == 0:
        return ""
    dd = analysis["current_dd_pct"]
    as_deep_pct = analysis["as_deep_pct"]
    as_deep_count = analysis["as_deep_count"]
    total = analysis["observations"]
    verdict = analysis["verdict"]
    reason = analysis["verdict_reason"]
    cond_30 = analysis["conditional"].get("30d", {})
    cond_90 = analysis["conditional"].get("90d", {})
    p5_30 = cond_30.get("5")
    p10_30 = cond_30.get("10")
    p5_90 = cond_90.get("5")
    detail_lines = []
    if p5_30 is not None:
        detail_lines.append(f"Dropped another 5% within 30 days: <b>{p5_30:.0f}%</b> of the time")
    if p10_30 is not None:
        detail_lines.append(f"Dropped another 10% within 30 days: <b>{p10_30:.0f}%</b> of the time")
    if p5_90 is not None:
        detail_lines.append(f"Dropped another 5% within 90 days: <b>{p5_90:.0f}%</b> of the time")
    detail = " · ".join(detail_lines)
    return (
        f"<b>How rare is this dip in 22 years of data?</b> "
        f"Today you are {abs(dd):.1f}% below the 90-day peak. "
        f"Only <b>{as_deep_pct:.1f}%</b> of all trading days ({as_deep_count:,} out of "
        f"{total:,}) had a dip this deep or deeper.<br><br>"
        f"<b>When it happened historically:</b> {detail}.<br><br>"
        f"<b>Verdict: {verdict}.</b> {reason}"
    )


# --------------------------------------------------------------------------
# Local bottom detector — complements the dip-depth tiers by catching the
# TURN. The depth tiers answer "how far below the peak?"; this answers
# "was yesterday the floor and is the market starting to rise?"
#
# Two signal flavors:
#   watchpoint — today's close is the lowest in the last `window` days.
#                The floor may be being set right now. Fires same evening.
#   confirmed  — yesterday's close was the window low AND today's close
#                is higher by at least `bounce_min_pct`. The bottom is
#                behind us; the window to catch the absolute low has
#                closed, but we're still within the bounce.
# --------------------------------------------------------------------------

LOCAL_BOTTOM_WINDOW = 20
LOCAL_BOTTOM_BOUNCE_MIN_PCT = 0.3     # smallest bounce that counts as a turn
LOCAL_BOTTOM_FWD_WINDOWS = (7, 30, 90)


@lru_cache(maxsize=4)
def _precompute_local_bottom_stats(window: int = LOCAL_BOTTOM_WINDOW) -> dict:
    """Over 22 years, measure what happened after every N-day low.

    Returns a dict:
      {
        'observations': int,         # historical days = N-day low
        'confirmed_observations': int,  # subset where next-day closed higher
        'watchpoint': { '7': {hit_rate, median_return}, ... },
        'confirmed':  { '7': {hit_rate, median_return}, ... },
      }
    """
    df = _fetch_gold_history().copy().sort_values("ds").reset_index(drop=True)
    df["rolling_min"] = df["price"].rolling(window, min_periods=window).min()
    df["is_n_day_low"] = df["price"] == df["rolling_min"]
    lows = df[df["is_n_day_low"]].copy()

    prices = df.set_index("ds")["price"]

    watch_rows = []
    conf_rows = []
    for idx, row in lows.iterrows():
        ds_val = row["ds"]
        p = row["price"]
        # Forward slice (excluding today itself)
        fwd = prices.loc[ds_val:].iloc[1:]
        if len(fwd) == 0:
            continue
        forward_returns = {}
        for h in LOCAL_BOTTOM_FWD_WINDOWS:
            w = fwd.iloc[:h]
            if len(w) == 0:
                forward_returns[h] = None
            else:
                # Return at the END of the horizon (not max/min) — we
                # want "where did price sit N days later", not "did it
                # ever cross up/down". A bounce that reverses within the
                # window should count against the signal.
                forward_returns[h] = (float(w.iloc[-1]) / p - 1) * 100
        watch_rows.append(forward_returns)

        # Confirmed: next-day close > this day's close by the threshold
        if len(fwd) >= 1:
            next_close = float(fwd.iloc[0])
            bounce = (next_close / p - 1) * 100
            if bounce >= LOCAL_BOTTOM_BOUNCE_MIN_PCT:
                conf_rows.append(forward_returns)

    def summarize(rows):
        out = {}
        for h in LOCAL_BOTTOM_FWD_WINDOWS:
            vals = [r[h] for r in rows if r.get(h) is not None]
            if not vals:
                out[str(h)] = {"hit_rate": None, "median_return": None, "n": 0}
                continue
            hit = sum(1 for v in vals if v > 0) / len(vals) * 100
            med = sorted(vals)[len(vals) // 2]
            out[str(h)] = {
                "hit_rate": hit,
                "median_return": med,
                "n": len(vals),
            }
        return out

    return {
        "observations": len(watch_rows),
        "confirmed_observations": len(conf_rows),
        "watchpoint": summarize(watch_rows),
        "confirmed": summarize(conf_rows),
    }


def local_bottom_analysis(history_df: pd.DataFrame,
                          window: int = LOCAL_BOTTOM_WINDOW,
                          bounce_min_pct: float = LOCAL_BOTTOM_BOUNCE_MIN_PCT) -> dict:
    """Detect whether today or yesterday posted a new N-day low.

    Args:
      history_df: DataFrame with columns (ds, price), sorted ascending by
        date. The LAST row is treated as "today".
      window: lookback length in trading days.
      bounce_min_pct: minimum next-day bounce (positive pct) that counts
        as confirming yesterday's low.

    Returns a dict (or None if not enough history):
      {
        'signal': 'confirmed' | 'watchpoint' | None,
        'window': int,
        'low_date': str,       # ISO date of the N-day low
        'low_price': float,
        'today_price': float,
        'bounce_pct': float,   # positive % from low to today (confirmed only)
        'historical': {        # from _precompute_local_bottom_stats
            'observations': int, 'hit_rate_30d': float,
            'median_return_30d': float, ...
        },
      }
    """
    if len(history_df) < window + 2:
        return None
    df = history_df.sort_values("ds").reset_index(drop=True)
    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    # Window for yesterday's N-day-low test = the `window` closes ending with
    # yesterday (inclusive). For today's test = closes ending with today.
    yest_window = df.iloc[-(window + 1):-1]["price"]
    today_window = df.iloc[-window:]["price"]

    signal = None
    low_date = None
    low_price = None
    bounce_pct = 0.0

    # Confirmed takes priority — it's the stronger signal.
    if (yesterday["price"] <= yest_window.min()
            and today["price"] > yesterday["price"]):
        bp = (float(today["price"]) / float(yesterday["price"]) - 1) * 100
        if bp >= bounce_min_pct:
            signal = "confirmed"
            low_date = yesterday["ds"].date().isoformat() \
                if hasattr(yesterday["ds"], "date") else str(yesterday["ds"])
            low_price = float(yesterday["price"])
            bounce_pct = bp

    if signal is None and today["price"] <= today_window.min():
        signal = "watchpoint"
        low_date = today["ds"].date().isoformat() \
            if hasattr(today["ds"], "date") else str(today["ds"])
        low_price = float(today["price"])

    if signal is None:
        return None

    stats = _precompute_local_bottom_stats(window=window)
    bucket = stats[signal]  # 'confirmed' or 'watchpoint'
    return {
        "signal": signal,
        "window": window,
        "low_date": low_date,
        "low_price": low_price,
        "today_price": float(today["price"]),
        "bounce_pct": bounce_pct,
        "historical": {
            "observations": stats["observations"] if signal == "watchpoint"
                              else stats["confirmed_observations"],
            "hit_rate_30d": bucket["30"]["hit_rate"],
            "median_return_30d": bucket["30"]["median_return"],
            "hit_rate_7d": bucket["7"]["hit_rate"],
            "median_return_7d": bucket["7"]["median_return"],
        },
    }


def format_local_bottom_block(analysis: dict) -> str:
    """One-paragraph HTML block for the alert email."""
    if not analysis:
        return ""
    sig = analysis["signal"]
    window = analysis["window"]
    low_date = analysis["low_date"]
    low_price = analysis["low_price"]
    today_price = analysis["today_price"]
    bounce = analysis["bounce_pct"]
    hist = analysis["historical"]
    n = hist["observations"]
    hit30 = hist["hit_rate_30d"]
    med30 = hist["median_return_30d"]

    stats_line = ""
    if hit30 is not None and med30 is not None:
        stats_line = (
            f"Historically, {hit30:.0f}% of these were positive 30 days later "
            f"(median return <b>{med30:+.1f}%</b>, n={n}).")

    if sig == "confirmed":
        return (
            f"<b>Local bottom confirmed.</b> Yesterday's close "
            f"(${low_price:,.0f} on {low_date}) was the lowest in {window} "
            f"trading days. Today's close of ${today_price:,.0f} is "
            f"<b>{bounce:+.2f}%</b> above that — the floor is behind you. "
            f"{stats_line} "
            f"Acting in the next 1-2 sessions still captures most of the "
            f"discount; waiting risks the bounce running away."
        )
    # watchpoint
    return (
        f"<b>Watch — new {window}-day low posted today.</b> Today's close of "
        f"${today_price:,.0f} is the lowest in {window} trading days. "
        f"This may be the floor being set right now; the next session will "
        f"tell. {stats_line} "
        f"If tomorrow closes higher, the bounce is on and the entry window "
        f"starts closing fast."
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "local-bottom":
        print("Testing local-bottom stats...")
        s = _precompute_local_bottom_stats()
        print(f"\nTotal N-day lows over 22yr: {s['observations']}")
        print(f"Confirmed (bounce next day):  {s['confirmed_observations']}")
        for h in LOCAL_BOTTOM_FWD_WINDOWS:
            w = s["watchpoint"][str(h)]
            c = s["confirmed"][str(h)]
            print(f"  +{h}d — watchpoint: hit {w['hit_rate']:.1f}%, median {w['median_return']:+.2f}% "
                  f"| confirmed: hit {c['hit_rate']:.1f}%, median {c['median_return']:+.2f}%"
                  if w['hit_rate'] is not None and c['hit_rate'] is not None else f"  +{h}d — N/A")
        sys.exit(0)
    dd = float(sys.argv[1]) if len(sys.argv) > 1 else -8.0
    print(f"Testing rarity analysis for current drawdown = {dd}%")
    out = rarity_analysis(dd)
    print(f"\nObservations: {out['observations']}")
    print(f"Days at least this deep: {out['as_deep_count']} ({out['as_deep_pct']:.2f}%)")
    print(f"Conditional probabilities:")
    for horizon, row in out["conditional"].items():
        for drop, p in row.items():
            print(f"  P(additional {drop}% drop within {horizon}) = {p:.1f}%" if p is not None else f"  P(additional {drop}% drop within {horizon}) = N/A")
    print(f"\nVerdict: {out['verdict']}")
    print(f"Reason:  {out['verdict_reason']}")
