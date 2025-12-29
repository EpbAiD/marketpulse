#!/usr/bin/env python3
"""
BigQuery Storage Backend
Implements storage using Google BigQuery with natural SQL queries
"""

import os
import pandas as pd
import yaml
import time
from google.cloud import bigquery
from typing import Optional
from pathlib import Path
from .base import StorageBackend


class BigQueryStorage(StorageBackend):
    """BigQuery cloud storage backend with SQL queries"""

    def __init__(self, config_path: str = "configs/bigquery_config.yaml"):
        """
        Initialize BigQuery storage

        Args:
            config_path: Path to BigQuery configuration file
        """
        # Load configuration
        config_file = Path(config_path)
        if not config_file.exists():
            # Try relative to project root
            config_file = Path(__file__).parent.parent.parent / config_path

        with open(config_file, "r") as f:
            self.config = yaml.safe_load(f)['bigquery']

        # Set credentials
        # Priority: 1) GitHub Actions secret (env var), 2) Local credentials file
        if 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ:
            # Running locally - use credentials file from config
            creds_path = self.config['credentials_path']
            if not os.path.isabs(creds_path):
                # Make relative to project root
                creds_path = str(Path(__file__).parent.parent.parent / creds_path)

            if os.path.exists(creds_path):
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
                print(f"✓ Using local BigQuery credentials: {creds_path}")
            else:
                raise FileNotFoundError(
                    f"BigQuery credentials not found at: {creds_path}\n"
                    "For local development: Ensure credentials file exists.\n"
                    "For GitHub Actions: Add GCP_CREDENTIALS secret."
                )
        else:
            print(f"✓ Using BigQuery credentials from environment (GitHub Actions)")

        # Initialize client
        self.client = bigquery.Client(project=self.config['project_id'])

        # Dataset reference
        self.dataset_id = f"{self.config['project_id']}.{self.config['dataset_id']}"

        # Retry settings
        self.max_retries = 3
        self.retry_delay = self.config.get('retry_delay', 5)

    def _retry_operation(self, operation, max_retries: Optional[int] = None):
        """Retry operation with exponential backoff"""
        max_retries = max_retries or self.max_retries

        for attempt in range(max_retries):
            try:
                return operation()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                print(f"⚠️  Retry {attempt + 1}/{max_retries} after error: {e}")
                time.sleep(self.retry_delay * (2 ** attempt))

    def _get_table_ref(self, table_name: str) -> str:
        """Get full table reference"""
        table = self.config['tables'].get(table_name, table_name)
        return f"{self.dataset_id}.{table}"

    def _execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute SQL query and return DataFrame

        Args:
            query: SQL query string

        Returns:
            DataFrame with results
        """
        def query_op():
            query_job = self.client.query(query)
            return query_job.to_dataframe()

        return self._retry_operation(query_op)

    # ========================================================================
    # SAVE METHODS
    # ========================================================================

    def save_raw_feature(
        self,
        df: pd.DataFrame,
        feature_name: str,
        cadence: str,
        incremental: bool = True
    ) -> None:
        """Save raw feature to BigQuery"""
        if incremental:
            # Check latest timestamp using SQL
            latest_ts = self.get_latest_timestamp(feature_name, cadence)

            if latest_ts:
                # Make timezone-naive for comparison
                latest_ts = pd.Timestamp(latest_ts).tz_localize(None)

                # Filter for new rows only
                new_rows = df[df.index > latest_ts]

                if new_rows.empty:
                    print(f"✅ BigQuery: Up to date (raw) → {feature_name}")
                    return

                df = new_rows
                print(f"📤 BigQuery: +{len(new_rows)} new rows (raw) → {feature_name}")
            else:
                print(f"📤 BigQuery: Initial upload ({len(df)} rows) → {feature_name}")

        # Prepare data
        data = df.reset_index()
        data['feature_name'] = feature_name
        data['cadence'] = cadence
        data['source'] = 'pipeline'
        data.columns = ['timestamp', 'value', 'feature_name', 'cadence', 'source']

        # Write to BigQuery
        table_ref = self._get_table_ref('raw_features')
        job_config = bigquery.LoadJobConfig(
            write_disposition='WRITE_APPEND',
            autodetect=True
        )

        def write_op():
            job = self.client.load_table_from_dataframe(
                data, table_ref, job_config=job_config
            )
            return job.result()

        self._retry_operation(write_op)

    def save_engineered_features(
        self,
        df: pd.DataFrame,
        feature_name: str,
        incremental: bool = True
    ) -> None:
        """Save engineered features to BigQuery using NARROW schema (EAV pattern)"""
        if incremental:
            # Check latest timestamp using SQL
            latest_ts = self._get_latest_engineered_timestamp(feature_name)

            if latest_ts:
                # Ensure both timestamps are timezone-naive for comparison
                latest_ts = pd.Timestamp(latest_ts).tz_localize(None)

                # If dataframe index is timezone-aware, make it naive
                if df.index.tz is not None:
                    df_index_naive = df.index.tz_localize(None)
                    df = df.copy()
                    df.index = df_index_naive

                new_rows = df[df.index > latest_ts]

                if new_rows.empty:
                    print(f"✅ BigQuery: Up to date (engineered) → {feature_name}")
                    return

                df = new_rows
                print(f"📤 BigQuery: +{len(new_rows)} new rows (engineered) → {feature_name}")
            else:
                print(f"📤 BigQuery: Initial upload ({len(df)} rows, engineered) → {feature_name}")

        # Convert WIDE format to NARROW format (EAV pattern)
        # Each column becomes a separate row with (base_feature, timestamp, derived_feature_name, value)
        data_rows = []

        for timestamp in df.index:
            for col in df.columns:
                value = df.loc[timestamp, col]
                data_rows.append({
                    'base_feature': feature_name,
                    'timestamp': timestamp,
                    'derived_feature_name': col,
                    'value': float(value) if pd.notna(value) else None
                })

        data = pd.DataFrame(data_rows)

        # Write to BigQuery
        table_ref = self._get_table_ref('engineered_features')
        job_config = bigquery.LoadJobConfig(
            write_disposition='WRITE_APPEND',
            autodetect=True
        )

        def write_op():
            job = self.client.load_table_from_dataframe(
                data, table_ref, job_config=job_config
            )
            return job.result()

        self._retry_operation(write_op)

    def save_aligned_dataset(self, df: pd.DataFrame) -> None:
        """Save aligned dataset (replace mode)"""
        # Prepare data
        data = df.copy()
        data = data.reset_index()

        # Rename index column
        index_col = data.columns[0]
        if index_col != 'timestamp':
            data = data.rename(columns={index_col: 'timestamp'})

        # Write to BigQuery (REPLACE mode)
        table_ref = self._get_table_ref('aligned_dataset')
        job_config = bigquery.LoadJobConfig(
            write_disposition='WRITE_TRUNCATE',
            autodetect=True
        )

        def write_op():
            job = self.client.load_table_from_dataframe(
                data, table_ref, job_config=job_config
            )
            return job.result()

        self._retry_operation(write_op)
        print(f"✅ BigQuery: Replaced aligned_dataset ({len(data)} rows)")

    def save_cluster_assignments(self, df: pd.DataFrame) -> None:
        """Save cluster assignments (replace mode)"""
        # Prepare data
        data = df.copy()
        data = data.reset_index()

        # Rename index column
        index_col = data.columns[0]
        if index_col != 'timestamp':
            data = data.rename(columns={index_col: 'timestamp'})

        # Write to BigQuery (REPLACE mode)
        table_ref = self._get_table_ref('cluster_assignments')
        job_config = bigquery.LoadJobConfig(
            write_disposition='WRITE_TRUNCATE',
            autodetect=True
        )

        def write_op():
            job = self.client.load_table_from_dataframe(
                data, table_ref, job_config=job_config
            )
            return job.result()

        self._retry_operation(write_op)
        print(f"✅ BigQuery: Replaced cluster_assignments ({len(data)} rows)")

    # ========================================================================
    # LOAD METHODS
    # ========================================================================

    def load_raw_feature(
        self,
        feature_name: str,
        cadence: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Load raw feature from BigQuery"""
        table_ref = self._get_table_ref('raw_features')

        # SQL query
        query = f"""
            SELECT
                timestamp,
                value
            FROM `{table_ref}`
            WHERE feature_name = '{feature_name}'
              AND cadence = '{cadence}'
            ORDER BY timestamp ASC
        """

        if limit:
            query += f"\nLIMIT {limit}"

        df = self._execute_query(query)

        if df.empty:
            return None

        # Set timestamp as index (ensure timezone-naive)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        df = df.set_index('timestamp')

        return df

    def load_engineered_features(
        self,
        feature_name: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Load engineered features from BigQuery (convert from NARROW to WIDE format)"""
        table_ref = self._get_table_ref('engineered_features')

        # SQL query - load NARROW format data
        query = f"""
            SELECT timestamp, derived_feature_name, value
            FROM `{table_ref}`
            WHERE base_feature = '{feature_name}'
            ORDER BY timestamp ASC, derived_feature_name ASC
        """

        if limit:
            # Note: limit applies to rows, not unique timestamps
            query += f"\nLIMIT {limit * 20}"  # Estimate ~20 derived features per base

        df_narrow = self._execute_query(query)

        if df_narrow.empty:
            return None

        # Convert from NARROW to WIDE format (pivot)
        df_narrow['timestamp'] = pd.to_datetime(df_narrow['timestamp']).dt.tz_localize(None)

        df_wide = df_narrow.pivot(
            index='timestamp',
            columns='derived_feature_name',
            values='value'
        )

        # Sort by timestamp
        df_wide = df_wide.sort_index()

        if limit:
            df_wide = df_wide.tail(limit)

        return df_wide

    def load_aligned_dataset(self) -> Optional[pd.DataFrame]:
        """Load aligned dataset from BigQuery"""
        table_ref = self._get_table_ref('aligned_dataset')

        # SQL query
        query = f"""
            SELECT *
            FROM `{table_ref}`
            ORDER BY timestamp ASC
        """

        df = self._execute_query(query)

        if df.empty:
            return None

        # Set timestamp as index (ensure timezone-naive)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        df = df.set_index('timestamp')

        return df

    def load_cluster_assignments(self) -> Optional[pd.DataFrame]:
        """Load cluster assignments from BigQuery"""
        table_ref = self._get_table_ref('cluster_assignments')

        # SQL query
        query = f"""
            SELECT *
            FROM `{table_ref}`
            ORDER BY timestamp ASC
        """

        df = self._execute_query(query)

        if df.empty:
            return None

        # Set timestamp as index (ensure timezone-naive)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        df = df.set_index('timestamp')

        return df

    # ========================================================================
    # UTILITY METHODS WITH SQL QUERIES
    # ========================================================================

    def get_latest_timestamp(
        self,
        feature_name: str,
        cadence: str
    ) -> Optional[pd.Timestamp]:
        """
        Get latest timestamp for a feature using SQL MAX() function

        Args:
            feature_name: Feature identifier
            cadence: Data frequency

        Returns:
            Latest timestamp or None if no data
        """
        query = f"""
            SELECT MAX(timestamp) as max_ts
            FROM `{self.dataset_id}.raw_features`
            WHERE feature_name = '{feature_name}'
              AND cadence = '{cadence}'
        """

        df = self._execute_query(query)

        if df.empty or df['max_ts'].isna().all():
            return None

        return pd.to_datetime(df['max_ts'].iloc[0])

    def _get_latest_engineered_timestamp(self, feature_name: str) -> Optional[pd.Timestamp]:
        """Get latest timestamp for engineered features using SQL"""
        query = f"""
            SELECT MAX(timestamp) as max_ts
            FROM `{self.dataset_id}.engineered_features`
            WHERE base_feature = '{feature_name}'
        """

        df = self._execute_query(query)

        if df.empty or df['max_ts'].isna().all():
            return None

        return pd.to_datetime(df['max_ts'].iloc[0])

    def feature_exists(self, feature_name: str, cadence: str) -> bool:
        """Check if feature exists using SQL COUNT()"""
        query = f"""
            SELECT COUNT(*) as cnt
            FROM `{self.dataset_id}.raw_features`
            WHERE feature_name = '{feature_name}'
              AND cadence = '{cadence}'
            LIMIT 1
        """

        df = self._execute_query(query)
        return not df.empty and df['cnt'].iloc[0] > 0

    # ========================================================================
    # ADDITIONAL SQL QUERIES FOR VALIDATION & STATISTICS
    # ========================================================================

    def validate_data_quality(self, feature_name: str, cadence: str) -> dict:
        """
        Validate data quality using SQL queries

        Returns:
            Dictionary with validation metrics
        """
        table_ref = self._get_table_ref('raw_features')

        # SQL query with aggregations
        query = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT timestamp) as unique_timestamps,
                MIN(timestamp) as earliest_date,
                MAX(timestamp) as latest_date,
                COUNT(value) as non_null_values,
                AVG(value) as avg_value,
                STDDEV(value) as std_value,
                MIN(value) as min_value,
                MAX(value) as max_value
            FROM `{table_ref}`
            WHERE feature_name = '{feature_name}'
              AND cadence = '{cadence}'
        """

        df = self._execute_query(query)

        if df.empty:
            return {}

        return df.iloc[0].to_dict()

    def get_regime_distribution(self) -> pd.DataFrame:
        """
        Get regime distribution using SQL GROUP BY

        Returns:
            DataFrame with regime counts and percentages
        """
        query = f"""
            SELECT
                regime,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
            FROM `{self.dataset_id}.cluster_assignments`
            GROUP BY regime
            ORDER BY regime
        """

        return self._execute_query(query)

    def get_feature_statistics_by_regime(self, feature_cols: list) -> pd.DataFrame:
        """
        Calculate feature statistics per regime using SQL

        Args:
            feature_cols: List of feature column names

        Returns:
            DataFrame with mean values per regime
        """
        # Build SQL with AVG() for each feature
        avg_cols = ', '.join([f'AVG({col}) as avg_{col}' for col in feature_cols])

        query = f"""
            SELECT
                regime,
                COUNT(*) as count,
                {avg_cols}
            FROM `{self.dataset_id}.cluster_assignments`
            GROUP BY regime
            ORDER BY regime
        """

        return self._execute_query(query)

    def get_data_freshness(self) -> pd.DataFrame:
        """
        Check data freshness for all features using SQL

        Returns:
            DataFrame with feature names and latest timestamps
        """
        query = f"""
            SELECT
                feature_name,
                cadence,
                MAX(timestamp) as latest_timestamp,
                COUNT(*) as total_rows,
                DATE_DIFF(CURRENT_DATE(), DATE(MAX(timestamp)), DAY) as days_since_update
            FROM `{self.dataset_id}.raw_features`
            GROUP BY feature_name, cadence
            ORDER BY feature_name, cadence
        """

        return self._execute_query(query)

    def count_rows_by_table(self) -> dict:
        """
        Count rows in each table using SQL

        Returns:
            Dictionary with table names and row counts
        """
        tables = ['raw_features', 'engineered_features', 'aligned_dataset', 'cluster_assignments']
        counts = {}

        for table in tables:
            query = f"""
                SELECT COUNT(*) as cnt
                FROM `{self.dataset_id}.{table}`
            """
            df = self._execute_query(query)
            counts[table] = df['cnt'].iloc[0] if not df.empty else 0

        return counts

    # ========================================================================
    # FORECAST TRACKING METHODS
    # ========================================================================

    def save_forecast(self, regime_df: pd.DataFrame, model_version: int = 1) -> str:
        """
        Save regime forecast to BigQuery regime_forecasts table
        
        Args:
            regime_df: DataFrame with columns [ds, regime, regime_probability]
            model_version: Model version number
            
        Returns:
            forecast_id: Unique identifier for this forecast
        """
        from datetime import datetime
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        forecast_id = f"forecast_{timestamp_str}"
        
        # Prepare forecast metadata
        forecast_start_date = pd.to_datetime(regime_df['ds']).min().date()
        forecast_end_date = pd.to_datetime(regime_df['ds']).max().date()
        horizon_days = len(regime_df)
        
        # Build rows for BigQuery
        rows = []
        for _, row in regime_df.iterrows():
            rows.append({
                'forecast_id': forecast_id,
                'forecast_generated_at': datetime.now(),
                'forecast_start_date': forecast_start_date,
                'forecast_end_date': forecast_end_date,
                'horizon_days': horizon_days,
                'predicted_date': pd.to_datetime(row['ds']).date(),
                'predicted_regime': int(row['regime']),
                'regime_probability': float(row.get('regime_probability', 0.0)),
                'model_version': model_version,
                'forecasting_models': 'Prophet,ARIMA,XGBoost,NeuralForecast',
                'validation_status': 'PENDING',
                'actual_regime': None,
                'is_correct': None,
                'validated_at': None
            })
        
        # Upload to BigQuery
        table_ref = self._get_table_ref('regime_forecasts')
        upload_df = pd.DataFrame(rows)
        
        job_config = bigquery.LoadJobConfig(write_disposition='WRITE_APPEND')
        
        def write_op():
            job = self.client.load_table_from_dataframe(
                upload_df, table_ref, job_config=job_config
            )
            return job.result()
        
        self._retry_operation(write_op)
        return forecast_id

    def get_latest_forecasts(self, limit: int = 10) -> pd.DataFrame:
        """Get latest N forecasts from BigQuery"""
        query = f"""
            SELECT
                forecast_id,
                MAX(forecast_generated_at) as forecast_generated_at,
                MAX(forecast_start_date) as forecast_start_date,
                MAX(forecast_end_date) as forecast_end_date,
                MAX(horizon_days) as horizon_days
            FROM `{self.dataset_id}.regime_forecasts`
            GROUP BY forecast_id
            ORDER BY forecast_generated_at DESC
            LIMIT {limit}
        """
        return self._execute_query(query)

    def get_forecast_by_id(self, forecast_id: str) -> Optional[pd.DataFrame]:
        """Load specific forecast by ID"""
        query = f"""
            SELECT
                predicted_date as ds,
                predicted_regime as regime,
                regime_probability,
                actual_regime,
                is_correct,
                validation_status
            FROM `{self.dataset_id}.regime_forecasts`
            WHERE forecast_id = '{forecast_id}'
            ORDER BY predicted_date
        """
        df = self._execute_query(query)
        return df if not df.empty else None

    def save_validation_results(self, validation_data: list) -> None:
        """
        Save SMAPE validation results to feature_validations table
        
        Args:
            validation_data: List of validation result dicts
        """
        if not validation_data:
            return
        
        table_ref = self._get_table_ref('feature_validations')
        upload_df = pd.DataFrame(validation_data)
        
        job_config = bigquery.LoadJobConfig(write_disposition='WRITE_APPEND')
        
        def write_op():
            job = self.client.load_table_from_dataframe(
                upload_df, table_ref, job_config=job_config
            )
            return job.result()
        
        self._retry_operation(write_op)

    def get_validation_metrics(self, days: int = 7) -> Optional[dict]:
        """Get latest validation metrics from BigQuery"""
        query = f"""
            SELECT
                AVG(overall_avg_smape) as avg_smape,
                MAX(needs_retraining) as needs_retraining,
                COUNT(DISTINCT forecast_id) as forecasts_validated
            FROM `{self.dataset_id}.feature_validations`
            WHERE validation_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        """
        try:
            df = self._execute_query(query)
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception:
            pass
        return None
