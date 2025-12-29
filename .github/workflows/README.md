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

**Runtime:** ~5-10 minutes
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

### If Using Local Files (No BigQuery):

No additional setup needed! Workflows are ready to use.

### If Using BigQuery:

1. **Create Service Account:**
   - Go to Google Cloud Console
   - IAM & Admin → Service Accounts
   - Create service account with BigQuery access
   - Create and download JSON key

2. **Add Secret to GitHub:**
   - Go to: `https://github.com/EpbAiD/marketpulse/settings/secrets/actions`
   - Click "New repository secret"
   - Name: `GCP_CREDENTIALS`
   - Value: Paste entire JSON content
   - Click "Add secret"

3. **Uncomment in workflows:**
   - Edit `daily-forecast.yml` and `manual-retrain.yml`
   - Uncomment the line: `GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}`

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
- Daily forecast: 5 min × 30 days = 150 min/month
- Tests: 2 min × 20 commits = 40 min/month
- Monthly retrain: 90 min × 1 = 90 min/month
- **Total:** ~280 minutes/month

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

**Last Updated:** December 27, 2024
**Status:** ✅ Ready to use
**Cost:** $0/month
