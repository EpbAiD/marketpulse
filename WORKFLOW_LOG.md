# Workflow Execution Log

**Started**: 2026-06-26 13:16:09 UTC

---

**[13:16:09]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[13:16:59]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[13:20:36]** (4.5min) ✅ **SUCCESS**: Data fetch completed (267.3s) - Saved to BigQuery

**[13:20:39]** (4.5min) 📍 **STAGE**: Starting stage: Feature Engineering

**[13:20:39]** (4.5min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[13:25:15]** (9.1min) ✅ **SUCCESS**: Feature engineering completed (276.1s) - Saved to BigQuery

**[13:25:17]** (9.1min) 📍 **STAGE**: Starting stage: Feature Selection

**[13:25:18]** (9.2min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[13:31:32]** (15.4min) ✅ **SUCCESS**: Feature selection completed (374.4s) - Selected features saved to BigQuery

**[13:31:34]** (15.4min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[13:31:34]** (15.4min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[13:31:46]** (15.6min) ❌ **ERROR**: HMM clustering FAILED: cannot reindex on an axis with duplicate labels

**[13:32:02]** (15.9min) 📍 **STAGE**: Starting stage: Forecasting

**[13:32:02]** (15.9min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[13:32:02]** (15.9min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

