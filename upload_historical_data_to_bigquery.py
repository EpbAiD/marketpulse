#!/usr/bin/env python3
"""
Upload historical cluster assignments and market data to BigQuery
This enables the Streamlit Cloud dashboard to display full visualizations
"""

import pandas as pd
from pathlib import Path
from data_agent.storage import get_storage

def upload_cluster_assignments():
    """Upload historical cluster assignments to BigQuery"""
    print("📤 Uploading cluster assignments to BigQuery...")

    cluster_file = Path("outputs/clustering/cluster_assignments.parquet")
    if not cluster_file.exists():
        print("⚠️  No cluster assignments file found")
        return

    df = pd.read_parquet(cluster_file)

    # Reset index to get timestamp as column
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        df.rename(columns={df.columns[0]: 'timestamp'}, inplace=True)

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    storage = get_storage(use_bigquery=True)

    # Save to BigQuery cluster_assignments table
    from google.cloud import bigquery
    table_ref = storage._get_table_ref('cluster_assignments')

    job_config = bigquery.LoadJobConfig(
        write_disposition='WRITE_TRUNCATE',  # Replace existing data
        autodetect=True
    )

    job = storage.client.load_table_from_dataframe(
        df, table_ref, job_config=job_config
    )
    result = job.result()

    print(f"✅ Uploaded {len(df)} cluster assignment rows to BigQuery")

def upload_market_data():
    """Upload market data files to BigQuery raw_features table"""
    print("\n📤 Uploading market data to BigQuery...")

    market_dir = Path("outputs/fetched/cleaned")
    if not market_dir.exists():
        print("⚠️  No market data directory found")
        return

    storage = get_storage(use_bigquery=True)

    for file in market_dir.glob("*.parquet"):
        feature_name = file.stem
        print(f"  Uploading {feature_name}...")

        df = pd.read_parquet(file)

        # Save using the storage layer's method
        storage.save_raw_feature(df, feature_name, 'daily', incremental=False)

    print(f"✅ Uploaded market data to BigQuery")

if __name__ == "__main__":
    print("🚀 Uploading historical data to BigQuery for Streamlit Cloud dashboard\n")

    upload_cluster_assignments()
    upload_market_data()

    print("\n✅ Upload complete! Streamlit Cloud dashboard will now show full visualizations.")
    print("   Refresh the dashboard to see historical regime analysis and market data.")
