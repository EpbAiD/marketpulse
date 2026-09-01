# Gold Dip Alert — Setup

## What This Is

Daily-scheduled email alert system that monitors gold-futures prices
(`GC=F`) and notifies recipients when historically-validated dip
conditions are met. Four alert tiers, all anchored to 21 years of
walk-forward analysis in [gold_dip_threshold_research.py](../scripts/diagnostics/gold_dip_threshold_research.py).

## What You Get

Roughly 5-6 emails per year across four tiers:

| Tier | Window | Trigger | Expected freq | Meaning |
|---|---|---|---|---|
| Seasonal buy | Jan-Feb | -3% dip from 20d high | ~1.5x/yr | Primary buying signal |
| Seasonal deadline | Feb 28 | Only if seasonal never fired | rare | Buy at market to keep seasonal edge |
| Opportunistic | Mar-Dec | -5% dip from 20d high | ~3x/yr | Out-of-season entry; quarter-conditional framing |
| Major | Any | -10% dip from 20d high | ~0.7x/yr | Quarter-conditional: STRONG BUY (Q1/Q4), WARNING (Q2), USE JUDGMENT (Q3) |

## Setup (One-Time)

### 1. Add Recipients

Edit [configs/gold_alert_recipients.yaml](../configs/gold_alert_recipients.yaml).
Every email listed receives every alert (unless the recipient sets a `tiers` filter).
Add as many as you want — no code change needed.

### 2. Generate A Gmail App Password

The workflow sends emails via Gmail SMTP. To do that you need an **App
Password** (not your regular Gmail password — Gmail blocks regular
passwords for SMTP).

- Go to [https://myaccount.google.com/security](https://myaccount.google.com/security)
- Enable **2-Step Verification** on your Gmail account (required to
  create app passwords)
- Under "Signing in to Google" pick **App passwords**
- Generate a new one; name it "MarketPulse gold alerts"
- Copy the 16-character string that appears (spaces are optional)

### 3. Add Secrets To GitHub

In the repo on GitHub, go to **Settings → Secrets and variables →
Actions → New repository secret**, and add these two:

- `GMAIL_SENDER_EMAIL` — the Gmail address the alerts are sent *from*
  (usually your own Gmail address)
- `GMAIL_APP_PASSWORD` — the 16-character app password from step 2

Once both secrets exist, the workflow will start sending on its next
scheduled run.

### 4. Manually Trigger A Test

To confirm end-to-end delivery before waiting for the next scheduled
run, trigger the workflow manually:

- On GitHub → **Actions** tab → **Gold Dip Alert** → **Run workflow** → Run

If no alerts fire today (most days won't), the workflow will log
"No alerts triggered today" and exit successfully — that's normal.

To force-test an actual alert delivery, temporarily lower one of the
thresholds in [scripts/gold_dip_alerts.py](../scripts/gold_dip_alerts.py)
(e.g. change `OPPORTUNISTIC_DIP_PCT` from 5.0 to 1.0), run the
workflow manually, confirm email delivery, then revert the threshold.

## Local Testing

Before pushing changes, dry-run the script locally:

```bash
python scripts/gold_dip_alerts.py --dry-run
```

Dry-run prints what would be sent but does not send email, does not
touch the state file, and does not require Gmail credentials to be set.

## How Duplicate Suppression Works

State is tracked per-year in
`outputs/alerts/gold_alert_state.json`. Rules:

- **Seasonal buy** fires *once per year*. If it fires on Jan 15, it
  will not fire again in Feb.
- **Seasonal deadline** fires *once per year*, and only if the
  seasonal buy never fired.
- **Opportunistic** fires at most once per 30 days.
- **Major** fires at most once per 30 days.

The workflow commits the state file back to the repo after each run,
so tomorrow's run knows what already fired.

## How To Adjust

- **Change alert thresholds**: edit the constants at the top of
  [scripts/gold_dip_alerts.py](../scripts/gold_dip_alerts.py)
  (`SEASONAL_DIP_PCT`, `OPPORTUNISTIC_DIP_PCT`, `MAJOR_DIP_PCT`).
- **Change the schedule**: edit the cron in
  [.github/workflows/gold-alert.yml](../.github/workflows/gold-alert.yml).
  Default is 22:15 UTC (safely after US market close).
- **Add / remove recipients**: edit `configs/gold_alert_recipients.yaml`.
  Every entry needs at least an `email`; `name` and `tiers` are optional.

## Why These Thresholds

Full statistical justification for the four thresholds is in
[gold_dip_threshold_research.py](../scripts/diagnostics/gold_dip_threshold_research.py).
Short version:

- **-3% seasonal**: fires in 100% of years within Q1, catches the
  seasonal-low + intra-quarter dip stacking effect (5-8% total discount
  vs yearly avg on average)
- **-5% opportunistic**: beats waiting-for-next-Q1 in 58% of cases,
  fires ~3x/year outside Q1 — actionable frequency
- **-10% major**: rare (0.7x/yr) and quarter-conditional — Q4 events
  have 100% historical recovery rate; Q2 events have 50% recovery
  rate and include famous bear-market starts (Apr 2008, Apr 2013),
  so the alert framing differs by quarter
