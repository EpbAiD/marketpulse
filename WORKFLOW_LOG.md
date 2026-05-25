# Workflow Execution Log

**Started**: 2026-05-25 14:12:39 UTC

---

**[14:12:39]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[14:13:27]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[14:14:49]** (2.2min) ✅ **SUCCESS**: Data fetch completed (129.9s) - Saved to BigQuery

**[14:14:52]** (2.2min) 📍 **STAGE**: Starting stage: Feature Engineering

**[14:14:52]** (2.2min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[14:17:19]** (4.7min) ✅ **SUCCESS**: Feature engineering completed (147.4s) - Saved to BigQuery

**[14:17:21]** (4.7min) 📍 **STAGE**: Starting stage: Feature Selection

**[14:17:22]** (4.7min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[14:23:36]** (11.0min) ✅ **SUCCESS**: Feature selection completed (375.2s) - Selected features saved to BigQuery

**[14:23:38]** (11.0min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[14:23:38]** (11.0min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[14:23:53]** (11.2min) ❌ **ERROR**: HMM clustering FAILED: cannot reindex on an axis with duplicate labels

**[14:24:09]** (11.5min) 📍 **STAGE**: Starting stage: Forecasting

**[14:24:09]** (11.5min) ℹ️ **INFO**: Selective training: 18 features (GSPC, IXIC, DXY, UUP, VIX...)

**[14:24:09]** (11.5min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

