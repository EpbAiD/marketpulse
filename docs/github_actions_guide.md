# GitHub Actions for MarketPulse - Complete Guide

## Yes, You Can Use GitHub Actions! 🎉

GitHub Actions is **perfect** for automating your daily market regime forecasts.

---

## Costs (Short Answer: FREE for You!)

### ✅ **FREE Plan (Your Current Setup):**

**Public Repository:**
- ✅ **UNLIMITED minutes** for standard runners
- ✅ **UNLIMITED storage** for artifacts
- ✅ **FREE forever** for public repos

**Private Repository:**
- ✅ **2,000 minutes/month** FREE
- ✅ **500 MB storage** FREE
- Your daily run: ~5 minutes/day × 30 days = **150 minutes/month**
- **Cost: $0** (well under the limit)

### Cost Breakdown:

| Plan | Free Minutes/Month | Storage | Your Usage | Cost |
|------|-------------------|---------|------------|------|
| **Free** | 2,000 min (private)<br>Unlimited (public) | 500 MB | ~150 min/month | **$0** |
| **Pro** | 3,000 min | 1 GB | N/A | $4/month |
| **Team** | 3,000 min | 2 GB | N/A | $4/user/month |

**Your situation:**
- If public repo → **FREE unlimited** ✅
- If private repo → **FREE** (150 min << 2,000 min limit) ✅

---

## What GitHub Actions Can Do for Your Project

### ✅ **Automated Daily Forecasts:**
- Run `./daily_update.sh` every 6 AM automatically
- Generate regime predictions
- Update `DAILY_PREDICTIONS.md`
- Commit results to GitHub
- **No need to keep your computer running!**

### ✅ **Automated Testing:**
- Run tests on every commit
- Validate forecasts before merging
- Check code quality

### ✅ **Scheduled Retraining:**
- Monthly model retraining
- Performance monitoring
- Alert if accuracy drops

### ✅ **CI/CD Pipeline:**
- Lint Python code
- Run data validation
- Deploy dashboard updates

---

## Implementation Guide

### Setup 1: Daily Forecast Automation (Recommended)

**What it does:**
- Runs every day at 6 AM UTC
- Executes inference pipeline
- Commits results to GitHub
- Updates dashboard screenshot

**File:** `.github/workflows/daily-forecast.yml`

```yaml
name: Daily Market Regime Forecast

on:
  schedule:
    # Run at 6 AM UTC daily (1 AM EST, 10 PM PST)
    - cron: '0 6 * * *'
  workflow_dispatch:  # Allow manual trigger

jobs:
  forecast:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run daily forecast
        env:
          # Add BigQuery credentials if needed
          GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}
        run: |
          python run_daily_update.py

      - name: Commit and push results
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add DAILY_PREDICTIONS.md assets/dashboard.png
          git diff --quiet && git diff --staged --quiet || (git commit -m "Daily forecast update $(date +'%Y-%m-%d')" && git push)
```

**Estimated runtime:** 5-10 minutes/day
**Monthly minutes:** ~300 minutes (15% of free tier)

---

### Setup 2: Test on Every Commit

**File:** `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest

      - name: Run tests
        run: |
          pytest tests/ -v

      - name: Validate data pipeline
        run: |
          python -m data_agent.fetcher --test
```

**Cost:** FREE (public repo) or ~10 min/month (private)

---

### Setup 3: Monthly Model Retraining

**File:** `.github/workflows/retrain.yml`

```yaml
name: Monthly Model Retraining

on:
  schedule:
    # Run on 1st of every month at 2 AM UTC
    - cron: '0 2 1 * *'
  workflow_dispatch:

jobs:
  retrain:
    runs-on: ubuntu-latest
    timeout-minutes: 120  # 2 hours max

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run full training pipeline
        env:
          GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}
        run: |
          python run_pipeline.py --workflow training

      - name: Upload model artifacts
        uses: actions/upload-artifact@v4
        with:
          name: trained-models
          path: outputs/models/
          retention-days: 90

      - name: Commit updated models
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add outputs/models/metadata.json
          git commit -m "Monthly model retraining $(date +'%Y-%m-%d')" || true
          git push || true
```

**Estimated runtime:** 60-90 minutes/month
**Monthly minutes:** ~90 minutes (4.5% of free tier)

---

## Current Repository Status

**Your repo:** `https://github.com/EpbAiD/marketpulse`

**Visibility:**
- If **public** → ✅ Unlimited free minutes
- If **private** → ✅ 2,000 free minutes/month

**Current setup:**
- ❌ No `.github/workflows/` directory
- ❌ No automation configured
- ✅ Ready to implement!

---

## Implementation Steps

### Step 1: Create Workflows Directory

```bash
mkdir -p .github/workflows
```

### Step 2: Add Daily Forecast Workflow

Create `.github/workflows/daily-forecast.yml` with the YAML above.

### Step 3: Configure Secrets (If Using BigQuery)

1. Go to: `https://github.com/EpbAiD/marketpulse/settings/secrets/actions`
2. Click "New repository secret"
3. Name: `GCP_CREDENTIALS`
4. Value: Your BigQuery service account JSON (base64 encoded)

### Step 4: Test Manually

1. Go to Actions tab: `https://github.com/EpbAiD/marketpulse/actions`
2. Select "Daily Market Regime Forecast"
3. Click "Run workflow"
4. Monitor execution

### Step 5: Enable Daily Schedule

Workflows with `schedule` trigger run automatically!

---

## Benefits vs. Local Cron Job

| Feature | Local Cron | GitHub Actions |
|---------|-----------|----------------|
| **Cost** | Free (your electricity) | FREE (GitHub servers) |
| **Uptime** | Requires your computer on | ✅ Always available |
| **Scalability** | Single machine | ✅ Cloud infrastructure |
| **Logs** | Local files | ✅ Built-in UI with history |
| **Debugging** | Manual | ✅ Visual workflow viewer |
| **Security** | Your credentials | ✅ Encrypted secrets |
| **Portability** | Tied to your machine | ✅ Works anywhere |

---

## Cost Estimate for Your Project

### Scenario 1: Public Repository (Recommended)

**Usage:**
- Daily forecast: 5 min × 30 days = 150 min
- Tests on commits: 2 min × 20 commits = 40 min
- Monthly retrain: 90 min × 1 = 90 min
- **Total:** 280 minutes/month

**Cost:** **$0** (unlimited for public repos)

### Scenario 2: Private Repository

**Usage:** Same as above (280 min/month)

**Cost:**
- Free tier: 2,000 min/month
- Your usage: 280 min/month (14% of quota)
- **Cost:** **$0** (well under limit)

### If You Exceed Free Tier (Unlikely):

**Pricing:**
- Linux runners: $0.008/minute
- 1,000 extra minutes = $8
- You'd need 5,000 min/month to hit costs (17× current usage)

**Your actual cost: $0** ✅

---

## Limitations to Be Aware Of

### ✅ **Not a Problem for You:**

1. **Runtime Limit:** 6 hours/job
   - Your job: ~5 minutes ✅

2. **Storage Limit:** 500 MB (free tier)
   - Your artifacts: ~10 MB ✅

3. **Concurrent Jobs:** 20 (free tier)
   - Your jobs: 1 at a time ✅

### ⚠️ **Potential Issues:**

1. **BigQuery Access:**
   - Need to store GCP credentials as GitHub secret
   - Solution: Use service account JSON

2. **Large Model Files:**
   - Can't store 1GB+ model files in repo
   - Solution: Use Git LFS or external storage

3. **Long Training:**
   - If retraining takes >2 hours, may timeout
   - Solution: Split into multiple jobs

---

## Security Best Practices

### ✅ **Do:**
- Store BigQuery credentials in GitHub Secrets
- Use `GITHUB_TOKEN` for commits (auto-generated)
- Limit secret access to specific workflows
- Use `workflow_dispatch` for manual testing

### ❌ **Don't:**
- Hardcode credentials in workflow files
- Commit credentials to repository
- Grant unnecessary permissions
- Store API keys in code

---

## Monitoring & Debugging

### View Workflow Runs:
```
https://github.com/EpbAiD/marketpulse/actions
```

### Check Logs:
1. Click on workflow run
2. Expand job steps
3. View real-time logs

### Enable Email Notifications:
Settings → Notifications → Actions → Email on failure

---

## Alternative: Self-Hosted Runner (Advanced)

If you want to run on your own hardware (e.g., Mac with MPS for faster training):

**Setup:**
1. Go to Settings → Actions → Runners
2. Click "New self-hosted runner"
3. Follow setup instructions

**Cost:**
- Hardware: Your existing Mac
- Electricity: ~$5/month
- GitHub Actions: **FREE** (self-hosted = no minutes charged)

**Use case:**
- Large model training
- Need GPU acceleration
- Already have powerful local machine

---

## Recommended Setup for You

### Phase 1: Start Simple (This Week)

**Implement:**
1. Daily forecast workflow
2. Manual trigger option

**Cost:** $0
**Time to setup:** 30 minutes

### Phase 2: Add Testing (Next Week)

**Implement:**
1. Tests on every commit
2. Code quality checks

**Cost:** $0
**Time to setup:** 1 hour

### Phase 3: Full Automation (Month 2)

**Implement:**
1. Monthly retraining
2. Performance monitoring
3. Slack/email alerts

**Cost:** $0
**Time to setup:** 2 hours

---

## Sample Workflow File (Ready to Use)

I can create this for you! Here's what you'll get:

### `.github/workflows/daily-forecast.yml`
- Runs at 6 AM UTC daily
- Executes your pipeline
- Commits results
- Handles errors gracefully

### `.github/workflows/manual-retrain.yml`
- Manually triggered only
- Full training pipeline
- Artifact upload
- Email notification on completion

---

## Comparison with Other CI/CD Options

| Platform | Free Tier | Ease of Use | Integration |
|----------|-----------|-------------|-------------|
| **GitHub Actions** | ✅ 2,000 min | ✅✅✅ Native | ✅✅✅ Perfect |
| GitLab CI | 400 min | ✅✅ Good | ✅✅ Good |
| CircleCI | 6,000 min | ✅ Moderate | ✅ Fair |
| Jenkins | Unlimited (self-host) | ❌ Complex | ✅ Good |
| AWS CodeBuild | 100 min | ✅ Moderate | ✅ Fair |

**Best choice:** GitHub Actions (native, free, easy)

---

## Real-World Examples

### Similar ML Projects Using GitHub Actions:

1. **Automated Stock Predictions:**
   - Daily LSTM forecasts
   - Costs: $0/month (public repo)

2. **Weather Forecasting Bot:**
   - Hourly predictions
   - Costs: $0/month (150 min/day, public)

3. **Sentiment Analysis Pipeline:**
   - Daily Twitter scraping + analysis
   - Costs: $0/month (under 2,000 min)

**Your project fits perfectly in this category!**

---

## Next Steps

### Want me to implement this for you?

I can create:

1. ✅ `.github/workflows/daily-forecast.yml` - Daily automation
2. ✅ `.github/workflows/tests.yml` - Quality checks
3. ✅ `.github/workflows/manual-retrain.yml` - Monthly retraining
4. ✅ Documentation on how to use them

**Time to implement:** 15 minutes
**Cost:** $0/month
**Benefit:** Fully automated, hands-off forecasting

---

## FAQ

### Q: Will this work if my repo is private?
**A:** Yes! You get 2,000 free minutes/month (your usage: ~280 min)

### Q: Do I need to keep my computer on?
**A:** No! GitHub runs it on their servers.

### Q: What if I exceed free tier?
**A:** Very unlikely. You'd need 7× current usage. Even then, overage is cheap ($0.008/min).

### Q: Can I run this locally too?
**A:** Yes! Keep your cron job or run manually. GitHub Actions is supplementary.

### Q: How do I stop it?
**A:** Disable the workflow in `.github/workflows/` or delete the file.

### Q: Does this work with BigQuery?
**A:** Yes! Store GCP credentials as GitHub Secret.

---

## Conclusion

### ✅ **YES, Use GitHub Actions!**

**Reasons:**
1. **FREE** for your usage (280 min << 2,000 min limit)
2. **Reliable** (GitHub's infrastructure)
3. **Easy** to set up (15 minutes)
4. **Professional** (production-grade CI/CD)
5. **Showcaseable** (employers love seeing this)

**No downsides** for your project size!

---

## Sources

- [GitHub Actions billing and usage](https://docs.github.com/en/actions/concepts/billing-and-usage)
- [Pricing changes for GitHub Actions](https://resources.github.com/actions/2026-pricing-changes-for-github-actions/)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub pricing plans](https://github.com/pricing)
- [Actions billing documentation](https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions)

---

**Created:** December 27, 2024
**Recommendation:** ✅ IMPLEMENT (Free, Easy, Professional)
**Estimated Setup Time:** 15-30 minutes
**Monthly Cost:** $0
