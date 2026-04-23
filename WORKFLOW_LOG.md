# Workflow Execution Log

**Started**: 2026-04-23 19:25:00 UTC

---

**[19:25:00]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[19:25:48]** (0.8min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[19:27:01]** (2.0min) ✅ **SUCCESS**: Data fetch completed (121.0s) - Saved to BigQuery

**[19:27:03]** (2.1min) 📍 **STAGE**: Starting stage: Feature Engineering

**[19:27:03]** (2.1min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[19:27:05]** (2.1min) ❌ **ERROR**: Feature engineering FAILED: 403 Access Denied: Table regime01:forecasting_pipeline.raw_features: User does not have permission to query table regime01:forecasting_pipeline.raw_features, or perhaps it does not exist.; reason: accessDenied, message: Access Denied: Table regime01:forecasting_pipeline.raw_features: User does not have permission to query table regime01:forecasting_pipeline.raw_features, or perhaps it does not exist.

Location: us-central1
Job ID: 01b6fac3-fc47-4df8-883b-cb752dd7947f


**[19:27:21]** (2.4min) 📍 **STAGE**: Starting stage: Forecasting

**[19:27:21]** (2.4min) ℹ️ **INFO**: Training all feature models

**[19:27:21]** (2.4min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

