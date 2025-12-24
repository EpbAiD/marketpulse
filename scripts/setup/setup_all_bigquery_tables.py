#!/usr/bin/env python3
"""
Master BigQuery Setup Script
=============================
Creates ALL required tables for the Market Regime Forecasting System.

Consolidates:
- setup_bigquery_tables.py (basic tables)
- setup_additional_bigquery_tables.py (engineered features, aligned dataset)
- setup_forecast_tracking_tables.py (regime forecasts, validations)

Usage:
    python scripts/setup/setup_all_bigquery_tables.py
"""

import os
import yaml
from google.cloud import bigquery
from pathlib import Path

# Load config
config_path = Path(__file__).parent.parent.parent / "configs" / "bigquery_config.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)['bigquery']

# Set credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['credentials_path']

# Initialize client
client = bigquery.Client(project=config['project_id'])
dataset_id = f"{config['project_id']}.{config['dataset_id']}"

print("=" * 80)
print("🚀 BIGQUERY SETUP - MARKET REGIME FORECASTING SYSTEM")
print("=" * 80)
print(f"Project: {config['project_id']}")
print(f"Dataset: {config['dataset_id']}")
print(f"Location: {config['location']}")
print("=" * 80)

# ============================================================================
# STEP 1: Create Dataset
# ============================================================================
print("\n📦 [1/9] Creating dataset...")
dataset = bigquery.Dataset(dataset_id)
dataset.location = config['location']
dataset = client.create_dataset(dataset, exists_ok=True)
print(f"✅ Dataset ready: {dataset_id}")

# ============================================================================
# STEP 2: Raw Features Table
# ============================================================================
print("\n📊 [2/9] Creating raw_features table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.raw_features` (
        feature_name STRING NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        value FLOAT64 NOT NULL,
        cadence STRING NOT NULL,
        source STRING,
        ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY TIMESTAMP_TRUNC(timestamp, MONTH)
    CLUSTER BY feature_name, cadence
""").result()
print("✅ raw_features table created")

# ============================================================================
# STEP 3: Engineered Features Table
# ============================================================================
print("\n📊 [3/9] Creating engineered_features table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.engineered_features` (
        feature_name STRING NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        value FLOAT64 NOT NULL,
        base_feature STRING,
        transformation STRING,
        ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY TIMESTAMP_TRUNC(timestamp, MONTH)
    CLUSTER BY feature_name
""").result()
print("✅ engineered_features table created")

# ============================================================================
# STEP 4: Selected Features Table
# ============================================================================
print("\n📊 [4/9] Creating selected_features table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.selected_features` (
        feature_name STRING NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        value FLOAT64 NOT NULL,
        selection_method STRING,
        importance_score FLOAT64,
        ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY TIMESTAMP_TRUNC(timestamp, MONTH)
    CLUSTER BY feature_name
""").result()
print("✅ selected_features table created")

# ============================================================================
# STEP 5: Aligned Dataset Table
# ============================================================================
print("\n📊 [5/9] Creating aligned_dataset table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.aligned_dataset` (
        timestamp TIMESTAMP NOT NULL,
        feature_name STRING NOT NULL,
        value FLOAT64 NOT NULL,
        ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY TIMESTAMP_TRUNC(timestamp, MONTH)
    CLUSTER BY feature_name
""").result()
print("✅ aligned_dataset table created")

# ============================================================================
# STEP 6: Cluster Assignments Table
# ============================================================================
print("\n📊 [6/9] Creating cluster_assignments table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.cluster_assignments` (
        timestamp TIMESTAMP NOT NULL,
        cluster_id INT64 NOT NULL,
        cluster_label STRING,
        probability FLOAT64,
        model_version STRING,
        ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY TIMESTAMP_TRUNC(timestamp, MONTH)
    CLUSTER BY cluster_id
""").result()
print("✅ cluster_assignments table created")

# ============================================================================
# STEP 7: Regime Forecasts Table
# ============================================================================
print("\n📊 [7/9] Creating regime_forecasts table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.regime_forecasts` (
        -- Forecast metadata
        forecast_id STRING NOT NULL,
        forecast_generated_at TIMESTAMP NOT NULL,
        forecast_start_date DATE NOT NULL,
        forecast_end_date DATE NOT NULL,
        horizon_days INT64 NOT NULL,

        -- Individual prediction
        predicted_date DATE NOT NULL,
        predicted_regime INT64 NOT NULL,
        regime_probability FLOAT64 NOT NULL,

        -- Model info
        model_version INT64 DEFAULT 1,
        model_type STRING,

        -- Validation status
        validation_status STRING DEFAULT 'PENDING',
        actual_regime INT64,
        validation_smape FLOAT64,
        validation_timestamp TIMESTAMP,

        -- Metadata
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY forecast_start_date
    CLUSTER BY forecast_id, predicted_regime
""").result()
print("✅ regime_forecasts table created")

# ============================================================================
# STEP 8: Feature Validations Table
# ============================================================================
print("\n📊 [8/9] Creating feature_validations table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.feature_validations` (
        validation_id STRING NOT NULL,
        validation_timestamp TIMESTAMP NOT NULL,
        forecast_id STRING NOT NULL,
        forecast_generated_at TIMESTAMP NOT NULL,
        feature_name STRING NOT NULL,
        avg_smape FLOAT64 NOT NULL,
        smape_threshold FLOAT64 NOT NULL,
        exceeds_threshold BOOL NOT NULL,
        comparisons INT64 NOT NULL,
        overall_avg_smape FLOAT64,
        needs_retraining BOOL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY DATE(validation_timestamp)
    CLUSTER BY forecast_id, feature_name
""").result()
print("✅ feature_validations table created")

# ============================================================================
# STEP 9: Forecast Results Table (Legacy/Optional)
# ============================================================================
print("\n📊 [9/9] Creating forecast_results table...")
client.query(f"""
    CREATE TABLE IF NOT EXISTS `{dataset_id}.forecast_results` (
        feature_name STRING NOT NULL,
        forecast_date DATE NOT NULL,
        horizon_days INT64 NOT NULL,
        predicted_value FLOAT64 NOT NULL,
        confidence_lower FLOAT64,
        confidence_upper FLOAT64,
        model_type STRING,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY forecast_date
    CLUSTER BY feature_name, model_type
""").result()
print("✅ forecast_results table created")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("✅ ALL BIGQUERY TABLES CREATED SUCCESSFULLY")
print("=" * 80)
print("\nTables created:")
print("  1. raw_features          - Raw market data from Yahoo/FRED")
print("  2. engineered_features   - Derived features (returns, volatility, etc.)")
print("  3. selected_features     - PCA+mRMR selected features")
print("  4. aligned_dataset       - Time-aligned feature matrix")
print("  5. cluster_assignments   - HMM regime assignments")
print("  6. regime_forecasts      - Daily regime predictions")
print("  7. feature_validations   - SMAPE-based forecast validation")
print("  8. forecast_results      - Raw feature forecasts (legacy)")
print("\nDataset: " + dataset_id)
print("=" * 80 + "\n")
