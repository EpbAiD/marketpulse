# Workflow Execution Log

**Started**: 2026-01-20 11:26:56 UTC

---

**[11:26:56]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[11:26:58]** (0.0min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[11:28:16]** (1.3min) ✅ **SUCCESS**: Data fetch completed (80.3s) - Saved to BigQuery

**[11:28:18]** (1.4min) 📍 **STAGE**: Starting stage: Feature Engineering

**[11:28:18]** (1.4min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[11:29:40]** (2.7min) ✅ **SUCCESS**: Feature engineering completed (82.5s) - Saved to BigQuery

**[11:29:41]** (2.8min) 📍 **STAGE**: Starting stage: Feature Selection

**[11:29:42]** (2.8min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[11:33:42]** (6.8min) ✅ **SUCCESS**: Feature selection completed (241.0s) - Selected features saved to BigQuery

**[11:33:43]** (6.8min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[11:33:43]** (6.8min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[11:33:57]** (7.0min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[11:33:57]** (7.0min) ✅ **SUCCESS**: HMM clustering completed (13.6s) - 3 regimes detected, saved to BigQuery

