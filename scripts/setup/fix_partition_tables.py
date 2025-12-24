#!/usr/bin/env python3
"""
Fix BigQuery Tables - Change to MONTH Partitioning
Recreates tables with MONTH partitioning instead of DAY to avoid 4000 partition limit
"""

import os
import yaml
from google.cloud import bigquery

# Load config
with open("configs/bigquery_config.yaml", "r") as f:
    config = yaml.safe_load(f)['bigquery']

# Set credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['credentials_path']

# Initialize client
client = bigquery.Client(project=config['project_id'])
dataset_id = f"{config['project_id']}.{config['dataset_id']}"

print("=" * 70)
print("🔧 Fixing BigQuery Tables - Switching to MONTH Partitioning")
print("=" * 70)

# ============================================================================
# Fix 1: raw_features
# ============================================================================
print("\n📊 Recreating raw_features with MONTH partitioning...")

table_ref = f"{dataset_id}.raw_features"
try:
    client.delete_table(table_ref, not_found_ok=True)
    print(f"   ✅ Deleted old table")
except Exception as e:
    print(f"   ⚠️  {e}")

schema = [
    bigquery.SchemaField("feature_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("cadence", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("value", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("source", "STRING", mode="NULLABLE"),
]

table = bigquery.Table(table_ref, schema=schema)
table.time_partitioning = bigquery.TimePartitioning(
    type_=bigquery.TimePartitioningType.MONTH,  # ← MONTH instead of DAY
    field="timestamp"
)
table.clustering_fields = ["feature_name", "cadence"]

client.create_table(table)
print(f"✅ Created: {table_ref}")
print(f"   Partitioned by: MONTH(timestamp)")
print(f"   Clustered by: feature_name, cadence")

# ============================================================================
# Fix 2: engineered_features
# ============================================================================
print("\n📊 Recreating engineered_features with MONTH partitioning...")

table_ref = f"{dataset_id}.engineered_features"
try:
    client.delete_table(table_ref, not_found_ok=True)
    print(f"   ✅ Deleted old table")
except Exception as e:
    print(f"   ⚠️  {e}")

schema = [
    bigquery.SchemaField("feature_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("base_value", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ret", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ret_5d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ret_10d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ret_21d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("ret_63d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("rv_21d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("rv_63d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("z_21d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("z_63d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("dd_21d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("dd_63d", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("yoy", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("mom", "FLOAT64", mode="NULLABLE"),
]

table = bigquery.Table(table_ref, schema=schema)
table.time_partitioning = bigquery.TimePartitioning(
    type_=bigquery.TimePartitioningType.MONTH,  # ← MONTH instead of DAY
    field="timestamp"
)
table.clustering_fields = ["feature_name"]

client.create_table(table)
print(f"✅ Created: {table_ref}")
print(f"   Partitioned by: MONTH(timestamp)")
print(f"   Clustered by: feature_name")

# ============================================================================
# Fix 3: aligned_dataset
# ============================================================================
print("\n📊 Recreating aligned_dataset with MONTH partitioning...")

table_ref = f"{dataset_id}.aligned_dataset"
try:
    client.delete_table(table_ref, not_found_ok=True)
    print(f"   ✅ Deleted old table")
except Exception as e:
    print(f"   ⚠️  {e}")

schema = [
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
]

table = bigquery.Table(table_ref, schema=schema)
table.time_partitioning = bigquery.TimePartitioning(
    type_=bigquery.TimePartitioningType.MONTH,  # ← MONTH instead of DAY
    field="timestamp"
)

client.create_table(table)
print(f"✅ Created: {table_ref}")
print(f"   Partitioned by: MONTH(timestamp)")

# ============================================================================
# Fix 4: cluster_assignments
# ============================================================================
print("\n📊 Recreating cluster_assignments with MONTH partitioning...")

table_ref = f"{dataset_id}.cluster_assignments"
try:
    client.delete_table(table_ref, not_found_ok=True)
    print(f"   ✅ Deleted old table")
except Exception as e:
    print(f"   ⚠️  {e}")

schema = [
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("regime", "INT64", mode="NULLABLE"),
]

table = bigquery.Table(table_ref, schema=schema)
table.time_partitioning = bigquery.TimePartitioning(
    type_=bigquery.TimePartitioningType.MONTH,  # ← MONTH instead of DAY
    field="timestamp"
)

client.create_table(table)
print(f"✅ Created: {table_ref}")
print(f"   Partitioned by: MONTH(timestamp)")

print("\n" + "=" * 70)
print("✅ All Tables Recreated with MONTH Partitioning!")
print("=" * 70)
print("\n📋 Summary:")
print("   • Can now handle 4,000 months = 333 years of data")
print("   • Our 35 years (420 months) fits easily!")
print("   • Ready for full historical data upload")
print("=" * 70 + "\n")
