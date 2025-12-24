#!/usr/bin/env python3
"""
Local Storage Backend
Implements storage using local parquet files
"""

import os
import pandas as pd
from typing import Optional
from pathlib import Path
from .base import StorageBackend


class LocalStorage(StorageBackend):
    """Local parquet file storage backend"""

    def __init__(self, base_path: str = "outputs"):
        """
        Initialize local storage

        Args:
            base_path: Root directory for data files
        """
        self.base_path = Path(base_path)
        self.raw_path = self.base_path / "fetched" / "cleaned"
        self.engineered_path = self.base_path / "engineered"
        self.selected_path = self.base_path / "selected"
        self.clustering_path = self.base_path / "clustering"

        # Create directories
        for path in [self.raw_path, self.engineered_path, self.selected_path, self.clustering_path]:
            path.mkdir(parents=True, exist_ok=True)

    def save_raw_feature(
        self,
        df: pd.DataFrame,
        feature_name: str,
        cadence: str,
        incremental: bool = True
    ) -> None:
        """Save raw feature to parquet file"""
        filepath = self.raw_path / f"{feature_name}.parquet"

        if incremental and filepath.exists():
            # Load existing data
            existing_df = pd.read_parquet(filepath)

            # Find new rows (index is timestamp)
            new_rows = df[~df.index.isin(existing_df.index)]

            if not new_rows.empty:
                # Append and save
                combined_df = pd.concat([existing_df, new_rows]).sort_index()
                combined_df.to_parquet(filepath)
                print(f"💾 Local: +{len(new_rows)} new rows → {filepath.name}")
            else:
                print(f"✅ Local: Up to date → {filepath.name}")
        else:
            # First save or overwrite
            df.to_parquet(filepath)
            print(f"💾 Local: Saved {len(df)} rows → {filepath.name}")

    def save_engineered_features(
        self,
        df: pd.DataFrame,
        feature_name: str,
        incremental: bool = True
    ) -> None:
        """Save engineered features to parquet file"""
        filepath = self.engineered_path / f"{feature_name}.parquet"

        if incremental and filepath.exists():
            existing_df = pd.read_parquet(filepath)
            new_rows = df[~df.index.isin(existing_df.index)]

            if not new_rows.empty:
                combined_df = pd.concat([existing_df, new_rows]).sort_index()
                combined_df.to_parquet(filepath)
                print(f"💾 Local: +{len(new_rows)} new rows → {filepath.name}")
            else:
                print(f"✅ Local: Up to date → {filepath.name}")
        else:
            df.to_parquet(filepath)
            print(f"💾 Local: Saved {len(df)} rows → {filepath.name}")

    def save_aligned_dataset(self, df: pd.DataFrame) -> None:
        """Save aligned dataset (replace mode)"""
        filepath = self.selected_path / "aligned_dataset.parquet"
        df.to_parquet(filepath)
        print(f"💾 Local: Saved {len(df)} rows → {filepath.name}")

    def save_cluster_assignments(self, df: pd.DataFrame) -> None:
        """Save cluster assignments (replace mode)"""
        filepath = self.clustering_path / "cluster_assignments.parquet"
        df.to_parquet(filepath)
        print(f"💾 Local: Saved {len(df)} rows → {filepath.name}")

    def load_raw_feature(
        self,
        feature_name: str,
        cadence: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Load raw feature from parquet file"""
        filepath = self.raw_path / f"{feature_name}.parquet"

        if not filepath.exists():
            return None

        df = pd.read_parquet(filepath)

        if limit:
            df = df.tail(limit)

        return df

    def load_engineered_features(
        self,
        feature_name: str,
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Load engineered features from parquet file"""
        filepath = self.engineered_path / f"{feature_name}.parquet"

        if not filepath.exists():
            return None

        df = pd.read_parquet(filepath)

        if limit:
            df = df.tail(limit)

        return df

    def load_aligned_dataset(self) -> Optional[pd.DataFrame]:
        """Load aligned dataset"""
        filepath = self.selected_path / "aligned_dataset.parquet"

        if not filepath.exists():
            return None

        return pd.read_parquet(filepath)

    def load_cluster_assignments(self) -> Optional[pd.DataFrame]:
        """Load cluster assignments"""
        filepath = self.clustering_path / "cluster_assignments.parquet"

        if not filepath.exists():
            return None

        return pd.read_parquet(filepath)

    def get_latest_timestamp(
        self,
        feature_name: str,
        cadence: str
    ) -> Optional[pd.Timestamp]:
        """Get latest timestamp for a feature"""
        df = self.load_raw_feature(feature_name, cadence)

        if df is None or df.empty:
            return None

        return df.index.max()

    def feature_exists(self, feature_name: str, cadence: str) -> bool:
        """Check if feature file exists"""
        filepath = self.raw_path / f"{feature_name}.parquet"
        return filepath.exists()
