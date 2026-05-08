# Workflow Execution Log

**Started**: 2026-05-08 12:12:39 UTC

---

**[12:12:39]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[12:13:28]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[12:15:43]** (3.1min) ✅ **SUCCESS**: Data fetch completed (183.8s) - Saved to BigQuery

**[12:15:45]** (3.1min) 📍 **STAGE**: Starting stage: Feature Engineering

**[12:15:45]** (3.1min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[12:18:40]** (6.0min) ✅ **SUCCESS**: Feature engineering completed (175.4s) - Saved to BigQuery

**[12:18:42]** (6.0min) 📍 **STAGE**: Starting stage: Feature Selection

**[12:18:43]** (6.1min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[12:24:12]** (11.5min) ✅ **SUCCESS**: Feature selection completed (330.0s) - Selected features saved to BigQuery

**[12:24:13]** (11.6min) ℹ️ **INFO**: Using existing HMM model (14 days old < 30 day threshold)

**[12:24:15]** (11.6min) ℹ️ **INFO**: Using existing RF classifier (14 days old < 30 day threshold)

**[12:24:30]** (11.8min) 📍 **STAGE**: Starting stage: Forecasting

**[12:24:30]** (11.8min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[12:24:30]** (11.8min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

