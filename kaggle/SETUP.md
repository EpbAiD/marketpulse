# Kaggle GPU Training Setup

One-time setup to migrate training from Cloud Run to Kaggle's free T4 GPU.

## Why secrets live in a Kaggle Dataset, not Kaggle Secrets

Kaggle's `UserSecretsClient` ("Add-ons → Secrets") binds secrets to a specific
**kernel version**. Every `kaggle kernels push` creates a new version, and
Kaggle does NOT carry secret attachments forward — so any push from GitHub
Actions immediately fails with `HTTP 400: Bad Request` on the very first
`secrets.get_secret(...)` call.

Kaggle **Datasets** persist across kernel versions when listed in
`kernel-metadata.json -> dataset_sources`. So we ship a private dataset
called `marketpulse-secrets` containing one file (`secrets.json`) and the
kernel reads from `/kaggle/input/marketpulse-secrets/secrets.json`.

## 1. Create the secrets dataset (one-time, on kaggle.com)

```bash
# On your local machine. Build a single JSON file with both tokens.
mkdir -p /tmp/marketpulse-secrets

cat > /tmp/marketpulse-secrets/secrets.json <<EOF
{
  "GITHUB_TOKEN": "ghp_YOUR_FINE_GRAINED_PAT",
  "GCP_CREDENTIALS": $(cat ~/Downloads/regime01-b5321d26c433.json | jq -Rs .)
}
EOF

# Initialize as a Kaggle Dataset
cd /tmp/marketpulse-secrets
kaggle datasets init -p .

# Edit the generated dataset-metadata.json: set "title", "id" to
#   <your-kaggle-username>/marketpulse-secrets
# and ensure isPrivate: true

# Create the dataset (private)
kaggle datasets create -p . --dir-mode zip
```

Verify it shows up at `https://www.kaggle.com/datasets/<your-username>/marketpulse-secrets`
with the **Private** badge.

To update secrets later (e.g. rotate GitHub PAT):
```bash
# Edit /tmp/marketpulse-secrets/secrets.json then:
kaggle datasets version -p /tmp/marketpulse-secrets -m "rotate tokens"
```

## 2. GitHub Actions Secrets (on github.com)

Go to: https://github.com/EpbAiD/marketpulse/settings/secrets/actions

| Secret name        | Value                                                         |
|--------------------|---------------------------------------------------------------|
| `KAGGLE_USERNAME`  | Your Kaggle username (e.g. `eeshanprasadbhanap`)              |
| `KAGGLE_KEY`       | API key from kaggle.com → Settings → Create New API Token     |
| `GCP_CREDENTIALS`  | (already exists — keep as is, used by GH Actions itself)      |

The kaggle CLI uses `KAGGLE_USERNAME` + `KAGGLE_KEY` env vars to authenticate.

## 3. First Deployment of the Kernel

From your local repo (one time only, to publish the kernel):

```bash
# Install kaggle CLI
pip install kaggle

# Put your API creds in ~/.kaggle/kaggle.json
mkdir -p ~/.kaggle
mv /path/to/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json

# Substitute KAGGLE_USERNAME placeholder with your actual username
# (the committed file uses the placeholder; CI does the same substitution)
cd kaggle
sed -i '' "s|KAGGLE_USERNAME|$KAGGLE_USERNAME|g" kernel-metadata.json  # macOS

# Push the kernel — this creates v1
kaggle kernels push
```

The committed `kernel-metadata.json` lists `KAGGLE_USERNAME/marketpulse-secrets`
as a dataset source. After substitution it becomes
`<your-username>/marketpulse-secrets`, and Kaggle attaches the dataset
automatically. **No manual UI clicks required.**

After first push, the kernel lives at:
`https://www.kaggle.com/code/<your-username>/marketpulse-training`.

## 4. How It Works

Every daily GitHub Actions run:
1. Fetches market data → BigQuery
2. Runs `intelligent_model_checker`
3. If models are stale → `kaggle kernels push -p kaggle/` from CI
4. The new kernel version inherits the dataset attachment automatically
5. Kernel reads secrets from `/kaggle/input/marketpulse-secrets/secrets.json`,
   clones the repo, runs LangGraph training on T4 GPU, commits models back
6. Next day's inference uses the fresh models

Kaggle free tier gives **30 hrs/week of GPU time** — plenty for monthly retrains.

## 5. Verifying the Setup

Trigger a manual run:

```bash
cd kaggle
kaggle kernels push                                            # creates a new version
kaggle kernels status $KAGGLE_USERNAME/marketpulse-training    # poll status
# When status hits COMPLETE, the kernel pushed a chore: commit to main.
```

Or open the kernel URL in browser and click **Save & Run All**.

## 6. Rolling Back

If Kaggle becomes flaky, the GitHub Actions workflow has `continue-on-error: true`
on the training step — inference still runs with the existing models. To fully
roll back, revert the `kaggle_training` step in `.github/workflows/daily-forecast.yml`
to the prior `gcloud run jobs execute` block from git history.
