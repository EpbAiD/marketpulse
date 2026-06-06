# Workflow Execution Log

**Started**: 2026-06-06 12:10:09 UTC

---

**[12:10:09]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[12:10:58]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[12:14:42]** (4.6min) ✅ **SUCCESS**: Data fetch completed (273.6s) - Saved to BigQuery

**[12:14:45]** (4.6min) 📍 **STAGE**: Starting stage: Feature Engineering

**[12:14:45]** (4.6min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[12:18:16]** (8.1min) ✅ **SUCCESS**: Feature engineering completed (211.2s) - Saved to BigQuery

**[12:18:18]** (8.2min) 📍 **STAGE**: Starting stage: Feature Selection

**[12:18:19]** (8.2min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[12:24:22]** (14.2min) ✅ **SUCCESS**: Feature selection completed (363.5s) - Selected features saved to BigQuery

**[12:24:24]** (14.3min) ℹ️ **INFO**: Using existing HMM model (11 days old < 30 day threshold)

**[12:24:26]** (14.3min) ℹ️ **INFO**: Using existing RF classifier (10 days old < 30 day threshold)

**[12:24:41]** (14.5min) 📍 **STAGE**: Starting stage: Forecasting

**[12:24:41]** (14.5min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[12:24:41]** (14.5min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

