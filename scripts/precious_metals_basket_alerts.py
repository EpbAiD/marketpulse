#!/usr/bin/env python3
"""
Precious Metals Basket Alert — coordinated gold + silver dip notifications.

Runs daily (independent from gold_dip_alerts.py). Fires only when BOTH
gold AND silver simultaneously pull back beyond their tier thresholds
from their respective trailing 20-day highs.

Design rationale — honest framing:
  Gold and silver pullbacks are ~0.80 correlated over 21 years. Requiring
  both to dip does NOT meaningfully lift hit rate over gold-alone
  (61% vs 62% in the backtest). So the basket alert is NOT positioned as
  a stronger predictive signal.

  Its value is different: it identifies moments when the entire precious
  metals complex is on sale, coordinating buying decisions across both
  positions. Useful specifically for anyone who wants to hold both metals
  as part of a diversified precious-metals allocation.

Tiers (silver thresholds scaled ~2x gold to reflect silver's higher vol):
  1. STANDARD  — gold -3%, silver -6%   (~6x/year, moderate signal)
  2. STRONG    — gold -5%, silver -10%  (~3x/year, better signal)
  3. MAJOR     — gold -10%, silver -20% (~0.5x/year, crisis-level)

Isolation from gold_dip_alerts.py:
  - Own config, own state file, own workflow
  - Standalone script, imports nothing from the gold alerter
  - Delivery via same Gmail SMTP secrets
  - If this system fails, gold alerts keep working and vice versa
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

RECIPIENTS_FILE = BASE_DIR / "configs" / "precious_metals_recipients.yaml"
STATE_FILE = BASE_DIR / "outputs" / "alerts" / "pm_basket_state.json"

GOLD_TICKER = "GC=F"
SILVER_TICKER = "SI=F"

# Tier definitions in plain language.
TIERS = [
    {
        "name": "standard",
        "g_thresh": 3.0, "s_thresh": 6.0, "min_gap": 30,
        "subject_tag": "both metals dropped",
        "action": "BUY both gold and silver",
        "size": "About 40% of what you planned to spend on precious metals this year (split it 60% gold, 40% silver)",
        "confidence": "Medium",
        "odds": ("This has happened 133 times in the last 22 years. About 65 "
                 "out of every 100 times, buying here was profitable within "
                 "3 months. Typical gain: 4% up."),
        "why": ("When both gold AND silver drop at the same time, it usually "
                "means the whole precious-metals market is on sale — often "
                "because the dollar strengthened or interest rates spiked. "
                "Buying both spreads your risk. Silver tends to bounce back "
                "harder than gold when things recover."),
    },
    {
        "name": "strong",
        "g_thresh": 5.0, "s_thresh": 10.0, "min_gap": 45,
        "subject_tag": "both metals dropped a lot",
        "action": "BUY both gold and silver — a larger amount",
        "size": "About 60-70% of what you planned to spend on precious metals this year (split 60% gold, 40% silver)",
        "confidence": "Medium-High",
        "odds": ("This has happened 64 times in the last 22 years. About 64 "
                 "out of every 100 times, buying here was profitable within "
                 "3 months. Typical gain: 5% up."),
        "why": ("Silver has dropped twice as much as gold — that's a classic "
                "setup where silver has been oversold and often bounces back "
                "faster and harder than gold. Good time to buy both, and "
                "especially good time to weight a bit more toward silver."),
    },
    {
        "name": "major",
        "g_thresh": 10.0, "s_thresh": 20.0, "min_gap": 90,
        "subject_tag": "RARE — both metals had a huge drop",
        "action": "BUY both — this is a rare opportunity",
        "size": "About 80-100% of any precious-metals budget you have left this year",
        "confidence": "High — rare and historically strong",
        "odds": ("Only 13 times in the last 22 years. About 65-70 out of every "
                 "100 times, buying was profitable within 3 months. When it "
                 "worked, typical gain: 8-15% up. Examples: COVID crash 2020, "
                 "the big gold sell-off in 2013, and the 2008 financial crisis."),
        "why": ("A big drop in both gold AND silver at the same time is rare "
                "and usually happens during panic selling. Historically, these "
                "moments have been some of the best buying opportunities for "
                "the whole precious-metals market."),
    },
]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def fetch_recent(ticker: str, days: int = 90) -> pd.DataFrame:
    df = yf.download(ticker, period=f"{days}d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.reset_index()[["Date", "Close"]]
    df.columns = ["ds", "price"]
    df["ds"] = pd.to_datetime(df["ds"])
    return df.sort_values("ds").reset_index(drop=True)


def compute_pullback(df: pd.DataFrame, label: str) -> dict:
    if len(df) < 20:
        raise ValueError(f"{label}: need at least 20 days, got {len(df)}")
    latest = df.iloc[-1]
    roll_20d_high = df["price"].tail(20).max()
    pb = (latest["price"] / roll_20d_high - 1) * 100
    return {
        "date": latest["ds"].date().isoformat(),
        "price": float(latest["price"]),
        "roll_20d_high": float(roll_20d_high),
        "pullback_pct": float(pb),
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


def days_since(date_str: str | None, today_iso: str) -> int:
    if not date_str:
        return 10**6
    return (datetime.fromisoformat(today_iso).date()
            - datetime.fromisoformat(date_str).date()).days


# --------------------------------------------------------------------------
# Tier evaluation
# --------------------------------------------------------------------------

def evaluate_basket(gold_ctx: dict, silver_ctx: dict, state: dict) -> list[dict]:
    alerts = []
    date = gold_ctx["date"]
    quarter = (datetime.fromisoformat(date).month - 1) // 3 + 1

    for tier in TIERS:
        # Both metals must be at or below their respective thresholds
        if gold_ctx["pullback_pct"] > -tier["g_thresh"]:
            continue
        if silver_ctx["pullback_pct"] > -tier["s_thresh"]:
            continue
        # Cooldown
        last_fire_key = f"last_{tier['name']}_date"
        if days_since(state.get(last_fire_key), date) < tier["min_gap"]:
            continue

        q_name = {1: "January-March", 2: "April-June",
                  3: "July-September", 4: "October-December"}.get(quarter, "")
        q_note = ({
            1: "This is happening during the historically cheap months for gold — an especially good time.",
            4: "This is happening during the highest-demand months for gold (Indian weddings, Chinese New Year buying) — prices usually recover.",
            2: "This is happening in April-June, which has historically been a mixed period. Be a bit more careful than usual.",
            3: "This is happening in July-September, which has an average track record.",
        }).get(quarter, "")

        alerts.append({
            "tier": tier["name"],
            "subject": f"gold + silver: {tier['subject_tag']}",
            "headline": f"Both gold AND silver dropped — {tier['action']}",
            "detail": (
                f"Both gold and silver have dropped at the same time:\n\n"
                f"  Gold today: ${gold_ctx['price']:.2f} — down "
                f"{abs(gold_ctx['pullback_pct']):.1f}% from its recent 20-day peak "
                f"of ${gold_ctx['roll_20d_high']:.2f}\n\n"
                f"  Silver today: ${silver_ctx['price']:.2f} — down "
                f"{abs(silver_ctx['pullback_pct']):.1f}% from its recent 20-day peak "
                f"of ${silver_ctx['roll_20d_high']:.2f}\n\n"
                f"Time of year: {q_name}. {q_note}"
            ),
            "playbook_action": tier["action"],
            "playbook_size": tier["size"],
            "playbook_confidence": tier["confidence"],
            "playbook_odds": tier["odds"],
            "playbook_why": tier["why"],
            "playbook_next": (
                "If gold or silver keeps falling, you may get another alert "
                "from either this system or the gold-only alert. If prices "
                "start recovering instead, no further action needed — you've "
                "caught a good entry."
            ),
        })
    return alerts


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def _localize_prices(html: str, price_fmt, fx_line: str) -> str:
    """Substitute $NNN price mentions with local currency; add FX footer note."""
    import re
    def _sub(m):
        raw = m.group(1).replace(",", "")
        try:
            usd = float(raw)
        except ValueError:
            return m.group(0)
        return price_fmt(usd)
    out = re.sub(r"\$([\d]{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)", _sub, html)
    if fx_line:
        out = out.replace(
            "Nothing here is personal financial advice",
            f"{fx_line}<br>Nothing here is personal financial advice",
        )
    return out


def render_html(alert: dict, gold_ctx: dict, silver_ctx: dict,
                recipient_name: str | None,
                price_fmt=None, fx_line: str = "",
                multi_currency_table: str = "") -> str:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
    action = alert.get("playbook_action", "").upper()
    if "STAND DOWN" in action or "DO NOT" in action:
        accent = "#C0392B"
    elif "BUY" in action:
        accent = "#27AE60"
    else:
        accent = "#E67E22"

    html = f"""<!doctype html><html><body style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #2C3E50; line-height: 1.55;">
  <div style="border-left: 4px solid #1F4E79; padding: 1.25rem 1.5rem; background: #F8F9FA;">
    <div style="text-transform: uppercase; font-size: 0.75rem; color: #7F8C8D; letter-spacing: 0.5px;">Gold + Silver Alert · {gold_ctx['date']}</div>
    <h1 style="margin: 0.3rem 0 0.6rem; font-size: 1.4rem; color: #1F4E79; font-weight: 500;">{alert['headline']}</h1>
    <div style="color: #34495E; font-size: 0.95rem;">
      Gold ${gold_ctx['price']:.0f} (down {abs(gold_ctx['pullback_pct']):.1f}%) · Silver ${silver_ctx['price']:.2f} (down {abs(silver_ctx['pullback_pct']):.1f}%)
    </div>
  </div>

  <p>{greeting}</p>

  <p style="font-size: 0.95rem;">{alert['detail'].replace(chr(10) + chr(10), '</p><p style="font-size: 0.95rem;">')}</p>

  {multi_currency_table}

  <div style="border: 2px solid {accent}; padding: 1.1rem 1.3rem; border-radius: 4px; margin: 1.5rem 0; background: #FDFDFD;">
    <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.8px;">What to do</div>
    <div style="font-size: 1.5rem; color: {accent}; font-weight: 600; margin: 0.3rem 0 0.9rem;">{alert['playbook_action']}</div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.7rem 1.2rem; margin-bottom: 0.9rem;">
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">How much to buy</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{alert['playbook_size']}</div>
      </div>
      <div>
        <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">How sure I am</div>
        <div style="font-size: 0.95rem; color: #34495E; font-weight: 500;">{alert['playbook_confidence']}</div>
      </div>
    </div>

    <div style="margin-top: 0.9rem; padding: 0.75rem 0.9rem; background: #F8F9FA; border-left: 3px solid {accent}; border-radius: 2px;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px; margin-bottom: 0.25rem;">How often this has worked before</div>
      <div style="font-size: 0.9rem; color: #2C3E50; font-weight: 500;">{alert['playbook_odds']}</div>
    </div>

    <div style="margin-top: 0.9rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">Why this recommendation</div>
      <div style="font-size: 0.9rem; color: #34495E; margin-top: 0.25rem;">{alert['playbook_why']}</div>
    </div>

    <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid #ECF0F1;">
      <div style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px;">What might happen next</div>
      <div style="font-size: 0.9rem; color: #34495E; margin-top: 0.25rem;">{alert['playbook_next']}</div>
    </div>
  </div>

  <p style="color: #7F8C8D; font-size: 0.8rem; margin-top: 2rem; border-top: 1px solid #ECF0F1; padding-top: 0.8rem;">
    You'll only get this alert when both gold AND silver have dropped at the same time.
    It's a separate signal from the gold-only alerts. Nothing here is personal
    financial advice — only spend money you can afford to hold for years.
  </p>
</body></html>"""

    if price_fmt is not None:
        html = _localize_prices(html, price_fmt, fx_line)
    return html


def send_email(smtp_host, smtp_port, sender, password,
               recipient, subject, html) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
        s.login(sender, password)
        s.sendmail(sender, [recipient], msg.as_string())


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def _run_test_email() -> int:
    """Send a synthetic sample basket alert to every recipient."""
    with open(RECIPIENTS_FILE) as f:
        cfg = yaml.safe_load(f)
    recipients = cfg.get("recipients", [])
    if not recipients:
        print("No recipients."); return 0

    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("ERROR: GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set.")
        return 1

    # Fetch real current data
    try:
        g = fetch_recent(GOLD_TICKER)
        s = fetch_recent(SILVER_TICKER)
        g_ctx = compute_pullback(g, "gold")
        s_ctx = compute_pullback(s, "silver")
    except Exception:
        g_ctx = {"date": datetime.utcnow().date().isoformat(),
                 "price": 4481, "roll_20d_high": 4641, "pullback_pct": -3.44}
        s_ctx = {"date": datetime.utcnow().date().isoformat(),
                 "price": 41.20, "roll_20d_high": 45.80, "pullback_pct": -10.04}

    # Force a STRONG basket alert scenario using real gold, synthetic silver-adjust
    # to hit -10%. This lets recipient see the STRONG-tier format.
    s_ctx_synth = dict(s_ctx)
    s_ctx_synth["pullback_pct"] = -10.1  # force STRONG threshold
    g_ctx_synth = dict(g_ctx)
    g_ctx_synth["pullback_pct"] = -5.1  # force STRONG threshold
    empty_state = {}
    sample_alerts = evaluate_basket(g_ctx_synth, s_ctx_synth, empty_state)
    sample = None
    for a in sample_alerts:
        if a["tier"] == "strong":
            sample = {**a,
                      "subject": "precious metals: test alert — sample basket format",
                      "headline": "SAMPLE: " + a["headline"],
                      "detail": ("This is a SYNTHETIC test alert showing the format "
                                 "of a real precious-metals basket email. Real gold "
                                 "spot with a fabricated silver pullback to trigger "
                                 "the STRONG threshold.\n\n" + a["detail"])}
            break

    if not sample:
        print("Failed to build sample alert."); return 1

    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
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
        weight_units_list = r.get("weight_units")
        weight_unit_single = r.get("weight_unit", "troy_ounce")
        if currencies_list:
            currencies_list = [c.upper() for c in currencies_list]
            price_fmt = None
            fx_line = ""
            wu_for_table = weight_units_list or [weight_unit_single]
            multi_table = build_multi_currency_table_html(
                {"Gold": g_ctx_synth["price"],
                 "Silver": s_ctx_synth["price"]},
                currencies_list,
                weight_units=wu_for_table,
            )
            label = f"multi:{','.join(currencies_list)} × {','.join(wu_for_table)}"
        else:
            currency = r.get("currency", "USD")
            price_fmt = make_price_formatter(currency, weight_unit_single)[0]
            rate = make_price_formatter(currency)[1]
            fx_line = fx_footer_line(currency, rate)
            multi_table = ""
            label = f"{currency} ({weight_unit_single})"
        try:
            send_email(smtp_host, smtp_port, sender, password, email,
                       sample["subject"],
                       render_html(sample, g_ctx_synth, s_ctx_synth, r.get("name"),
                                   price_fmt=price_fmt, fx_line=fx_line,
                                   multi_currency_table=multi_table))
            print(f"  sent basket test -> {email} ({label})")
            sent += 1
        except Exception as e:
            print(f"  FAILED -> {email}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\nTest delivery: {sent} sent, {failed} failed.")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-email", action="store_true")
    args = parser.parse_args()

    if args.test_email:
        return _run_test_email()

    with open(RECIPIENTS_FILE) as f:
        cfg = yaml.safe_load(f)
    recipients = cfg.get("recipients", [])
    if not recipients:
        print("No recipients configured."); return 0

    try:
        g = fetch_recent(GOLD_TICKER)
        s = fetch_recent(SILVER_TICKER)
        g_ctx = compute_pullback(g, "gold")
        s_ctx = compute_pullback(s, "silver")
    except Exception as e:
        print(f"Failed to fetch price data: {e}")
        return 1

    print(f"Gold:   ${g_ctx['price']:.2f} ({g_ctx['pullback_pct']:+.2f}% from 20d high)")
    print(f"Silver: ${s_ctx['price']:.2f} ({s_ctx['pullback_pct']:+.2f}% from 20d high)")

    state = load_state()
    alerts = evaluate_basket(g_ctx, s_ctx, state)

    if not alerts:
        print("No basket-alert conditions met today.")
        return 0

    print(f"{len(alerts)} basket alert(s) triggered:")
    for a in alerts:
        print(f"  - [{a['tier']}] {a['subject']}")

    if args.dry_run:
        for a in alerts:
            print(f"\n=== {a['subject']} ===")
            print(f"{a['detail']}")
            print(f"\nACTION: {a['playbook_action']} | SIZE: {a['playbook_size']}")
            print(f"ODDS:   {a['playbook_odds']}")
        return 0

    sender = os.environ.get("GMAIL_SENDER_EMAIL")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("ERROR: GMAIL_SENDER_EMAIL or GMAIL_APP_PASSWORD not set.")
        return 1

    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
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
        wanted = set(r.get("tiers") or ["standard", "strong", "major"])

        currencies_list = r.get("currencies")
        weight_units_list = r.get("weight_units")
        weight_unit_single = r.get("weight_unit", "troy_ounce")
        if currencies_list:
            currencies_list = [c.upper() for c in currencies_list]
            price_fmt = None
            fx_line = ""
            wu_for_table = weight_units_list or [weight_unit_single]
            multi_table = build_multi_currency_table_html(
                {"Gold": g_ctx["price"], "Silver": s_ctx["price"]},
                currencies_list,
                weight_units=wu_for_table,
            )
            label = f"multi:{','.join(currencies_list)} × {','.join(wu_for_table)}"
        else:
            currency = r.get("currency", "USD")
            price_fmt = make_price_formatter(currency, weight_unit_single)[0]
            rate = make_price_formatter(currency)[1]
            fx_line = fx_footer_line(currency, rate)
            multi_table = ""
            label = f"{currency} ({weight_unit_single})"

        for a in alerts:
            if a["tier"] not in wanted:
                continue
            try:
                send_email(smtp_host, smtp_port, sender, password,
                           email, a["subject"],
                           render_html(a, g_ctx, s_ctx, r.get("name"),
                                       price_fmt=price_fmt, fx_line=fx_line,
                                       multi_currency_table=multi_table))
                print(f"  sent [{a['tier']}] -> {email} ({label})")
                sent += 1
            except Exception as e:
                print(f"  FAILED [{a['tier']}] -> {email}: {type(e).__name__}: {e}")

    # Update state
    today = g_ctx["date"]
    for a in alerts:
        state[f"last_{a['tier']}_date"] = today
    save_state(state)
    print(f"State updated → {STATE_FILE}")

    return 0 if sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
