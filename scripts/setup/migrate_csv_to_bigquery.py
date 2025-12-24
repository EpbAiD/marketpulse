#!/usr/bin/env python3
"""
Migrate Existing CSV Forecasts to BigQuery

Reads all regime_forecast_*.csv files from outputs/inference/
and inserts them into BigQuery regime_forecasts table.

This allows testing the BigQuery system with existing data.
"""

import os
import yaml
import pandas as pd
import glob
from pathlib import Path
from datetime import datetime
from google.cloud import bigquery


def migrate_forecasts():
    """Migrate all CSV forecasts to BigQuery"""

    print("=" * 80)
    print("MIGRATING CSV FORECASTS TO BIGQUERY")
    print("=" * 80)

    # Load config
    with open("configs/bigquery_config.yaml") as f:
        config = yaml.safe_load(f)['bigquery']

    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['credentials_path']
    client = bigquery.Client(project=config['project_id'])
    dataset_id = f"{config['project_id']}.{config['dataset_id']}"
    table_ref = f"{dataset_id}.regime_forecasts"

    # Find all CSV forecast files
    forecast_files = glob.glob("outputs/inference/regime_forecast_*.csv")
    forecast_files = [f for f in forecast_files if not f.endswith('_metadata.json')]
    forecast_files.sort()

    print(f"\n📁 Found {len(forecast_files)} forecast files to migrate")

    if len(forecast_files) == 0:
        print("   No forecast files found. Generate forecasts first.")
        return

    total_rows = 0
    migrated_forecasts = 0

    for idx, file_path in enumerate(forecast_files, 1):
        filename = Path(file_path).name

        # Extract timestamp from filename: regime_forecast_20251219_001228.csv
        try:
            timestamp_str = filename.replace('regime_forecast_', '').replace('.csv', '')
            # Parse: YYYYMMDD_HHMMSS
            forecast_generated_at = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            forecast_id = f"forecast_{timestamp_str}"
        except Exception as e:
            print(f"   ⚠️  Skipping {filename}: Cannot parse timestamp ({e})")
            continue

        print(f"\n[{idx}/{len(forecast_files)}] Migrating {filename}...")
        print(f"   Forecast ID: {forecast_id}")
        print(f"   Generated at: {forecast_generated_at}")

        # Load CSV
        try:
            df = pd.read_csv(file_path)

            # Check if already migrated
            check_query = f"""
                SELECT COUNT(*) as count
                FROM `{table_ref}`
                WHERE forecast_id = '{forecast_id}'
            """
            result = client.query(check_query).to_dataframe()

            if result['count'].iloc[0] > 0:
                print(f"   ℹ️  Already migrated ({result['count'].iloc[0]} rows), skipping")
                continue

            # Validate required columns
            if 'ds' not in df.columns or 'regime' not in df.columns:
                print(f"   ⚠️  Skipping: Missing required columns (ds, regime)")
                continue

            # Build forecast metadata
            forecast_start_date = pd.to_datetime(df['ds']).min()
            forecast_end_date = pd.to_datetime(df['ds']).max()
            horizon_days = len(df)

            # Build rows for BigQuery
            rows = []
            for _, row in df.iterrows():
                rows.append({
                    'forecast_id': forecast_id,
                    'forecast_generated_at': forecast_generated_at,
                    'forecast_start_date': forecast_start_date.date(),
                    'forecast_end_date': forecast_end_date.date(),
                    'horizon_days': horizon_days,
                    'predicted_date': pd.to_datetime(row['ds']).date(),
                    'predicted_regime': int(row['regime']),
                    'regime_probability': float(row.get('regime_probability', 0.0)),
                    'model_version': 1,
                    'forecasting_models': 'Prophet,ARIMA,XGBoost,NeuralForecast',
                    'validation_status': 'PENDING',
                    'actual_regime': None,
                    'is_correct': None,
                    'validated_at': None
                })

            # Upload to BigQuery
            upload_df = pd.DataFrame(rows)
            job_config = bigquery.LoadJobConfig(write_disposition='WRITE_APPEND')
            job = client.load_table_from_dataframe(upload_df, table_ref, job_config=job_config)
            job.result()

            print(f"   ✅ Migrated {len(rows)} rows")
            total_rows += len(rows)
            migrated_forecasts += 1

        except Exception as e:
            print(f"   ❌ Error: {e}")
            continue

    print("\n" + "=" * 80)
    print("✅ MIGRATION COMPLETE")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   Total files processed: {len(forecast_files)}")
    print(f"   Successfully migrated: {migrated_forecasts}")
    print(f"   Total rows inserted: {total_rows}")

    # Verify migration
    print(f"\n🔍 Verifying migration...")
    verify_query = f"""
        SELECT
            COUNT(DISTINCT forecast_id) as total_forecasts,
            COUNT(*) as total_predictions,
            MIN(forecast_generated_at) as first_forecast,
            MAX(forecast_generated_at) as latest_forecast
        FROM `{table_ref}`
    """
    result = client.query(verify_query).to_dataframe()

    print(f"   Total forecasts in BigQuery: {result['total_forecasts'].iloc[0]}")
    print(f"   Total predictions: {result['total_predictions'].iloc[0]}")
    print(f"   First forecast: {result['first_forecast'].iloc[0]}")
    print(f"   Latest forecast: {result['latest_forecast'].iloc[0]}")

    print("\n🔗 View in BigQuery Console:")
    print(f"   https://console.cloud.google.com/bigquery?project={config['project_id']}")
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    migrate_forecasts()
