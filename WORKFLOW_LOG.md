# Workflow Execution Log

**Started**: 2026-05-27 14:31:05 UTC

---

**[14:31:05]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[14:32:00]** (0.9min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[14:33:52]** (2.8min) ✅ **SUCCESS**: Data fetch completed (166.5s) - Saved to BigQuery

**[14:33:54]** (2.8min) 📍 **STAGE**: Starting stage: Feature Engineering

**[14:33:54]** (2.8min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[14:36:51]** (5.8min) ✅ **SUCCESS**: Feature engineering completed (177.0s) - Saved to BigQuery

**[14:36:53]** (5.8min) 📍 **STAGE**: Starting stage: Feature Selection

**[14:36:54]** (5.8min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[14:42:59]** (11.9min) ✅ **SUCCESS**: Feature selection completed (365.5s) - Selected features saved to BigQuery

**[14:43:00]** (11.9min) ℹ️ **INFO**: Using existing HMM model (2 days old < 30 day threshold)

**[14:43:02]** (11.9min) ℹ️ **INFO**: Using existing RF classifier (0 days old < 30 day threshold)

**[14:43:19]** (12.2min) 📍 **STAGE**: Starting stage: Forecasting

**[14:43:19]** (12.2min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[14:43:19]** (12.2min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

