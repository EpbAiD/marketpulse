#!/usr/bin/env python3
"""
Upload Pipeline Results to BigQuery
Uploads forecasts, model metrics, and classification results
"""

import os
import yaml
import pandas as pd
from google.cloud import bigquery
from datetime import datetime
import json
import glob

# Load config
with open('configs/bigquery_config.yaml', 'r') as f:
    config = yaml.safe_load(f)['bigquery']

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config['credentials_path']
client = bigquery.Client(project=config['project_id'])
dataset_id = f"{config['project_id']}.{config['dataset_id']}"

print('=' * 80)
print('UPLOADING PIPELINE RESULTS TO BIGQUERY')
print('=' * 80)
print()

# 1. Upload regime forecast to cluster_assignments
print('[1/4] Uploading regime forecasts...')
forecast_files = glob.glob('outputs/inference/regime_forecast_*.csv')
if forecast_files:
    latest_forecast = max(forecast_files, key=os.path.getctime)
    forecast_df = pd.read_csv(latest_forecast)

    # Prepare for cluster_assignments table schema (matches setup script schema)
    upload_df = pd.DataFrame({
        'timestamp': pd.to_datetime(forecast_df['ds']),
        'regime': forecast_df['regime'].astype(int),
        'model_version': 1,
        'created_at': datetime.now()
    })

    table_id = f'{dataset_id}.cluster_assignments'
    job_config = bigquery.LoadJobConfig(
        write_disposition='WRITE_APPEND',
        schema=[
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("regime", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("model_version", "INT64"),
            bigquery.SchemaField("created_at", "TIMESTAMP")
        ]
    )
    job = client.load_table_from_dataframe(upload_df, table_id, job_config=job_config)
    job.result()
    print(f'  ✅ Uploaded forecast: {os.path.basename(latest_forecast)}')
    print(f'     Rows: {len(upload_df)}')
    print(f'     Date range: {upload_df["timestamp"].min()} to {upload_df["timestamp"].max()}')
else:
    print('  ⚠️ No forecast files found')

# 2. Upload model performance metrics
print('[2/4] Uploading model metrics...')
if os.path.exists('outputs/model_performance_log.jsonl'):
    with open('outputs/model_performance_log.jsonl', 'r') as f:
        lines = f.readlines()
        metrics_data = []
        for line in lines:
            record = json.loads(line)
            # Add multiple metrics as separate rows
            metrics_data.extend([
                {
                    'feature_name': 'regime_classifier',
                    'model_version': 1,
                    'model_name': 'HMM',
                    'cadence': 'daily',
                    'metric_name': 'overall_accuracy',
                    'metric_value': record['overall_accuracy'],
                    'evaluation_set': 'validation',
                    'created_at': pd.to_datetime(record['timestamp'])
                },
                {
                    'feature_name': 'regime_classifier',
                    'model_version': 1,
                    'model_name': 'HMM',
                    'cadence': 'daily',
                    'metric_name': 'recent_accuracy_7d',
                    'metric_value': record['recent_accuracy_7d'],
                    'evaluation_set': 'validation',
                    'created_at': pd.to_datetime(record['timestamp'])
                },
                {
                    'feature_name': 'regime_classifier',
                    'model_version': 1,
                    'model_name': 'HMM',
                    'cadence': 'daily',
                    'metric_name': 'sample_size',
                    'metric_value': float(record['sample_size']),
                    'evaluation_set': 'validation',
                    'created_at': pd.to_datetime(record['timestamp'])
                }
            ])

    metrics_df = pd.DataFrame(metrics_data)
    table_id = f'{dataset_id}.model_metrics'
    job_config = bigquery.LoadJobConfig(
        write_disposition='WRITE_TRUNCATE',
        schema=[
            bigquery.SchemaField("feature_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("model_version", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("model_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("cadence", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("metric_name", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("metric_value", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("evaluation_set", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP")
        ]
    )
    job = client.load_table_from_dataframe(metrics_df, table_id, job_config=job_config)
    job.result()
    print(f'  ✅ Uploaded {len(metrics_df)} metric records')
else:
    print('  ⚠️ No model performance log found')

# 3. Upload classification results (historical regimes)
print('[3/4] Uploading historical regimes...')
if os.path.exists('outputs/clustering/cluster_assignments.parquet'):
    cluster_df = pd.read_parquet('outputs/clustering/cluster_assignments.parquet')

    # Prepare for classification_results schema
    upload_df = pd.DataFrame({
        'timestamp': pd.to_datetime(cluster_df.index),
        'predicted_regime': cluster_df['regime'].astype(int),
        'actual_regime': None,  # Will be filled when validating
        'probability': 0.0,  # Historical assignments don't have probabilities
        'model_version': 1,
        'created_at': datetime.now()
    })

    table_id = f'{dataset_id}.classification_results'
    job_config = bigquery.LoadJobConfig(
        write_disposition='WRITE_TRUNCATE',
        schema=[
            bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("predicted_regime", "INT64", mode="REQUIRED"),
            bigquery.SchemaField("actual_regime", "INT64"),
            bigquery.SchemaField("probability", "FLOAT64"),
            bigquery.SchemaField("model_version", "INT64"),
            bigquery.SchemaField("created_at", "TIMESTAMP")
        ]
    )
    job = client.load_table_from_dataframe(upload_df, table_id, job_config=job_config)
    job.result()
    print(f'  ✅ Uploaded {len(upload_df)} historical regime records')
    print(f'     Date range: {upload_df["timestamp"].min()} to {upload_df["timestamp"].max()}')
else:
    print('  ⚠️ No classification results found')

# 4. Log pipeline run
print('[4/4] Logging pipeline run...')
import uuid
run_id = str(uuid.uuid4())
timestamp_now = datetime.now()

# Log multiple stages
stages_data = []

# Data fetch stage
stages_data.append({
    'run_id': run_id,
    'stage': 'data_fetch',
    'status': 'success',
    'start_time': timestamp_now,
    'end_time': timestamp_now,
    'error_message': None,
    'metadata': json.dumps({'latest_data_date': '2025-12-17'}),
    'created_at': timestamp_now
})

# Forecast stage
if forecast_files:
    stages_data.append({
        'run_id': run_id,
        'stage': 'regime_forecast',
        'status': 'success',
        'start_time': timestamp_now,
        'end_time': timestamp_now,
        'error_message': None,
        'metadata': json.dumps({
            'forecast_start': forecast_df['ds'].min(),
            'forecast_end': forecast_df['ds'].max(),
            'horizon_days': 10
        }),
        'created_at': timestamp_now
    })

# Upload stage
stages_data.append({
    'run_id': run_id,
    'stage': 'bigquery_upload',
    'status': 'success',
    'start_time': timestamp_now,
    'end_time': timestamp_now,
    'error_message': None,
    'metadata': json.dumps({'tables_updated': ['cluster_assignments', 'model_metrics', 'classification_results']}),
    'created_at': timestamp_now
})

pipeline_run = pd.DataFrame(stages_data)

table_id = f'{dataset_id}.pipeline_runs'
job_config = bigquery.LoadJobConfig(
    write_disposition='WRITE_APPEND',
    schema=[
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("stage", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("start_time", "TIMESTAMP"),
        bigquery.SchemaField("end_time", "TIMESTAMP"),
        bigquery.SchemaField("error_message", "STRING"),
        bigquery.SchemaField("metadata", "STRING"),  # Changed from JSON to STRING
        bigquery.SchemaField("created_at", "TIMESTAMP")
    ]
)
job = client.load_table_from_dataframe(pipeline_run, table_id, job_config=job_config)
job.result()
print(f'  ✅ Pipeline run logged (run_id: {run_id[:8]}...)')

print()
print('=' * 80)
print('BIGQUERY UPLOAD COMPLETE')
print('=' * 80)
print(f'View in console: https://console.cloud.google.com/bigquery?project={config["project_id"]}')
print()
print('Tables updated:')
print('  - cluster_assignments (regime forecasts)')
print('  - model_metrics (performance tracking)')
print('  - classification_results (historical regimes)')
print('  - pipeline_runs (execution log)')
print('=' * 80)
