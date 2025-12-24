#!/usr/bin/env python3
"""
Base Storage Interface
Defines abstract interface for data storage backends (local, BigQuery)
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional, List


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    def save_raw_feature(
        self,
        df: pd.DataFrame,
        feature_name: str,
        cadence: str,
        incremental: bool = True
    ) -> None:
        """
        Save raw feature data

        Args:
            df: DataFrame with timestamp index and 'value' column
            feature_name: Feature identifier (e.g., 'GSPC', 'VIX')
            cadence: Data frequency ('daily', 'weekly', 'monthly')
            incremental: If True, only save new rows not already in storage
        """
        pass

    @abstractmethod
    def save_engineered_features(
        self,
        df: pd.DataFrame,
        feature_name: str,
        incremental: bool = True
    ) -> None:
        """
        Save engineered features (returns, volatility, z-scores, etc.)

        Args:
            df: DataFrame with timestamp index and derived feature columns
            feature_name: Base feature identifier
            incremental: If True, only save new rows
        """
        pass

    @abstractmethod
    def save_aligned_dataset(self, df: pd.DataFrame) -> None:
        """
        Save aligned dataset (selected features after PCA/mRMR)

        Args:
            df: DataFrame with timestamp index and selected feature columns
        """
        pass

    @abstractmethod
    def save_cluster_assignments(self, df: pd.DataFrame) -> None:
        """
        Save cluster/regime assignments

        Args:
            df: DataFrame with timestamp index, 'regime' column, and feature columns
        """
        pass

    @abstractmethod
    def load_raw_feature(
        self,
        feature_name: str,
        cadence: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Load raw feature data

        Args:
            feature_name: Feature identifier
            cadence: Data frequency
            limit: Maximum number of rows to return (most recent)

        Returns:
            DataFrame with timestamp index and 'value' column, or None if not found
        """
        pass

    @abstractmethod
    def load_engineered_features(
        self,
        feature_name: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Load engineered features

        Args:
            feature_name: Base feature identifier
            limit: Maximum number of rows to return

        Returns:
            DataFrame with timestamp index and derived feature columns, or None if not found
        """
        pass

    @abstractmethod
    def load_aligned_dataset(self) -> Optional[pd.DataFrame]:
        """
        Load aligned dataset

        Returns:
            DataFrame with timestamp index and selected features, or None if not found
        """
        pass

    @abstractmethod
    def load_cluster_assignments(self) -> Optional[pd.DataFrame]:
        """
        Load cluster assignments

        Returns:
            DataFrame with timestamp index, regime column, and features, or None if not found
        """
        pass

    @abstractmethod
    def get_latest_timestamp(
        self,
        feature_name: str,
        cadence: str
    ) -> Optional[pd.Timestamp]:
        """
        Get latest timestamp for a feature

        Args:
            feature_name: Feature identifier
            cadence: Data frequency

        Returns:
            Latest timestamp or None if no data exists
        """
        pass

    @abstractmethod
    def feature_exists(self, feature_name: str, cadence: str) -> bool:
        """
        Check if feature data exists

        Args:
            feature_name: Feature identifier
            cadence: Data frequency

        Returns:
            True if feature exists, False otherwise
        """
        pass
