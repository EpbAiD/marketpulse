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
        }
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

def evaluate_tiers(ctx: dict, year_st: dict) -> list[dict]:
    """Return the list of alerts that should fire today (0-2 typically)."""
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
            "subject": "gold: Q1 seasonal dip triggered",
            "headline": "Primary buying signal fired",
            "detail": (
                f"Gold pulled back {pb:.2f}% from its trailing 20-day high of "
                f"${ctx['roll_20d_high']:.0f} to today's close of ${ctx['price']:.0f}. "
                f"This is inside the Jan-Feb seasonal window where gold has "
                f"historically been ~3-5% cheaper than the yearly average, "
                f"and a -3% dip fires in most years. Combined discount vs "
                f"the typical yearly price: roughly 5-8%. This is the primary "
                f"entry point in the strategy."
            ),
            "action": (
                "This is a routine seasonal signal, not a rare event. "
                "Consider buying at market."
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
            "subject": "gold: Q1 seasonal window closing, no dip fired",
            "headline": "Seasonal deadline reminder",
            "detail": (
                f"Today is the last practical trading day of the Jan-Feb "
                f"seasonal buying window. No -3% dip triggered this year, "
                f"so the strategy defaults to buying at market to secure "
                f"the seasonal discount before Q2. Current close ${ctx['price']:.0f} "
                f"(pullback from 20d high: {pb:.2f}%)."
            ),
            "action": (
                "Consider buying at market. Waiting into Q2 historically "
                "costs ~2-5% because gold drifts up through the year and "
                "the seasonal edge disappears."
            ),
        })

    # Tier 3 — Opportunistic dip (out of season)
    if (month not in SEASONAL_MONTHS
            and pb <= -OPPORTUNISTIC_DIP_PCT
            and days_since(year_st["last_opportunistic_date"], date) >= OPPORTUNISTIC_MIN_GAP_DAYS):
        q_note = {
            2: "Caution: Q2 -5% dips have mixed history — sometimes a genuine buying opportunity, sometimes the start of a longer decline.",
            3: "Moderate signal — Q3 dips are historically middle-of-the-road.",
            4: "Historically strong — Q4 dips usually recover as Asian physical demand picks up.",
        }.get(q, "")
        alerts.append({
            "tier": "opportunistic",
            "subject": f"gold: -{OPPORTUNISTIC_DIP_PCT:.0f}% dip (Q{q}, out of season)",
            "headline": f"Opportunistic Q{q} dip",
            "detail": (
                f"Gold pulled back {pb:.2f}% from its trailing 20-day high "
                f"of ${ctx['roll_20d_high']:.0f} to today's close of "
                f"${ctx['price']:.0f}. This is outside the primary Jan-Feb "
                f"window, but historically -5% out-of-season dips beat "
                f"waiting for the next seasonal window 58% of the time.\n\n"
                f"{q_note}"
            ),
            "action": (
                "Weigh against your Q1 seasonal plan. If you have "
                "unallocated capital and this dip fits your risk budget, "
                "it's a defensible add. Not a strong-buy signal on its own."
            ),
        })

    # Tier 4 — Major dip (any time), quarter-conditional messaging
    if (pb <= -MAJOR_DIP_PCT
            and days_since(year_st["last_major_date"], date) >= MAJOR_MIN_GAP_DAYS):
        q_frame = {
            1: {"tag": "STRONG BUY",
                "note": ("Historically Q1 -10% dips recovered in 2 of 3 events with "
                         "a median +4.6% at 90 days. This is a rare event; treat as a "
                         "high-conviction add if it fits your allocation.")},
            2: {"tag": "WARNING",
                "note": ("Historically Q2 -10% dips have been dangerous: the April 2008 "
                         "and April 2013 events both marked the start of multi-year "
                         "gold bear markets. Only 2 of 4 Q2 events recovered, and the "
                         "failures were severe. Consider staying out or waiting for "
                         "the trend to confirm before adding.")},
            3: {"tag": "USE JUDGMENT",
                "note": ("Small historical sample (2 events) with mixed outcomes. "
                         "No strong statistical prior. Judge based on broader macro.")},
            4: {"tag": "STRONG BUY",
                "note": ("Historically Q4 -10% dips recovered in 4 of 4 events with "
                         "a median +8.3% at 90 days. Asian physical demand typically "
                         "kicks in through Q4, providing a mechanical bid. This is "
                         "one of the most reliable buying setups in the strategy.")},
        }[q]
        alerts.append({
            "tier": "major",
            "subject": f"gold: MAJOR -{MAJOR_DIP_PCT:.0f}% dip in Q{q} — {q_frame['tag']}",
            "headline": f"Major dip in Q{q}: {q_frame['tag']}",
            "detail": (
                f"Gold has fallen {pb:.2f}% from its trailing 20-day high "
                f"of ${ctx['roll_20d_high']:.0f} to today's close of "
                f"${ctx['price']:.0f}. Events of this magnitude fire roughly "
                f"once a year on average.\n\n{q_frame['note']}"
            ),
            "action": (
                "Q1/Q4 dips: consider a meaningful add if allocation "
                "allows. Q2 dips: exercise caution. Q3 dips: use your own "
                "read of the broader macro."
            ),
        })

    return alerts


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def render_html(alert: dict, ctx: dict, recipient_name: str | None) -> str:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
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

  <div style="background: #F8F9FA; padding: 0.9rem 1.1rem; border-radius: 3px; margin: 1.25rem 0;">
    <div style="text-transform: uppercase; font-size: 0.7rem; color: #7F8C8D; margin-bottom: 0.3rem;">Suggested framing</div>
    <div style="font-size: 0.95rem; color: #34495E;">{alert['action']}</div>
  </div>

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
    """Send a canned test alert to every recipient. Doesn't touch state, doesn't
    look at market data. Used to verify SMTP + secrets work before waiting for
    a real dip."""
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

    # Canned "test alert" using the same rendering pipeline as real alerts,
    # so recipients see exactly the visual style they'll get in production.
    test_alert = {
        "tier": "test",
        "subject": "gold: test alert (delivery check)",
        "headline": "Delivery test — you can ignore",
        "detail": (
            "This is a one-time test of the Gold Dip Alert system. If you "
            "received this, delivery is wired up correctly.\n\n"
            "You'll only receive real alerts when historically-validated "
            "buying conditions are met — roughly 5 to 6 emails per year."
        ),
        "action": "No action needed. This confirms the pipeline works.",
    }
    test_ctx = {
        "date": datetime.utcnow().date().isoformat(),
        "price": 0.0, "roll_20d_high": 0.0,
        "pullback_pct": 0.0, "quarter": 0, "month": 0,
    }

    sent, failed = 0, 0
    for r in recipients:
        email = r.get("email")
        if not email:
            continue
        try:
            send_email(smtp_host, smtp_port, sender, password,
                       email, test_alert["subject"],
                       render_html(test_alert, test_ctx, r.get("name")))
            print(f"  sent test -> {email}")
            sent += 1
        except Exception as e:
            print(f"  FAILED test -> {email}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\nTest delivery: {sent} sent, {failed} failed.")
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

    state = load_state()
    yr = datetime.fromisoformat(ctx["date"]).year
    yr_st = year_state(state, yr)

    alerts = evaluate_tiers(ctx, yr_st)

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
        wanted_tiers = set(r.get("tiers") or ["seasonal", "deadline", "opportunistic", "major"])
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
    save_state(state)
    print(f"State updated → {STATE_FILE}")

    return 0 if sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
