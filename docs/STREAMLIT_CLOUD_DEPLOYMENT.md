# Streamlit Cloud Deployment Guide

Deploy your MarketPulse dashboard to Streamlit Cloud for 24/7 public access!

---

## ✅ Prerequisites

- GitHub repository with code pushed ✅ (already done)
- BigQuery credentials JSON file ✅ (already have it)
- Streamlit Community Cloud account (free)

---

## Step 1: Create Streamlit Cloud Account

1. **Go to:** https://share.streamlit.io/

2. **Sign up with GitHub:**
   - Click "Continue with GitHub"
   - Authorize Streamlit to access your repositories

3. **Verify email** (if prompted)

---

## Step 2: Deploy Your App

### 2.1 Create New App

1. Click **"New app"** button

2. **Fill in deployment settings:**
   - **Repository:** `EpbAiD/marketpulse`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
   - **App URL (optional):** Choose custom subdomain like `marketpulse-yourname`

3. Click **"Deploy!"**

### 2.2 Initial Deployment

The app will:
- ⏳ Install dependencies from `requirements.txt`
- ⏳ Install system packages from `packages.txt`
- ❌ **FAIL initially** (expected - no credentials yet)

---

## Step 3: Add BigQuery Credentials

### 3.1 Get Your Credentials

On your local machine:

```bash
cat /Users/eeshanbhanap/Desktop/RFP/regime01-b5321d26c433.json
```

**Copy the ENTIRE JSON output** (all of it, including curly braces)

### 3.2 Add to Streamlit Secrets

1. In Streamlit Cloud, click **"⚙️ Settings"** (top right)

2. Go to **"Secrets"** tab

3. **Paste your credentials in TOML format:**

```toml
[gcp_service_account]
type = "service_account"
project_id = "regime01"
private_key_id = "YOUR_PRIVATE_KEY_ID_HERE"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n"
client_email = "YOUR_CLIENT_EMAIL_HERE"
client_id = "YOUR_CLIENT_ID_HERE"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CERT_URL_HERE"
```

**IMPORTANT:** Replace the placeholder values with actual values from your JSON file!

### 3.3 Save and Reboot

1. Click **"Save"** button

2. Click **"Reboot app"** (this restarts with new secrets)

3. Wait ~2-3 minutes for rebuild

---

## Step 4: Verify Deployment

### 4.1 Check App Status

Your app URL will be something like:
```
https://marketpulse-yourname.streamlit.app
```

Or the default:
```
https://yourname-marketpulse-dashboardapp-xxxxx.streamlit.app
```

### 4.2 Expected Behavior

✅ **Success indicators:**
- Dashboard loads
- Shows latest regime forecasts
- Charts render correctly
- No BigQuery connection errors

❌ **If you see errors:**
- Check secrets format (must be valid TOML)
- Verify all credentials fields are filled
- Check Streamlit Cloud logs (Settings → Logs)

---

## Step 5: Configure Auto-Updates

### 5.1 Enable Auto-Deployment

Streamlit Cloud automatically redeploys when you push to GitHub!

**Current setup:**
- Push to `main` branch → Streamlit Cloud auto-deploys
- Daily GitHub Actions workflow runs → Updates data in BigQuery
- Dashboard refreshes data automatically (pulls from BigQuery)

###5.2 Data Refresh Cycle

```
Daily at 6 AM EST:
GitHub Actions runs
  ↓
Updates BigQuery tables
  ↓
Streamlit Cloud dashboard (always running)
  ↓
Fetches latest data from BigQuery
  ↓
Users see updated forecasts!
```

**Dashboard updates:** Real-time (pulls fresh data from BigQuery on each page load)

**No manual intervention needed!**

---

## Security Best Practices

### ✅ What We Did Right

1. **Credentials in secrets** - Never in code
2. **GitHub .gitignore** - Excludes credentials file
3. **TOML template only** - Actual secrets.toml not committed
4. **Service account** - Limited permissions, not personal account

### ⚠️ Security Notes

- **Streamlit Cloud secrets are encrypted** at rest
- **Only your app can access** secrets (isolated environment)
- **Never share** your credentials JSON file
- **Rotate credentials** periodically (every 90 days recommended)

### 🔒 If Credentials Compromised

1. **Revoke service account** in Google Cloud Console
2. **Create new service account** with same permissions
3. **Update secrets** in Streamlit Cloud
4. **Update GitHub Actions** secret (`GCP_CREDENTIALS`)
5. **Update local** credentials file

---

## Troubleshooting

### Error: "No module named 'X'"

**Problem:** Missing dependency in requirements.txt

**Fix:**
1. Add package to `requirements.txt`
2. Push to GitHub
3. Streamlit Cloud auto-redeploys

### Error: "Please install the 'db-dtypes' package"

**Problem:** Missing BigQuery dependency

**Fix:** Already in requirements.txt (fixed)

### Error: "BigQuery credentials not found"

**Problem:** Secrets not configured or wrong format

**Fix:**
1. Go to Settings → Secrets
2. Verify `[gcp_service_account]` section exists
3. Check all fields are filled
4. Ensure no typos in TOML format
5. Reboot app

### Error: "403 Forbidden" or "Permission denied"

**Problem:** Service account lacks permissions

**Fix:**
1. Go to Google Cloud Console
2. IAM & Admin → Service Accounts
3. Find your service account
4. Grant roles:
   - `BigQuery Data Editor`
   - `BigQuery Job User`

### Dashboard loads but shows no data

**Problem:** BigQuery tables empty or wrong dataset

**Fix:**
1. Run local pipeline first: `python run_daily_update.py`
2. Verify data in BigQuery console
3. Check `configs/bigquery_config.yaml` dataset name matches

### App is slow to load

**Normal behavior:**
- First load: 10-15 seconds (fetching from BigQuery)
- Subsequent loads: 2-3 seconds (Streamlit caching)

**If very slow (>30s):**
- Check BigQuery query complexity
- Verify network connectivity
- Check Streamlit Cloud status page

---

## App Management

### View Logs

1. Go to your app in Streamlit Cloud
2. Click **"⚙️ Settings"**
3. Go to **"Logs"** tab
4. See real-time logs and errors

### Reboot App

1. Settings → **"Reboot app"**
2. Wait 2-3 minutes
3. Useful after:
   - Changing secrets
   - Updating code
   - Debugging issues

### Delete App

1. Settings → **"Delete app"**
2. Confirm deletion
3. **Warning:** This is permanent!

---

## Cost & Limits

### Streamlit Community Cloud (FREE Tier)

✅ **Included:**
- **Unlimited public apps**
- **Unlimited viewers**
- **1 GB memory per app**
- **1 CPU core**
- **Custom subdomain**
- **Auto-deployment from GitHub**

❌ **Limitations:**
- **Public only** (cannot make private)
- **No custom domains** (only *.streamlit.app)
- **Resource limits** (1 GB RAM, 1 CPU)

### Upgrade Options

**Streamlit Cloud Teams ($250/month):**
- Private apps
- 4 GB memory
- Priority support
- Custom authentication

**For this project:** FREE tier is sufficient! ✅

---

## Performance Tips

### 1. Enable Streamlit Caching

Already configured in `dashboard/app.py`:

```python
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data():
    # Fetch from BigQuery
    ...
```

### 2. Optimize BigQuery Queries

- Use `LIMIT` clauses
- Select only needed columns
- Add indexes on timestamp columns

### 3. Use Dataframes Efficiently

- Filter data early
- Avoid repeated computations
- Use pandas vectorization

---

## Alternative: Local-Only Dashboard

If you prefer NOT to deploy publicly:

### Option 1: Run Locally

```bash
streamlit run dashboard/app.py
```

Then open: http://localhost:8501

**Pros:** Full control, private
**Cons:** Manual, only accessible from your machine

### Option 2: Deploy on Your Own Server

Use Docker + nginx:
- Full privacy
- Custom domain
- More resources
- Costs: ~$5-10/month (VPS)

---

## Summary

### What You Get

✅ **Public dashboard URL:** `https://yourapp.streamlit.app`
✅ **Auto-updates:** Pulls latest data from BigQuery
✅ **Always online:** 24/7 availability
✅ **Free hosting:** $0/month
✅ **No maintenance:** Streamlit handles infrastructure

### What Happens Daily

```
6 AM EST:
  ↓
GitHub Actions workflow runs
  ↓
Fetches market data (yfinance, FRED)
  ↓
Generates regime forecasts
  ↓
Saves to BigQuery
  ↓
Streamlit dashboard (always running) fetches new data
  ↓
Users see updated forecasts instantly!
```

### Verification Checklist

After deployment, verify:

- [ ] Dashboard loads at your Streamlit URL
- [ ] Shows latest forecast data
- [ ] Charts render correctly
- [ ] No error messages
- [ ] BigQuery connection works
- [ ] Regime predictions display
- [ ] Feature trends visible
- [ ] Performance metrics show

---

## Next Steps

### 1. Share Your Dashboard

**Add to README:**
```markdown
## Live Dashboard

View the live dashboard: [https://your-app.streamlit.app](https://your-app.streamlit.app)
```

**Share on social media:**
- LinkedIn: Showcase your project
- Twitter: Share with #datascience #streamlit
- Portfolio: Add to your personal website

### 2. Monitor Usage

Streamlit Cloud provides:
- **Viewer count** (total views)
- **Active users** (concurrent)
- **Performance metrics**

Access via Settings → Analytics

### 3. Enhance Dashboard

Optional improvements:
- Add user authentication (if upgrade to Teams plan)
- Custom themes (edit `.streamlit/config.toml`)
- More visualizations
- Export to PDF functionality
- Email alerts integration

---

## Support

### Streamlit Cloud Docs
https://docs.streamlit.io/streamlit-community-cloud

### Community Forum
https://discuss.streamlit.io/

### GitHub Issues
https://github.com/EpbAiD/marketpulse/issues

---

**Ready to deploy? Follow Step 1 above to get started!** 🚀
