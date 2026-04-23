# Kaggle GPU Training Setup

One-time setup to migrate training from Cloud Run to Kaggle's free T4 GPU.

## 1. Kaggle Secrets (on kaggle.com)

Go to: https://www.kaggle.com/settings → Add-ons → Secrets

Add two secrets:

| Secret name        | Value                                                                 |
|--------------------|-----------------------------------------------------------------------|
| `GITHUB_TOKEN`     | GitHub PAT with `repo` scope (write access to `EpbAiD/marketpulse`)   |
| `GCP_CREDENTIALS`  | Contents of your GCP service-account JSON (same one in GH Actions)    |

Generate a GitHub PAT at: https://github.com/settings/tokens/new (fine-grained, repo access).

## 2. GitHub Actions Secrets (on github.com)

Go to: https://github.com/EpbAiD/marketpulse/settings/secrets/actions

Add two new secrets (in addition to the existing `GCP_CREDENTIALS`):

| Secret name        | Value                                                         |
|--------------------|---------------------------------------------------------------|
| `KAGGLE_USERNAME`  | Your Kaggle username (e.g. `eeshanbhanap`)                    |
| `KAGGLE_KEY`       | API key from kaggle.com → Settings → Create New API Token     |

Downloading the API token from Kaggle gives you a `kaggle.json` with both username and key.

## 3. First Deployment of the Kernel

From your local repo (one time only, to publish the kernel):

```bash
# Install kaggle CLI
pip install kaggle

# Put your API creds in ~/.kaggle/kaggle.json (from step 2)
mkdir -p ~/.kaggle
mv /path/to/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json

# Fill in your username and push the kernel
cd kaggle
sed -i '' "s|KAGGLE_USERNAME|$KAGGLE_USERNAME|g" kernel-metadata.json  # macOS
kaggle kernels push
```

After first push, the kernel lives at: `https://www.kaggle.com/code/<username>/marketpulse-training`.

## 4. How It Works

Every daily GitHub Actions run:
1. Fetches market data → BigQuery (same as before)
2. Runs `intelligent_model_checker`
3. If models are stale → triggers the Kaggle kernel
4. Kaggle pulls the repo, runs LangGraph training on T4 GPU, commits models back
5. Next day's inference uses the fresh models

Kaggle free tier gives **30 hrs/week of GPU time** — more than enough for monthly retrains (~90 min each).

## 5. Verifying the Setup

Test the end-to-end flow manually:

```bash
# Force a training run from your terminal
cd kaggle
kaggle kernels push
kaggle kernels status $KAGGLE_USERNAME/marketpulse-training
# Open the kernel URL to watch logs
```

Then check the repo for a new commit:
```
chore: retrain models via Kaggle GPU (...) [skip ci]
```

## 6. Rolling Back

If Kaggle becomes flaky, the GitHub Actions workflow has `continue-on-error: true` on the training step — inference still runs with the existing models. To fully roll back to Cloud Run, revert the `kaggle_training` step in `.github/workflows/daily-forecast.yml` back to the `gcloud run jobs execute` block from git history.
