# Cloud Run GPU Training Setup

This directory contains everything needed to run model training on Google Cloud Run with GPU acceleration.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│ Cloud Scheduler │────▶│  Cloud Run Job       │────▶│ Push to GitHub  │
│  (Daily 6 AM)   │     │  (GPU: NVIDIA L4)    │     │ (Models + JSON) │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
         │                        │
         │              ┌─────────┴─────────┐
         │              │                   │
         ▼              ▼                   ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│ Manual Trigger  │  │  BigQuery   │  │ Secret       │
│ (GitHub Action) │  │  (Data)     │  │ Manager      │
└─────────────────┘  └─────────────┘  └──────────────┘
```

## Cost Estimate

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| Cloud Run (GPU) | ~9 hrs/month | ~$4.50 |
| Artifact Registry | ~2 GB | ~$0.20 |
| Cloud Scheduler | 1 job | Free |
| Secret Manager | 2 secrets | Free |
| **Total** | | **~$5/month** |

## Setup Instructions

### 1. Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
- Docker installed
- GCP project with billing enabled

### 2. Set Environment Variable

```bash
export GCP_PROJECT_ID=your-actual-project-id
```

### 3. Run Setup Script

```bash
chmod +x cloud_run/*.sh
./cloud_run/setup.sh
```

### 4. Add Secrets

```bash
# GitHub Personal Access Token (needs repo write access)
echo 'ghp_your_github_token' | gcloud secrets versions add github-token --data-file=-

# GCP credentials (your existing BigQuery credentials)
gcloud secrets versions add gcp-credentials --data-file=/path/to/your/credentials.json
```

### 5. Build and Deploy

```bash
./cloud_run/deploy.sh
```

### 6. Create Scheduler

```bash
./cloud_run/create_scheduler.sh
```

## Manual Execution

### From Command Line

```bash
# Auto mode (intelligent retraining)
gcloud run jobs execute marketpulse-training --region=us-central1

# Train specific features
gcloud run jobs execute marketpulse-training --region=us-central1 \
  --update-env-vars="MODE=train,FEATURES=GSPC,VIX,TNX"

# Force retrain all
gcloud run jobs execute marketpulse-training --region=us-central1 \
  --update-env-vars="MODE=train,FORCE_RETRAIN=true"
```

### From GitHub Actions

Go to Actions → "Trigger Cloud Run Training" → Run workflow

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODE` | `auto`, `train`, or `inference` | `auto` |
| `FEATURES` | Comma-separated feature names or `all` | `all` |
| `FORCE_RETRAIN` | Force retrain even if fresh | `false` |
| `GITHUB_TOKEN` | PAT for pushing results | (from secret) |
| `GITHUB_REPO` | Repository name | `EpbAiD/marketpulse` |

## Monitoring

### View Logs

```bash
gcloud run jobs executions list --job=marketpulse-training --region=us-central1

# Get logs for specific execution
gcloud run jobs executions logs EXECUTION_NAME --region=us-central1
```

### View in Console

1. Go to [Cloud Run Console](https://console.cloud.google.com/run)
2. Select your project
3. Click on "Jobs" tab
4. Click on "marketpulse-training"

## Troubleshooting

### Job fails to start
- Check GPU quota in us-central1
- Verify secrets are set up correctly

### Out of memory
- Increase memory limit in job.yaml
- Train fewer features at once

### Git push fails
- Verify GitHub token has repo write access
- Check for merge conflicts
