# Daily Automation Guide

Complete guide for setting up and running MarketPulse daily automation.

---

## 🚀 Quick Start

### Run Daily Update (One Command)

```bash
./daily_update.sh
```

This single command does everything:
1. ✅ Runs inference pipeline (40 seconds)
2. ✅ Logs predictions to `DAILY_PREDICTIONS.md`
3. ✅ Captures dashboard screenshot
4. ✅ Commits and pushes to GitHub

---

## 📋 What Happens Automatically

### Step 1: Inference Pipeline
- Fetches 22 economic indicators (FRED, Yahoo Finance)
- Forecasts raw features 10 days ahead (NBEATSx + NHITS + PatchTST ensemble)
- Engineers 294 features from forecasts
- Predicts market regimes using Random Forest (98.4% accuracy)
- Validates forecasts (SMAPE metric)
- Detects regime shift alerts
- Stores results in BigQuery

**Time**: ~40 seconds
**Output**: `outputs/inference/regime_predictions_YYYYMMDD_HHMMSS.parquet`

### Step 2: Predictions Logging
- Loads latest regime predictions from BigQuery
- Generates markdown log entry with:
  - Timestamp
  - Forecast period
  - Regime distribution
  - Daily predictions table
- Appends to `DAILY_PREDICTIONS.md`

**Time**: ~2 seconds
**Output**: `DAILY_PREDICTIONS.md` (updated)

### Step 3: Dashboard Screenshot
- Starts Streamlit dashboard (if not running)
- Waits for initialization
- Captures full-page screenshot using Playwright
- Saves with timestamp
- Stops dashboard (if started by script)

**Time**: ~10-15 seconds
**Output**: `dashboard_screenshots/dashboard_YYYYMMDD_HHMMSS.png`

### Step 4: README Update
- Extracts latest forecast date
- Updates README metrics section (if exists)

**Time**: <1 second

### Step 5: Git Sync
- Stages all changes (`git add -A`)
- Creates commit with:
  - Daily timestamp
  - Latest forecast info
  - Validation metrics
- Pushes to GitHub (`git push origin main`)

**Time**: ~5 seconds
**Output**: GitHub repository updated

---

## ⚙️ Setup Instructions

### Prerequisites

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Install Playwright (for screenshots):**
```bash
playwright install chromium
```

3. **Make script executable:**
```bash
chmod +x daily_update.sh
```

### Manual Test Run

Test the full automation:

```bash
./daily_update.sh
```

Expected output:
```
================================================================================
📊 MarketPulse Daily Automation
Started: [timestamp]
================================================================================

[1/5] Running inference pipeline...
✅ Models ready! Running inference workflow...
[... inference output ...]

[2/5] Logging daily predictions...
✅ Logged 11 predictions to DAILY_PREDICTIONS.md

[3/5] Capturing dashboard screenshot...
🚀 Starting dashboard...
⏳ Waiting for dashboard to initialize...
✅ Screenshot saved: dashboard_screenshots/dashboard_[timestamp].png
🛑 Stopping dashboard...

[4/5] Updating README with latest metrics...
✅ Latest forecast: December 29, 2025

[5/5] Committing and pushing to GitHub...
✅ Changes committed and pushed to GitHub

================================================================================
✅ Daily automation complete!
================================================================================
```

---

## 🕐 Automated Scheduling

### Option 1: Cron (Linux/Mac)

Run daily at 6 AM:

```bash
# Open crontab editor
crontab -e

# Add this line
0 6 * * * cd /path/to/RFP && ./daily_update.sh >> logs/daily_automation.log 2>&1
```

### Option 2: Manual Daily Run

Simply run when needed:

```bash
cd /path/to/RFP
./daily_update.sh
```

---

## 📁 Output Files

### Files Updated Daily

| File | Description | Tracked in Git? |
|------|-------------|-----------------|
| `DAILY_PREDICTIONS.md` | Prediction log with regime forecasts | ✅ Yes |
| `dashboard_screenshots/dashboard_*.png` | Dashboard screenshots | ✅ Yes |
| `outputs/inference/regime_predictions_*.parquet` | Raw predictions | ❌ No (in .gitignore) |
| `outputs/model_performance_log.jsonl` | Validation metrics | ❌ No (in .gitignore) |
| `logs/daily_automation.log` | Script execution log | ❌ No (in .gitignore) |

### Git Commits

Each daily run creates a commit like:

```
Daily update 2025-12-22

- Regime predictions for next 10 days
- Latest forecast: December 29, 2025
- Dashboard updated with current market data
- Validation metrics: 11 days forecasted
```

---

## 🔧 Manual Workflow (Without Automation)

Run each step manually:

```bash
# 1. Inference
python run_daily_update.py

# 2. Log predictions
python log_daily_predictions.py

# 3. Capture screenshot (start dashboard first)
streamlit run dashboard/app.py  # In separate terminal
python capture_dashboard_screenshot.py

# 4. View results
cat DAILY_PREDICTIONS.md
ls dashboard_screenshots/

# 5. Manual git commit
git add -A
git commit -m "Daily update $(date +%Y-%m-%d)"
git push origin main
```

---

## 🐛 Troubleshooting

### Issue: "Permission denied: ./daily_update.sh"

**Solution:**
```bash
chmod +x daily_update.sh
```

### Issue: Screenshot capture fails

**Cause**: Playwright not installed or dashboard not accessible

**Solution:**
```bash
# Install Playwright
playwright install chromium

# Check dashboard manually
streamlit run dashboard/app.py
# Visit http://localhost:8501 in browser
```

### Issue: Git push fails

**Cause**: No remote configured or authentication issue

**Solution:**
```bash
# Check remote
git remote -v

# Add remote if missing
git remote add origin https://github.com/yourusername/RFP.git

# Configure credentials (GitHub CLI)
gh auth login
```

### Issue: "No changes to commit"

**Cause**: Script already ran today, no new predictions

**Solution:** This is normal. The system only generates new predictions when data changes.

---

## 📊 Monitoring System Health

### Check Latest Run

```bash
# View automation log
tail -n 50 logs/daily_automation.log

# Check latest predictions
tail -n 30 DAILY_PREDICTIONS.md

# View latest screenshot
ls -lt dashboard_screenshots/ | head -5
```

### Check Model Status

```bash
# View model age and status
python orchestrator/model_checker.py

# Check validation metrics
tail outputs/model_performance_log.jsonl
```

### Check Git Status

```bash
# View recent commits
git log --oneline -5

# Check if local is synced with remote
git status
```

---

## ⚡ Performance

Typical execution times:

| Step | Time | Notes |
|------|------|-------|
| Inference | ~40s | Forecasts 18 features × 10 days |
| Predictions Log | ~2s | Reads from BigQuery |
| Screenshot | ~15s | Includes dashboard startup |
| README Update | <1s | Extracts metadata |
| Git Push | ~5s | Depends on connection |
| **Total** | **~60s** | Full automation |

---

## 🎯 Best Practices

1. **Run at same time daily** - Use cron for consistency
2. **Monitor logs** - Check `logs/daily_automation.log` weekly
3. **Review predictions** - Check `DAILY_PREDICTIONS.md` for regime changes
4. **Verify screenshots** - Ensure dashboard rendering correctly
5. **Check GitHub** - Confirm commits are pushing successfully

---

## 🔒 Security Notes

### Excluded from Git

The following are **NOT** tracked in git (see `.gitignore`):

- `outputs/` directory (model outputs, parquet files)
- BigQuery credentials (`*credentials*.json`)
- Log files (`*.log`, `*.jsonl`)
- Model files (`*.pkl`, `*.pth`)

### Tracked in Git

The following **ARE** tracked:

- `DAILY_PREDICTIONS.md` - Daily predictions log
- `dashboard_screenshots/` - Dashboard screenshots
- All Python source code
- Configuration files

---

## 📞 Support

For issues or questions:

1. Check this guide
2. Review `logs/daily_automation.log`
3. Run manual workflow to isolate issues
4. Check GitHub Issues for similar problems

---

**System Status**: ✅ Production Ready
**Last Updated**: December 22, 2025
**Automation Tested**: ✅ All steps working
