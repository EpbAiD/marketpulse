# GitHub Actions Workflows

This directory contains automated workflows for the MarketPulse project.

## Available Workflows

### 1. Daily Market Regime Forecast (`daily-forecast.yml`)

**Trigger:** Runs automatically every day at 6 AM UTC

**What it does:**
- Executes the full inference pipeline
- Generates regime predictions for next 10 trading days
- Updates `DAILY_PREDICTIONS.md`
- Captures dashboard screenshot
- Commits results to GitHub
- Uploads artifacts for 7 days

**Manual run:**
1. Go to Actions tab
2. Select "Daily Market Regime Forecast"
3. Click "Run workflow"

**Runtime:** ~10-15 minutes (includes Streamlit + screenshot)
**Cost:** FREE (well under 2,000 min/month limit)

---

### 2. Manual Model Retraining (`manual-retrain.yml`)

**Trigger:** Manual only (not scheduled)

**What it does:**
- Runs complete training pipeline
- Fetches latest data
- Engineers features
- Trains all models (forecasters, classifier, clustering)
- Uploads model artifacts (90 day retention)
- Uploads diagnostics (30 day retention)

**How to run:**
1. Go to Actions tab
2. Select "Manual Model Retraining"
3. Click "Run workflow"
4. Optionally add reason (e.g., "Performance degradation")
5. Click "Run workflow"

**Runtime:** ~60-90 minutes
**Cost:** FREE (occasional runs, well under limit)

---

### 3. Tests (`tests.yml`)

**Trigger:** On every push or pull request to `main`

**What it does:**
- Lints Python code with flake8
- Validates project structure
- Checks Python imports
- Runs pytest (if tests exist)
- Provides code coverage report

**Manual run:**
1. Go to Actions tab
2. Select "Tests"
3. Click "Run workflow"

**Runtime:** ~2-3 minutes
**Cost:** FREE

---

## Setup Instructions

### ⚠️ REQUIRED: BigQuery Credentials

**This project uses BigQuery for data storage. You MUST configure credentials before running workflows.**

#### Step 1: Get Your Credentials File

Your local BigQuery credentials are at:
```
regime01-*.json
```

View the contents:
```bash
cat regime01-*.json
```

Copy the **entire JSON output** (you'll need it in Step 2).

#### Step 2: Add Secret to GitHub

1. **Go to GitHub Secrets page:**
   ```
   https://github.com/EpbAiD/marketpulse/settings/secrets/actions
   ```

2. **Create new secret:**
   - Click "New repository secret"
   - **Name:** `GCP_CREDENTIALS` (exact name, case-sensitive)
   - **Value:** Paste the entire JSON file contents from Step 1
   - Click "Add secret"

3. **Verify secret added:**
   - You should see `GCP_CREDENTIALS` in the list of secrets
   - The value will be hidden (shows as `***`)

#### Step 3: Verify Setup

✅ **No code changes needed!** Workflows are already configured to use this secret.

The workflows will automatically:
- Load `GCP_CREDENTIALS` secret
- Create temporary credentials file at `/tmp/gcp_credentials.json`
- Set `GOOGLE_APPLICATION_CREDENTIALS` environment variable
- Connect to BigQuery using these credentials

---

### Additional Dependencies (Auto-Installed)

The workflows automatically install:
- ✅ **Playwright** - For dashboard screenshot capture
- ✅ **Chromium browser** - For rendering dashboard
- ✅ **Streamlit** - For dashboard server (runs in background)

No manual configuration required for these.

---

## Monitoring

### View Workflow Runs:
```
https://github.com/EpbAiD/marketpulse/actions
```

### Check Logs:
1. Click on any workflow run
2. Expand job steps
3. View detailed logs

### Download Artifacts:
1. Go to completed workflow run
2. Scroll to "Artifacts" section
3. Download forecasts, models, or diagnostics

---

## Costs

**Current usage estimate:**
- Daily forecast: 12 min × 30 days = 360 min/month (includes Streamlit + Playwright)
- Tests: 2 min × 20 commits = 40 min/month
- Monthly retrain: 90 min × 1 = 90 min/month
- **Total:** ~490 minutes/month

**Free tier:** 2,000 minutes/month (private repo) or unlimited (public)

**Your cost:** $0 (well under limit)

---

## Troubleshooting

### Workflow not running:
- Check if workflows are enabled in Settings → Actions
- Verify cron schedule is correct
- Check workflow file syntax (YAML validation)

### Workflow failing:
- Check logs in Actions tab
- Verify dependencies install correctly
- Ensure BigQuery credentials are valid (if used)

### Commits not pushing:
- Verify GITHUB_TOKEN has write permissions
- Check if branch protection rules block bot commits

---

## Customization

### Change schedule:
Edit `cron` expression in `daily-forecast.yml`:
```yaml
schedule:
  - cron: '0 6 * * *'  # 6 AM UTC
  # Format: minute hour day month weekday
```

Examples:
- `'0 6 * * *'` - 6 AM UTC daily
- `'0 */6 * * *'` - Every 6 hours
- `'0 6 * * 1-5'` - 6 AM weekdays only

### Add email notifications:
Settings → Notifications → Actions → Email on failure

### Disable workflow:
Comment out entire file or delete it

---

## Best Practices

✅ **Do:**
- Use secrets for credentials
- Set reasonable timeouts
- Upload artifacts for debugging
- Add descriptive commit messages
- Monitor workflow runs

❌ **Don't:**
- Hardcode credentials
- Run expensive operations frequently
- Store large files in artifacts
- Commit generated files to main branch

---

**Last Updated:** December 29, 2025
**Status:** ⚠️ REQUIRES SETUP - Add `GCP_CREDENTIALS` secret first
**Cost:** $0/month
