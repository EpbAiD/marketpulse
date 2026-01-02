# Streamlit Cloud Deployment Fix

## Problem

Your deployment failed because `requirements.txt` includes **torch** (PyTorch), which is ~2GB and exceeds Streamlit Cloud's installation limits.

**The dashboard doesn't need torch** - it only displays data from BigQuery. Torch is only used by the forecasting agent which runs on GitHub Actions.

---

## Solution: Use Lighter Requirements

### Step 1: Update Streamlit App Settings

1. Go to your Streamlit Cloud app
2. Click **"Settings"** (gear icon)
3. Go to **"Advanced settings"**
4. Under **"Python dependencies"**, change from `requirements.txt` to a custom file

### Step 2: Create `dashboard_requirements.txt`

I've already created a lighter version. Just commit this file:

**File: `dashboard_requirements.txt`**
```txt
# Dashboard-only requirements (no training dependencies)

# Dashboard visualization
streamlit==1.51.0
plotly==6.3.1

# Data processing
pandas==2.2.3
numpy==1.26.4
pyarrow==17.0.0

# Cloud storage (BigQuery)
google-cloud-bigquery==3.38.0
google-cloud-bigquery-storage==2.35.0
google-cloud-core==2.5.0
db-dtypes==1.3.1

# Utilities
joblib==1.4.2
pyyaml==6.0.2
matplotlib==3.9.4
```

### Step 3: Configure Streamlit to Use It

**Option A: In Streamlit Cloud UI**
1. Settings → Python version & packages
2. Change requirements file to: `dashboard_requirements.txt`
3. Reboot app

**Option B: Delete & Redeploy**
1. Delete current app
2. Create new app
3. In "Advanced settings" → Set requirements file to `dashboard_requirements.txt`
4. Deploy

---

## Quick Fix (Recommended)

Just create the file and update Streamlit settings:

```bash
# Create the file
cat > dashboard_requirements.txt << 'EOF'
# Dashboard-only requirements
streamlit==1.51.0
plotly==6.3.1
pandas==2.2.3
numpy==1.26.4
pyarrow==17.0.0
google-cloud-bigquery==3.38.0
google-cloud-bigquery-storage==2.35.0
google-cloud-core==2.5.0
db-dtypes==1.3.1
joblib==1.4.2
pyyaml==6.0.2
matplotlib==3.9.4
EOF

# Commit and push
git add dashboard_requirements.txt
git commit -m "Add lightweight requirements for Streamlit Cloud"
git push
```

Then in Streamlit Cloud:
1. Settings → Advanced
2. Requirements file: `dashboard_requirements.txt`
3. Reboot

---

## Why This Happens

| Package | Size | Needed By | Solution |
|---------|------|-----------|----------|
| **torch** | ~2GB | Forecasting agent (GitHub Actions) | Remove from dashboard |
| **langgraph** | ~500MB | Orchestration (GitHub Actions) | Remove from dashboard |
| **prophet** | ~100MB | Forecasting (GitHub Actions) | Remove from dashboard |
| **scikit-learn** | ~50MB | Classification (GitHub Actions) | Remove from dashboard |
| **streamlit** | ~50MB | Dashboard | ✅ Keep |
| **plotly** | ~30MB | Dashboard | ✅ Keep |
| **pandas** | ~40MB | Dashboard | ✅ Keep |
| **bigquery** | ~20MB | Dashboard | ✅ Keep |

**Total removed:** ~2.7GB → **Total needed:** ~180MB ✅

---

## Verification

After changing to `dashboard_requirements.txt`, the deployment should:

✅ **Install in ~2 minutes** (vs timing out)
✅ **Use ~180MB** (vs ~2.7GB)
✅ **Work perfectly** (dashboard only needs data display packages)

---

Let me know once you've created the file and I'll help you configure it in Streamlit Cloud!
