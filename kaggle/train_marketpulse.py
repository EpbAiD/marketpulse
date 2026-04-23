"""
MarketPulse Training — Kaggle GPU Kernel
=========================================
Runs the LangGraph training pipeline on Kaggle's free T4 GPU.

Flow:
  1. Clone marketpulse repo using GITHUB_TOKEN
  2. Install dependencies
  3. Check which models need retraining (uses intelligent_model_checker)
  4. Try BigQuery first for data; fall back to committed parquets if it fails
  5. Run `run_pipeline.py --workflow training` with feature subset
  6. Commit trained models back to main branch

Triggered by GitHub Actions via kaggle-api when model checker detects stale models.
Uses Kaggle Secrets: GITHUB_TOKEN, GCP_CREDENTIALS.
"""
import os
import sys
import subprocess
import json
from pathlib import Path

# -----------------------------------------------------------------------------
# 1. Load secrets from Kaggle
# -----------------------------------------------------------------------------
from kaggle_secrets import UserSecretsClient

secrets = UserSecretsClient()
GITHUB_TOKEN = secrets.get_secret("GITHUB_TOKEN")
GITHUB_REPO = "EpbAiD/marketpulse"

try:
    GCP_CREDENTIALS = secrets.get_secret("GCP_CREDENTIALS")
    HAS_BIGQUERY = True
except Exception:
    print("⚠️  GCP_CREDENTIALS not found — will use parquet fallback for data")
    HAS_BIGQUERY = False

# Write GCP creds to a temp file for google-cloud-bigquery to pick up
if HAS_BIGQUERY:
    gcp_path = "/tmp/gcp_creds.json"
    with open(gcp_path, "w") as f:
        f.write(GCP_CREDENTIALS)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_path


# -----------------------------------------------------------------------------
# 2. Clone repo
# -----------------------------------------------------------------------------
REPO_DIR = "/kaggle/working/marketpulse"

if os.path.exists(REPO_DIR):
    subprocess.run(["rm", "-rf", REPO_DIR], check=True)

clone_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
print(f"📥 Cloning {GITHUB_REPO}...")
subprocess.run(["git", "clone", clone_url, REPO_DIR], check=True)

os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR)

# Configure git identity for commits
subprocess.run(["git", "config", "user.email", "kaggle-bot@marketpulse.ai"], check=True)
subprocess.run(["git", "config", "user.name", "Kaggle Training Bot"], check=True)


# -----------------------------------------------------------------------------
# 3. Install dependencies
# -----------------------------------------------------------------------------
# Kaggle ships with torch/torchvision/torchaudio already installed and matched
# to the CUDA runtime. Installing `torch==2.6.0` on top breaks torchvision's
# C extensions (circular import). Filter those lines out and keep Kaggle's
# preinstalled torch stack.
print("\n📦 Installing dependencies (skipping torch family to keep Kaggle's stack)...")
with open("requirements_github_actions.txt") as f:
    reqs = f.read().splitlines()

filtered = [
    line for line in reqs
    if line.strip() and not line.strip().startswith("#")
    and not line.strip().lower().startswith(("torch==", "torchvision", "torchaudio", "pytorch-lightning"))
]

with open("/tmp/kaggle_requirements.txt", "w") as f:
    f.write("\n".join(filtered))

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-r", "/tmp/kaggle_requirements.txt"],
    check=True,
)

# Confirm GPU + torch is still usable
import torch
print(f"\n🖥️  torch {torch.__version__}, GPU: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   Device: {torch.cuda.get_device_name(0)}")


# -----------------------------------------------------------------------------
# 4. Decide what to train (uses LangGraph's intelligent model checker)
# -----------------------------------------------------------------------------
from orchestrator.intelligent_model_checker import get_intelligent_recommendation

recommendation = get_intelligent_recommendation()
print(f"\n🧠 Checker recommendation: {recommendation['workflow']}")
print(f"   Reason: {recommendation['reason']}")

if recommendation["workflow"] == "inference":
    print("✅ All models are fresh — no training needed. Exiting.")
    sys.exit(0)

features_to_train = recommendation.get("features_to_train", [])
retrain_core = recommendation.get("retrain_core", False)
print(f"   Features to train: {features_to_train}")
print(f"   Retrain core models (HMM+RF): {retrain_core}")


# -----------------------------------------------------------------------------
# 5. Run the LangGraph training pipeline
# -----------------------------------------------------------------------------
# --workflow auto invokes the LangGraph graph and internally uses
# intelligent_model_checker to decide which features need retraining.
# Data fetch uses BigQuery (via GOOGLE_APPLICATION_CREDENTIALS set above);
# local parquet fallback is built into the fetcher.
cmd = [sys.executable, "run_pipeline.py", "--workflow", "auto", "--no-clean"]

print(f"\n🏋️  Running: {' '.join(cmd)}")
result = subprocess.run(cmd, cwd=REPO_DIR)

if result.returncode != 0:
    print(f"❌ Training failed with exit code {result.returncode}")
    sys.exit(result.returncode)

# Sanity check: did training actually produce cluster assignments?
# run_pipeline.py can exit 0 even when data fetch fails silently.
cluster_path = Path(REPO_DIR) / "outputs" / "clustering" / "cluster_assignments.parquet"
if retrain_core and not cluster_path.exists():
    print("❌ Training ran but cluster_assignments.parquet is missing — fetch or clustering likely failed.")
    sys.exit(1)


# -----------------------------------------------------------------------------
# 6. Commit trained models back to main
# -----------------------------------------------------------------------------
print("\n📤 Committing trained models to GitHub...")

paths_to_commit = [
    "outputs/models/",
    "outputs/clustering/",
    "outputs/forecasting/models/",
    # outputs/selected/ is gitignored (regenerated on each run)
]

subprocess.run(["git", "add"] + paths_to_commit, cwd=REPO_DIR)

# Only commit if there are changes
diff_result = subprocess.run(
    ["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR
)
if diff_result.returncode == 0:
    print("ℹ️  No model changes to commit.")
else:
    feature_summary = ",".join(features_to_train) if features_to_train else "all"
    commit_msg = f"chore: retrain models via Kaggle GPU ({feature_summary}) [skip ci]"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_DIR, check=True)
    # Pull + rebase in case main advanced while we trained
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO_DIR)
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True)
    print("✅ Models committed and pushed to main.")

print("\n✅ Kaggle training job complete.")
