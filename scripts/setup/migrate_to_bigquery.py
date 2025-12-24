#!/usr/bin/env python3
"""
Migrate Existing Data to BigQuery
Uploads all parquet files from outputs/ to BigQuery tables
"""

import os
import pandas as pd
import glob
from bigquery_writer import BigQueryWriter
from tqdm import tqdm
import yaml


def get_cadence_from_config(feature_name: str) -> str:
    """Determine cadence for a feature from config"""
    with open("configs/features_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    for cadence in ['daily', 'weekly', 'monthly']:
        features = config.get(cadence, {}).get('features', [])
        if feature_name in features:
            return cadence

    return None


def migrate_raw_features():
    """Migrate outputs/fetched/cleaned/*.parquet to raw_features table"""
    print("\n" + "=" * 70)
    print("📦 Migrating Raw Features")
    print("=" * 70)

    writer = BigQueryWriter()
    raw_dir = "outputs/fetched/cleaned"

    if not os.path.exists(raw_dir):
        print(f"⚠️  Directory not found: {raw_dir}")
        return 0

    parquet_files = glob.glob(os.path.join(raw_dir, "*.parquet"))

    if not parquet_files:
        print(f"⚠️  No parquet files found in {raw_dir}")
        return 0

    print(f"Found {len(parquet_files)} feature files")

    uploaded = 0
    for file_path in tqdm(parquet_files, desc="Uploading features"):
        feature_name = os.path.splitext(os.path.basename(file_path))[0]

        # Get cadence from config
        cadence = get_cadence_from_config(feature_name)
        if not cadence:
            print(f"⚠️  Skipping {feature_name} - cadence not found in config")
            continue

        try:
            # Read parquet file
            df = pd.read_parquet(file_path)

            # Upload to BigQuery
            writer.write_raw_features(df, feature_name, cadence)
            uploaded += 1

        except Exception as e:
            print(f"❌ Error uploading {feature_name}: {e}")

    print(f"\n✅ Uploaded {uploaded}/{len(parquet_files)} features")
    return uploaded


def verify_upload():
    """Verify data was uploaded correctly"""
    print("\n" + "=" * 70)
    print("🔍 Verifying Upload")
    print("=" * 70)

    from bigquery_loader import BigQueryLoader
    loader = BigQueryLoader()

    # Count rows in BigQuery
    query = f"""
        SELECT
            cadence,
            COUNT(DISTINCT feature_name) as feature_count,
            COUNT(*) as row_count
        FROM `{loader.config['project_id']}.{loader.config['dataset_id']}.raw_features`
        GROUP BY cadence
        ORDER BY cadence
    """

    try:
        df = loader._execute_query(query)

        if df.empty:
            print("⚠️  No data found in BigQuery")
            return False

        print("\n📊 Data in BigQuery:")
        print(df.to_string(index=False))

        total_features = df['feature_count'].sum()
        total_rows = df['row_count'].sum()

        print(f"\n✅ Total: {total_features} features, {total_rows} data points")
        return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def compare_with_local():
    """Compare BigQuery data with local files"""
    print("\n" + "=" * 70)
    print("📊 Comparing Local vs BigQuery")
    print("=" * 70)

    from bigquery_loader import BigQueryLoader
    loader = BigQueryLoader()

    raw_dir = "outputs/fetched/cleaned"
    parquet_files = glob.glob(os.path.join(raw_dir, "*.parquet"))

    print(f"\nComparing {len(parquet_files)} files...")

    mismatches = []

    for file_path in parquet_files[:5]:  # Sample first 5
        feature_name = os.path.splitext(os.path.basename(file_path))[0]
        cadence = get_cadence_from_config(feature_name)

        if not cadence:
            continue

        # Read local
        df_local = pd.read_parquet(file_path)
        local_count = len(df_local)

        # Read from BigQuery
        try:
            df_bq = loader.fetch_feature(feature_name, cadence=cadence)
            bq_count = len(df_bq)

            match = "✅" if local_count == bq_count else "❌"
            print(f"{match} {feature_name}: Local={local_count}, BigQuery={bq_count}")

            if local_count != bq_count:
                mismatches.append((feature_name, local_count, bq_count))

        except Exception as e:
            print(f"❌ {feature_name}: Error - {e}")

    if mismatches:
        print(f"\n⚠️  {len(mismatches)} mismatches found")
        return False
    else:
        print("\n✅ All samples match!")
        return True


def main():
    print("\n" + "=" * 70)
    print("🚀 BIGQUERY DATA MIGRATION")
    print("=" * 70)
    print("\nThis will upload all local parquet files to BigQuery")
    print("Local files will NOT be deleted (dual mode)\n")

    # Step 1: Migrate raw features
    uploaded = migrate_raw_features()

    if uploaded == 0:
        print("\n❌ No data uploaded. Exiting.")
        return

    # Step 2: Verify upload
    verified = verify_upload()

    # Step 3: Compare sample
    if verified:
        compare_with_local()

    print("\n" + "=" * 70)
    print("✅ MIGRATION COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Test forecaster with BigQuery: python run_forecasting.py --use-bigquery")
    print("2. Check data in console: https://console.cloud.google.com/bigquery?project=regime01")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
