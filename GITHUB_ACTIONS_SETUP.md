# GitHub Actions Setup - Quick Start Guide

**Status:** ⚠️ ACTION REQUIRED
**Time to Complete:** 5 minutes
**Difficulty:** Easy

---

## What You Need to Do

Your GitHub Actions workflows are configured, but they **won't work** until you add BigQuery credentials as a GitHub Secret.

---

## Step-by-Step Setup

### Step 1: Copy Your Credentials (1 minute)

Open Terminal and run:

```bash
cat regime01-*.json
```

You'll see output like this:
```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "...",
  ...
}
```

**Copy the ENTIRE output** (all the JSON including the curly braces).

---

### Step 2: Add Secret to GitHub (2 minutes)

1. **Open GitHub Secrets page:**

   Click this link (or go manually):
   ```
   https://github.com/EpbAiD/marketpulse/settings/secrets/actions
   ```

2. **Create new secret:**
   - Click the green **"New repository secret"** button
   - **Name:** Type exactly: `GCP_CREDENTIALS`
   - **Value:** Paste the JSON you copied in Step 1
   - Click **"Add secret"**

3. **Verify:**
   - You should now see `GCP_CREDENTIALS` in the list
   - The value will show as `***` (hidden for security)

---

### Step 3: Test the Workflow (2 minutes)

1. **Go to Actions tab:**
   ```
   https://github.com/EpbAiD/marketpulse/actions
   ```

2. **Trigger manual run:**
   - Click on **"Daily Market Regime Forecast"** (left sidebar)
   - Click **"Run workflow"** (blue button on the right)
   - Select `main` branch
   - Click **"Run workflow"** (in the popup)

3. **Monitor the run:**
   - Click on the workflow run that appears
   - Watch it execute in real-time
   - Should complete in ~10-15 minutes

---

## What Will Happen

When the workflow runs, it will:

1. ✅ Checkout your code from GitHub
2. ✅ Install Python 3.11
3. ✅ Install all dependencies (pandas, scikit-learn, etc.)
4. ✅ Install Playwright and Chromium browser
5. ✅ Load your BigQuery credentials from the secret
6. ✅ Start Streamlit dashboard in background
7. ✅ Fetch latest market data (yfinance, FRED)
8. ✅ Save data to BigQuery
9. ✅ Generate 10-day regime forecasts
10. ✅ Classify market regimes
11. ✅ Capture dashboard screenshot
12. ✅ Update DAILY_PREDICTIONS.md
13. ✅ Commit and push results to GitHub
14. ✅ Upload artifacts for download

**Total runtime:** ~10-15 minutes

---

## Verification Checklist

After the workflow completes, verify:

- [ ] Workflow shows green checkmark (success)
- [ ] New commit from "GitHub Actions Bot" in repository
- [ ] `DAILY_PREDICTIONS.md` updated with latest forecasts
- [ ] `assets/dashboard.png` updated with new screenshot
- [ ] No errors in workflow logs
- [ ] Artifacts available for download

---

## Troubleshooting

### Error: "GOOGLE_APPLICATION_CREDENTIALS not set"
**Problem:** Secret not configured correctly
**Fix:** Verify secret name is exactly `GCP_CREDENTIALS` (case-sensitive)

### Error: "Invalid credentials"
**Problem:** Wrong JSON content or corrupted
**Fix:** Re-copy the JSON file contents and recreate the secret

### Error: "playwright: command not found"
**Problem:** Playwright installation failed
**Fix:** Check workflow logs - may be temporary GitHub Actions issue, retry

### Error: "Connection refused: localhost:8501"
**Problem:** Streamlit server didn't start
**Fix:** Check if port is blocked or increase sleep time in workflow

### Workflow stuck on "Waiting for Streamlit to start..."
**Problem:** Dashboard not loading
**Fix:** Check `streamlit.log` in workflow artifacts for errors

---

## What Happens After Setup

### Automatic Daily Runs
Once setup is complete, workflows will run automatically:

- **Daily at 6 AM UTC** (1 AM EST, 10 PM PST):
  - Fetch latest market data
  - Generate new forecasts
  - Update README screenshot
  - Commit results to GitHub

### Manual Triggers
You can also run manually anytime:

1. **Daily Forecast:**
   - Actions tab → "Daily Market Regime Forecast" → "Run workflow"

2. **Model Retraining:**
   - Actions tab → "Manual Model Retraining" → "Run workflow"
   - Optionally add reason (e.g., "Performance degradation")

3. **Tests:**
   - Runs automatically on every commit
   - Can also trigger manually from Actions tab

---

## Security Notes

✅ **Your credentials are safe:**
- GitHub Secrets are encrypted at rest
- Secrets are never exposed in logs (shown as `***`)
- Only workflows in THIS repository can access them
- Secrets are not accessible to forked repositories

✅ **Best practices:**
- Never commit credential files to GitHub (already protected in `.gitignore`)
- Don't share your GCP credentials file with anyone
- Rotate credentials periodically (every 90 days recommended)
- Keep local credential files outside of publicly accessible directories

---

## Cost Summary

### GitHub Actions
- **Free tier:** 2,000 minutes/month (private repo)
- **Your usage:** ~490 minutes/month
- **Cost:** **$0/month** ✅

### BigQuery
- **Free tier:** 1 TB queries/month, 10 GB storage
- **Your usage:** ~1 GB queries/month, ~10 MB storage
- **Cost:** **$0/month** ✅

### External APIs
- **yfinance:** FREE (unlimited) ✅
- **FRED:** FREE (unlimited) ✅

**Total cost: $0/month** ✅

---

## Next Steps

After successful setup:

1. ✅ Monitor first few daily runs (check for errors)
2. ✅ Star your repository (makes it look professional on GitHub)
3. ✅ Add repository to LinkedIn/resume (showcase your work)
4. ✅ Share dashboard screenshot on social media
5. ✅ Consider adding email notifications (Settings → Notifications)

---

## Support

### Documentation
- [GitHub Actions Workflows](.github/workflows/README.md) - Detailed workflow documentation
- [Configuration Status](docs/GITHUB_ACTIONS_CONFIGURATION_STATUS.md) - Technical details
- [GitHub Actions Guide](docs/github_actions_guide.md) - Comprehensive guide

### Logs
- **View workflow runs:** https://github.com/EpbAiD/marketpulse/actions
- **Check logs:** Click on any run → Expand steps → View detailed logs
- **Download artifacts:** Scroll to bottom of run → "Artifacts" section

### Issues
If something goes wrong:
1. Check workflow logs for specific error messages
2. Review troubleshooting section above
3. Verify secret is configured correctly
4. Try manual run to reproduce issue

---

## Summary

✅ **What you configured:**
- BigQuery credentials (GCP_CREDENTIALS secret)

✅ **What's already set up:**
- Python environment
- Playwright + Chromium browser
- Streamlit dashboard
- Data fetching (yfinance, FRED)
- Model training/inference
- Screenshot capture
- Git commits

✅ **What happens automatically:**
- Daily forecasts at 6 AM UTC
- Dashboard screenshots
- Results committed to GitHub
- Artifacts uploaded

⏱️ **Total setup time:** ~5 minutes
💰 **Total cost:** $0/month

---

**Ready to go?** Follow Step 1 above to get started!
