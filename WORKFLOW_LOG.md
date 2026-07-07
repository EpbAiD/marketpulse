# Workflow Execution Log

**Started**: 2026-07-07 13:25:36 UTC

---

**[13:25:36]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[13:26:24]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[13:29:06]** (3.5min) ✅ **SUCCESS**: Data fetch completed (210.0s) - Saved to BigQuery

**[13:29:09]** (3.5min) 📍 **STAGE**: Starting stage: Feature Engineering

**[13:29:09]** (3.5min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[13:32:58]** (7.4min) ✅ **SUCCESS**: Feature engineering completed (228.8s) - Saved to BigQuery

**[13:33:00]** (7.4min) 📍 **STAGE**: Starting stage: Feature Selection

**[13:33:00]** (7.4min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[13:39:06]** (13.5min) ✅ **SUCCESS**: Feature selection completed (366.8s) - Selected features saved to BigQuery

**[13:39:09]** (13.5min) ℹ️ **INFO**: Using existing HMM model (11 days old < 30 day threshold)

**[13:39:11]** (13.6min) ℹ️ **INFO**: Using existing RF classifier (10 days old < 30 day threshold)

**[13:39:26]** (13.8min) 📍 **STAGE**: Starting stage: Forecasting

**[13:39:26]** (13.8min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[13:39:26]** (13.8min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

