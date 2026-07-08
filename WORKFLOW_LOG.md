# Workflow Execution Log

**Started**: 2026-07-08 12:25:43 UTC

---

**[12:25:43]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[12:26:35]** (0.9min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[12:28:41]** (3.0min) ✅ **SUCCESS**: Data fetch completed (178.0s) - Saved to BigQuery

**[12:28:43]** (3.0min) 📍 **STAGE**: Starting stage: Feature Engineering

**[12:28:43]** (3.0min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[12:32:05]** (6.4min) ✅ **SUCCESS**: Feature engineering completed (202.4s) - Saved to BigQuery

**[12:32:08]** (6.4min) 📍 **STAGE**: Starting stage: Feature Selection

**[12:32:08]** (6.4min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[12:37:59]** (12.3min) ✅ **SUCCESS**: Feature selection completed (351.9s) - Selected features saved to BigQuery

**[12:38:01]** (12.3min) ℹ️ **INFO**: Using existing HMM model (11 days old < 30 day threshold)

**[12:38:02]** (12.3min) ℹ️ **INFO**: Using existing RF classifier (11 days old < 30 day threshold)

**[12:38:18]** (12.6min) 📍 **STAGE**: Starting stage: Forecasting

**[12:38:18]** (12.6min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[12:38:18]** (12.6min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

