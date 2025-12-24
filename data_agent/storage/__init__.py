#!/usr/bin/env python3
"""
Storage Module
Provides unified interface for data storage (local parquet or BigQuery)
"""

from .base import StorageBackend
from .local_storage import LocalStorage
from .bigquery_storage import BigQueryStorage


def get_storage(use_bigquery: bool = True, base_path: str = "outputs") -> StorageBackend:
    """
    Factory function to get storage backend

    Args:
        use_bigquery: If True, use BigQuery storage; if False, use local parquet
        base_path: Base directory for local storage (ignored for BigQuery)

    Returns:
        Storage backend instance (LocalStorage or BigQueryStorage)

    Examples:
        >>> # Use local parquet files
        >>> storage = get_storage(use_bigquery=False)
        >>> storage.save_raw_feature(df, 'GSPC', 'daily')

        >>> # Use BigQuery
        >>> storage = get_storage(use_bigquery=True)
        >>> storage.save_raw_feature(df, 'GSPC', 'daily')
    """
    if use_bigquery:
        return BigQueryStorage()
    else:
        return LocalStorage(base_path=base_path)


__all__ = [
    'StorageBackend',
    'LocalStorage',
    'BigQueryStorage',
    'get_storage'
]
