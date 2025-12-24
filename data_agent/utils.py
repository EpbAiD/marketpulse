#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils.py
=============================================================
Common data utilities for RFP DataAgent:
- Missingness detection and cause analysis
- Imputation handling (with configurable policy)
- Instant diagnostics / console + CSV logging
- Lightweight visualizations
- Universal lexical normalization for feature names
- Safe numeric sanitization for infinities / NaNs
=============================================================
"""

import os
import re
import unicodedata
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# 🔧 Directory & Math Utilities
# ============================================================
def ensure_dir(path: str):
    """Ensure directory exists."""
    os.makedirs(path, exist_ok=True)


def pct(n, d):
    """Safe percentage calculation."""
    return 0 if d == 0 else 100.0 * n / d


# ============================================================
# 🧠 UNIVERSAL NORMALIZATION HELPERS
# ============================================================
def normalize_text(value: str) -> str:
    """
    General text normalizer:
    - Converts to string
    - Strips whitespace and special chars
    - Replaces all non-alphanumeric characters with '_'
    - Collapses multiple underscores
    - Ensures uppercase standardized representation
    """
    if value is None:
        return "UNKNOWN"
    s = str(value).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").upper()


def normalize_symbol(symbol: str) -> str:
    """
    Symbol-level normalization:
    - Removes carets, spaces, and punctuation
    - Applies generic normalize_text()
    - Works for any source (Yahoo, FRED, local CSVs)
    """
    if symbol is None:
        return "UNKNOWN"
    s = str(symbol).replace("^", "").strip()
    return normalize_text(s)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures all column names are plain strings and normalized.
    - Converts MultiIndex columns into flattened 'A_B' strings
    - Applies normalize_text() to each resulting name
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(map(str, col)).strip() for col in df.columns.values]
    df.columns = [normalize_text(c) for c in df.columns]
    return df


def enforce_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Final defensive layer:
    Ensures all columns are strings for ML and downstream pipelines.
    """
    df.columns = df.columns.astype(str)
    return df


# ============================================================
# 📊 Data Diagnostics
# ============================================================
def detect_missingness(df: pd.DataFrame, name: str, outdir: str):
    """
    Detect missing values and save summary CSV + heatmap.
    Automatically normalizes `name` for filesystem safety.
    """
    ensure_dir(outdir)
    safe_name = normalize_symbol(name)

    # Count missing values
    miss_df = df.isna().sum().to_frame("null_count")
    miss_df["null_percent"] = miss_df["null_count"].apply(lambda x: pct(x, len(df)))
    miss_df = miss_df.sort_values("null_percent", ascending=False)

    csv_path = os.path.join(outdir, f"{safe_name}_null_summary.csv")
    miss_df.to_csv(csv_path)
    print(f"🧮 Missingness summary saved → {csv_path}")

    # Heatmap (robust for single-column inputs)
    plt.figure(figsize=(10, 3))
    plt.imshow(df.isna().T, aspect='auto', cmap='gray_r')
    plt.title(f"{safe_name} — Missingness Map")
    plt.yticks(range(len(df.columns)), df.columns)
    plt.xlabel("Rows")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{safe_name}_missing_heatmap.png"), dpi=150)
    plt.close()


# ============================================================
# 🔄 Imputation
# ============================================================
def impute(df: pd.DataFrame, method: str = "ffill_bfill") -> pd.DataFrame:
    """Central imputation handler, shared across all pipeline stages."""
    if method == "ffill_bfill":
        return df.ffill().bfill()
    elif method == "interpolate":
        return df.interpolate(method="time").ffill().bfill()
    elif method == "none":
        return df
    else:
        raise ValueError(f"Invalid imputation method: {method}")


# ============================================================
# 🧼 Numeric Sanitization
# ============================================================
def sanitize_numerics(df: pd.DataFrame, fill: bool = True, report: bool = True, outdir: str | None = None, name: str = "unknown") -> pd.DataFrame:
    """
    Replace inf/-inf with NaN, optionally forward/back-fill small gaps.
    Logs a compact summary and optionally saves a report for diagnostics.

    Args:
        df: Input DataFrame.
        fill: Whether to forward/back-fill after replacement (default: True).
        report: Print summary stats (default: True).
        outdir: Optional diagnostics directory to save reports.
        name: Optional feature name for report filename.
    Returns:
        Sanitized DataFrame (copy).
    """
    df = df.copy()
    mask_inf = ~np.isfinite(df)
    n_inf = mask_inf.sum().sum()
    n_nan = df.isna().sum().sum()

    if n_inf > 0 and report:
        print(f"⚠️ Detected {n_inf} infinite values in {name} → replacing with NaN")

    # Replace infinities
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Optional forward/back fill
    if fill:
        df.ffill(inplace=True)
        df.bfill(inplace=True)

    n_after = df.isna().sum().sum()
    if report:
        print(f"🧮 Missing (NaN) count before={n_nan}, after sanitation={n_after}")

    # Optional diagnostics export
    if outdir is not None:
        ensure_dir(outdir)
        if n_inf > 0:
            inf_summary = mask_inf.sum(axis=0).reset_index()
            inf_summary.columns = ["feature", "inf_count"]
            safe_name = normalize_symbol(name)
            inf_summary.to_csv(os.path.join(outdir, f"{safe_name}_inf_summary.csv"), index=False)

    return df


# ============================================================
# 📈 Summary Printer
# ============================================================
def summarize_feature(df: pd.DataFrame, name: str):
    """Console-level diagnostic to track feature stats across steps."""
    safe_name = normalize_symbol(name)
    miss_pct = pct(df.isna().sum().sum(), df.size)
    print(
        f"📊 {safe_name} | shape={df.shape}, missing={miss_pct:.2f}% "
        f"| range: {df.index.min().date()} → {df.index.max().date()}"
    )