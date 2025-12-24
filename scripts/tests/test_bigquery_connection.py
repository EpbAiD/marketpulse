#!/usr/bin/env python3
"""
Test BigQuery Connection
Verify credentials and list existing datasets
"""

from google.cloud import bigquery
import os

# Set credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/eeshanbhanap/Desktop/RFP/regime01-b5321d26c433.json'

try:
    # Initialize client
    client = bigquery.Client(project='regime01')

    print("✅ Successfully connected to BigQuery!")
    print(f"📦 Project: {client.project}")
    print(f"📍 Location: {client.location or 'default'}")

    # List datasets
    print("\n📁 Existing Datasets:")
    datasets = list(client.list_datasets())

    if datasets:
        for dataset in datasets:
            print(f"  • {dataset.dataset_id}")

            # List tables in each dataset
            dataset_ref = client.dataset(dataset.dataset_id)
            tables = list(client.list_tables(dataset_ref))
            if tables:
                for table in tables:
                    print(f"    └─ {table.table_id}")
    else:
        print("  (No datasets found - we'll create them)")

    print("\n✅ Connection test successful!")

except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    import traceback
    traceback.print_exc()
