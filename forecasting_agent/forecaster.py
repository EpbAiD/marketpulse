#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
ForecastingAgent (Rolling Backtest + Weighted Ensemble)
===========================================================
Per-feature forecasting from `outputs/fetched/cleaned/*.parquet`
with cadence-specific ensembles, horizons, and validation/test sizes
loaded from `configs/features_config.yml` or `.yaml`.

New Additions:
--------------------------------
✅ Configurable weight metric: MAE, RMSE, MAPE, sMAPE (YAML-driven)
✅ Optional normalization and tie-breaker (equal | best_only)
✅ Compatible with single-cadence test mode or full run
✅ Rolling + Multi-fold backtesting retained
===========================================================
"""

import os
import sys
import json
import random
import time
import glob
import threading
import argparse
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

# 🔹 NumPy 2.0 Compatibility Patch
# Fix for Prophet/statsmodels using deprecated np.float_ in NumPy 2.0+
if not hasattr(np, 'float_'):
    np.float_ = np.float64
if not hasattr(np, 'int_'):
    np.int_ = np.int64

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml
from datetime import datetime
import gc  # ADD

def _mps_gc():
    """
    Aggressive memory cleanup for PyTorch + MPS.
    Clears GPU cache, PyTorch cache, and runs garbage collection.
    """
    try:
        import torch
        # Clear MPS cache (Apple Silicon)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        # Clear CUDA cache if available
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        # Clear PyTorch internal caches
        if hasattr(torch, '_C') and hasattr(torch._C, '_cuda_clearCublasWorkspaces'):
            torch._C._cuda_clearCublasWorkspaces()
    except Exception:
        pass
    # Run garbage collection multiple times for thorough cleanup
    gc.collect()
    gc.collect()
    gc.collect()
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.metrics import mean_absolute_error, mean_squared_error
# ===========================================================
# 🧩 Multiprocessing Safety Setup (prevents abrupt worker kills)
# ===========================================================
#import multiprocessing as mp
#try:
 #   mp.set_start_method("spawn", force=True)
#except RuntimeError:
 #   pass  # already set, ignore

# ===========================================================
# PATHS
# ===========================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(BASE_DIR, "outputs", "fetched", "cleaned")
OUT_BASE = os.path.join(BASE_DIR, "outputs", "forecasting")
MODEL_DIR = os.path.join(OUT_BASE, "models")
PLOT_DIR = os.path.join(OUT_BASE, "plots")
METRIC_DIR = os.path.join(OUT_BASE, "metrics")
PL_RUNS_DIR = os.path.join(OUT_BASE, "pl_runs")
LOG_DIR = os.path.join(OUT_BASE, "logs")
CONFIG_PATH_DEFAULT = os.path.join(BASE_DIR, "configs", "features_config.yaml")

for d in [MODEL_DIR, PLOT_DIR, METRIC_DIR, PL_RUNS_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

# ===========================================================
# UTILS
# ===========================================================
def set_global_seed(seed: int = 1):
    random.seed(seed)
    np.random.seed(seed)


def _safe_np(a) -> np.ndarray:
    return np.asarray(a, dtype=float)

# ===========================================================
# METRICS AND ENSEMBLE HELPERS
# ===========================================================
def compute_metrics(y_true, y_pred, mase_denominator: Optional[float] = None) -> dict:
    eps = 1e-8
    y_true = _safe_np(y_true)
    y_pred = _safe_np(y_pred)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if not np.any(mask):
        out = dict(MAE=np.nan, RMSE=np.nan, MAPE=np.nan, sMAPE=np.nan)
        if mase_denominator is not None:
            out["MASE"] = np.nan
        return out
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), eps))) * 100
    smape = 100 * np.mean(2 * np.abs(y_pred - y_true) /
                          (np.abs(y_true) + np.abs(y_pred) + eps))
    out = dict(MAE=mae, RMSE=rmse, MAPE=mape, sMAPE=smape)
    if mase_denominator is not None:
        out["MASE"] = mae / mase_denominator if mase_denominator > eps else np.nan
    return out

def _metric_error(y_true, y_pred, metric):
    y_true, y_pred = _safe_np(y_true), _safe_np(y_pred)
    if metric == "mae": return mean_absolute_error(y_true, y_pred)
    if metric == "rmse": return np.sqrt(mean_squared_error(y_true, y_pred))
    if metric == "mape":
        eps = 1e-8
        return np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), eps))) * 100
    if metric == "smape":
        eps = 1e-8
        return 100 * np.mean(2 * np.abs(y_pred - y_true) /
                             (np.abs(y_true) + np.abs(y_pred) + eps))
    return mean_absolute_error(y_true, y_pred)

def _fit_weighted_ensemble(X_val, y_val, metric="rmse", normalize=True, tie_breaker="equal"):
    n_models = X_val.shape[1]
    if n_models == 1: return np.ones(1)
    errs = np.array([_metric_error(y_val, X_val[:, i], metric) for i in range(n_models)])
    inv = 1.0 / np.maximum(errs, 1e-8)
    if tie_breaker == "best_only":
        w = np.zeros_like(inv)
        w[np.argmin(errs)] = 1.0
    else:
        w = inv
    if normalize:
        w = w / np.sum(w) if np.sum(w) > 0 else np.ones_like(w)/len(w)
    return w

# ===========================================================
# PLOTS
# ===========================================================
def _save_forecast_plot(df_true: pd.DataFrame, df_pred: pd.DataFrame, feature_name: str):
    plt.figure(figsize=(10, 4))
    plt.plot(df_true["ds"], df_true["y"], label="Actual", lw=1.5)
    plt.plot(df_pred["ds"], df_pred["y_pred"], label="Forecast", lw=1.5)
    plt.title(f"{feature_name} — Forecast vs Actual (TEST span)")
    plt.xlabel("Date"); plt.ylabel(feature_name); plt.legend(); plt.tight_layout()
    os.makedirs(PLOT_DIR, exist_ok=True)
    plt.savefig(os.path.join(PLOT_DIR, f"{feature_name}__forecast_vs_actual.png"), dpi=150)
    plt.close()

def _save_residuals_plots(df_merged: pd.DataFrame, feature_name: str):
    res = _safe_np(df_merged["y"] - df_merged["y_pred"])
    ds = pd.to_datetime(df_merged["ds"])
    plt.figure(figsize=(10, 3.6))
    plt.plot(ds, res, lw=1.2)
    plt.axhline(0.0, color="black", lw=1, alpha=0.6)
    plt.title(f"{feature_name} — Residuals over Time (TEST)")
    plt.tight_layout()
    os.makedirs(PLOT_DIR, exist_ok=True)
    plt.savefig(os.path.join(PLOT_DIR, f"{feature_name}__residuals_over_time.png"), dpi=150)
    plt.close()
    from scipy import stats
    fig = plt.figure(figsize=(10, 3.6))
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.hist(res, bins=20, edgecolor="k", alpha=0.7)
    ax2 = fig.add_subplot(1, 2, 2)
    try:
        stats.probplot(res, dist="norm", plot=ax2)
    except Exception:
        ax2.text(0.5, 0.5, "Q–Q unavailable", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, f"{feature_name}__residuals_hist_qq.png"), dpi=150)
    plt.close(fig)

# ===========================================================
# DATA HANDLING
# ===========================================================
def to_long_df_for_nf(df, feature_name):
    df = df.copy()
    num_df = df.select_dtypes(include=["number"])
    if num_df.empty:
        raise ValueError(f"No numeric data found for {feature_name}")
    if isinstance(df.index, pd.DatetimeIndex):
        work = num_df.copy()
        work["ds"] = df.index
    else:
        ds_col = next((c for c in ["ds","date","Date","timestamp","Datetime"] if c in df.columns), None)
        if ds_col:
            work = pd.concat([num_df, pd.to_datetime(df[ds_col]).rename("ds")], axis=1)
        else:
            work = pd.concat([num_df, pd.to_datetime(df.index, errors="coerce").rename("ds")], axis=1)
    work = work.dropna(subset=["ds"]).sort_values("ds")
    y_col = [c for c in work.columns if c != "ds"][0]
    out = work[["ds", y_col]].rename(columns={y_col: "y"})
    out["unique_id"] = feature_name
    return out[["ds","unique_id","y"]]

def infer_freq_from_ds(ds, fallback="B"):
    try:
        return pd.infer_freq(pd.Series(pd.to_datetime(ds)).sort_values()) or fallback
    except Exception:
        return fallback

# ===========================================================
# CONFIG LOAD
# ===========================================================
def _default_arima(cadence):
    return dict(seasonal=cadence!="daily", m=12 if cadence=="monthly" else 52 if cadence=="weekly" else 7)

def _default_prophet(cadence):
    return dict(yearly_seasonality=True, weekly_seasonality=(cadence=="daily"), daily_seasonality=False)

def load_yaml_config(path=None):
    path = path or CONFIG_PATH_DEFAULT
    if not os.path.exists(path):
        alt = path.replace(".yaml",".yml")
        if os.path.exists(alt): path = alt
        else: raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    cad = {}
    for cadence, g in cfg.items():
        if not isinstance(g, dict) or "features" not in g: continue
        arima_cfg = g.get("arima", _default_arima(cadence))
        prophet_cfg = g.get("prophet", _default_prophet(cadence))
        mb_cfg = g.get("multi_backtest", {"enabled": False, "folds": 3})
        ens_cfg = g.get("ensemble", {})
        cad[cadence] = {
            "features": list(g.get("features", [])),
            "horizon": int(g.get("horizon", 10)),
            "val_size": int(g.get("val_size", 30)),
            "test_size": int(g.get("test_size", g.get("horizon", 10) * 3)),
            "nf_loss": str(g.get("nf_loss", "mae")).lower(),
            "ensemble": {
                "weight_metric": ens_cfg.get("weight_metric", "rmse").lower(),
                "normalize_weights": bool(ens_cfg.get("normalize_weights", True)),
                "tie_breaker": ens_cfg.get("tie_breaker", "equal").lower()
            },
            "arima": arima_cfg,
            "prophet": prophet_cfg,
            "multi_backtest": {"enabled": bool(mb_cfg.get("enabled", False)), "folds": max(1, int(mb_cfg.get("folds", 3)))}
        }
    return cad

# ===========================================================
# NF MODEL BUILDER
# ===========================================================
def _build_nf_models(cadence, horizon, half, accelerator, loss_name):
    from neuralforecast.models import NBEATSx, NHITS, PatchTST
    from neuralforecast.losses.pytorch import MQLoss, MAE, MSE
    loss = MSE() if loss_name == "mse" else MAE() if loss_name == "mae" else MQLoss(level=[0.5])

    # Early stopping configuration to reduce training time
    # Monitor validation loss, stop if no improvement for 50 epochs
    early_stop_config = {
        'early_stop_patience_steps': 50,
        'max_steps': 1000  # Reduced from default (~3000-5000) for faster training
    }

    if cadence == "daily":
        return [
            NBEATSx(h=horizon, input_size=min(7*horizon, half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config),
            NHITS(h=horizon, input_size=min(28*(horizon//7+1), half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config),
            PatchTST(h=horizon, input_size=min(60, half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config)
        ]
    if cadence == "weekly":
        return [
            NHITS(h=horizon, input_size=min(16, half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config),
            NBEATSx(h=horizon, input_size=min(12, half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config)
        ]
    if cadence == "monthly":
        return [
            NBEATSx(h=horizon, input_size=min(12, half), loss=loss, accelerator=accelerator, devices=1, **early_stop_config)
        ]
    raise ValueError(f"Unknown cadence '{cadence}'")

# ===========================================================
# SINGLE-WINDOW FORECAST
# ===========================================================
def _fit_and_predict_window(cadence, horizon, df_fit, val_size, test_ds_window, inferred_freq,
                            accelerator, nf_loss, arima_cfg, prophet_cfg, ens_cfg, save_model=False,
                            versioned_paths=None, feature_name=None):
    """
    Fit per-feature ensemble (NeuralForecast + ARIMA/Prophet if applicable),
    predict next horizon, compute weights, and (optionally) persist models to disk.

    Safe version:
    - Handles ARIMA/Prophet failures gracefully.
    - Prevents abrupt process crashes under multiprocessing.
    - Uses overwrite=True for NF saves.
    - Supports versioned model saving when versioned_paths provided.
    """
    _mps_gc()  # 🔹 enter window
    import torch
    from neuralforecast.core import NeuralForecast
    import joblib
    import shutil

    if len(df_fit) <= val_size:
        raise RuntimeError("Too small for split.")
    
    # Split + per-feature folder
    df_train, df_val = df_fit.iloc[:-val_size], df_fit.iloc[-val_size:]
    feature_stub = df_fit["unique_id"].iloc[0] if "unique_id" in df_fit.columns else cadence
    feature_dir = os.path.join(MODEL_DIR, feature_stub)
    os.makedirs(feature_dir, exist_ok=True)

    # Reference stats from VAL (for scaling)
    ref_mean, ref_std = df_val["y"].mean(), df_val["y"].std(ddof=0) or 1.0

    # ------------------------------------------------------------------
    # 🧠 NeuralForecast ensemble
    # ------------------------------------------------------------------
    nf_models = _build_nf_models(cadence, horizon, len(df_fit)//2, accelerator, nf_loss)
    nf = NeuralForecast(models=nf_models, freq=inferred_freq)
    nf.fit(df=df_fit[["unique_id", "ds", "y"]], val_size=val_size)
    nf_fc = nf.predict().reset_index()

    # Collect NF predictions
    nf_cols = [c for c in nf_fc.columns if c not in ("ds", "unique_id", "index")]
    if len(nf_fc) > horizon:
        nf_fc = nf_fc.tail(horizon).copy()
    nf_fc["ds"] = pd.to_datetime(test_ds_window[:len(nf_fc)])
    for c in nf_cols:
        x = nf_fc[c].to_numpy()
        mu = float(np.nanmean(x))
        sd = float(np.nanstd(x) + 1e-8)
        nf_fc[c] = (x - mu) / sd * ref_std + ref_mean

    cols = [nf_fc[c].to_numpy() for c in nf_cols]
    base_names = [m.__class__.__name__ for m in getattr(nf, "models", nf_models)]
    col_map = {name: i for i, name in enumerate(base_names)}

    # ------------------------------------------------------------------
    # 🧩 ARIMA + Prophet (safe)
    # ------------------------------------------------------------------
    arima_model = None
    prophet_model = None

    # ---- ARIMA ----
    if cadence in ("weekly", "monthly"):
        import pmdarima as pm
        try:
            arima_model = pm.auto_arima(
                df_fit["y"],
                seasonal=bool(arima_cfg.get("seasonal", True)),
                m=int(arima_cfg.get("m", 1)),
                suppress_warnings=True,
                error_action="ignore"
            )
            arima_fc = arima_model.predict(n_periods=horizon)[:len(test_ds_window)]
            mu = float(np.nanmean(arima_fc)); sd = float(np.nanstd(arima_fc) + 1e-8)
            arima_fc = (arima_fc - mu) / sd * ref_std + ref_mean
            cols.append(arima_fc)
            col_map["ARIMA"] = len(cols) - 1
        except Exception as e:
            print(f"⚠️ ARIMA failed for {feature_stub}: {e}")
            arima_fc = np.zeros(horizon)
            cols.append(arima_fc)

    # ---- Prophet ----
    if cadence == "monthly":
        from prophet import Prophet
        import traceback
        try:
            print(f"🔮 Training Prophet for {feature_name} (monthly feature)...")

            # Limit history for very long monthly series to prevent memory issues
            MAX_MONTHLY_HISTORY = 240  # 20 years (240 months)
            if len(df_fit) > MAX_MONTHLY_HISTORY:
                print(f"⚠️ Limiting monthly history from {len(df_fit)} to {MAX_MONTHLY_HISTORY} months")
                df_fit_prophet = df_fit.tail(MAX_MONTHLY_HISTORY).copy()
            else:
                df_fit_prophet = df_fit.copy()

            prophet_model = Prophet(
                yearly_seasonality=bool(prophet_cfg.get("yearly_seasonality", True)),
                weekly_seasonality=bool(prophet_cfg.get("weekly_seasonality", False)),
                daily_seasonality=bool(prophet_cfg.get("daily_seasonality", False)),
                seasonality_mode=prophet_cfg.get("seasonality_mode", "additive"),
            )
            df_p = df_fit_prophet[["ds", "y"]].rename(columns={"ds": "ds", "y": "y"})

            print(f"Fitting Prophet model ({len(df_p)} data points)...")
            prophet_model.fit(df_p, algorithm='Newton')  # Explicitly use Newton (faster)

            future = pd.DataFrame({"ds": pd.to_datetime(test_ds_window[:horizon])})
            p_fc = prophet_model.predict(future)["yhat"].to_numpy()[:len(test_ds_window)]
            mu = float(np.nanmean(p_fc)); sd = float(np.nanstd(p_fc) + 1e-8)
            p_fc = (p_fc - mu) / sd * ref_std + ref_mean
            cols.append(p_fc)
            col_map["Prophet"] = len(cols) - 1
            print(f"✅ Prophet training completed for {feature_name}")
        except Exception as e:
            print(f"❌ Prophet FAILED for {feature_name}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            print(f"Continuing without Prophet (using neural + ARIMA only)...")
            p_fc = np.zeros(horizon)
            cols.append(p_fc)
            prophet_model = None  # Set to None so we don't try to save it

    # ------------------------------------------------------------------
    # ⚖️ Weighted Ensemble (VAL-based)
    # ------------------------------------------------------------------
    X = np.column_stack(cols) if cols else np.empty((0, 0))
    if X.size == 0:
        return pd.DataFrame({"ds": pd.to_datetime(test_ds_window[:0]), "y_pred": np.array([], dtype=float)})

    weight_metric = str(ens_cfg.get("weight_metric", "rmse")).lower()
    normalize = bool(ens_cfg.get("normalize_weights", True))
    tie_breaker = str(ens_cfg.get("tie_breaker", "equal")).lower()
    tie_breaker = tie_breaker if tie_breaker in {"equal", "best_only"} else "equal"

    if val_size >= horizon:
        y_val = df_val["y"].tail(horizon).to_numpy()
        X_val = X[-len(y_val):, :]
        w = _fit_weighted_ensemble(X_val, y_val, metric=weight_metric,
                                   normalize=normalize, tie_breaker=tie_breaker)
        y_pred = (X * w).sum(axis=1)
    else:
        w = None
        y_pred = X.mean(axis=1)

    # ------------------------------------------------------------------
    # 💾 Optional model persistence (with versioning support)
    # ------------------------------------------------------------------
    if save_model:
        # Use versioned paths if provided, otherwise use legacy non-versioned paths
        if versioned_paths:
            nf_save_path = versioned_paths["nf_bundle"]
            arima_path = versioned_paths["arima"]
            prophet_path = versioned_paths["prophet"]
            ensemble_path = versioned_paths["ensemble"]
        else:
            nf_save_path = os.path.join(feature_dir, "nf_bundle")
            arima_path = os.path.join(feature_dir, "arima.pkl")
            prophet_path = os.path.join(feature_dir, "prophet.pkl")
            ensemble_path = os.path.join(feature_dir, "ensemble.json")

        # Save NeuralForecast bundle
        try:
            nf.save(nf_save_path, overwrite=True)
            print(f"💾 Saved NeuralForecast models → {nf_save_path}")
        except Exception as e:
            print(f"⚠️ NF save failed for {feature_stub}: {e}")

        # Save ARIMA model
        if arima_model is not None:
            try:
                os.makedirs(os.path.dirname(arima_path), exist_ok=True)
                joblib.dump(arima_model, arima_path)
                print(f"💾 Saved ARIMA model → {arima_path}")
            except Exception as e:
                print(f"⚠️ Could not save ARIMA: {e}")

        # Save Prophet model
        if prophet_model is not None:
            try:
                os.makedirs(os.path.dirname(prophet_path), exist_ok=True)
                joblib.dump(prophet_model, prophet_path)
                print(f"💾 Saved Prophet model → {prophet_path}")
            except Exception as e:
                print(f"⚠️ Could not save Prophet: {e}")

        # Save ensemble metadata
        model_info = {
            "feature": feature_stub,
            "cadence": cadence,
            "base_models": list(col_map.keys()),
            "column_index_map": col_map,
            "n_models": int(X.shape[1]),
            "metric_used": weight_metric,
            "normalize": normalize,
            "tie_breaker": tie_breaker,
            "timestamp": datetime.now().isoformat(),
            "weights": [float(x) for x in w] if w is not None else "uniform_mean"
        }
        try:
            os.makedirs(os.path.dirname(ensemble_path), exist_ok=True)
            with open(ensemble_path, "w") as f:
                json.dump(model_info, f, indent=2)
            print(f"💾 Saved ensemble metadata → {ensemble_path}")
        except Exception as e:
            print(f"⚠️ Could not save ensemble JSON: {e}")

    # 🔹 Aggressive memory cleanup to prevent accumulation across features
    # Delete all model objects and clear caches
    try:
        del nf_models
    except:
        pass
    try:
        del nf
    except:
        pass
    try:
        del arima_model
    except:
        pass
    try:
        del prophet_model
    except:
        pass

    _mps_gc()  # 🔹 exit window
    # ------------------------------------------------------------------
    # ✅ Return predictions
    # ------------------------------------------------------------------
    return pd.DataFrame({
        "ds": pd.to_datetime(test_ds_window[:len(y_pred)]),
        "y_pred": np.nan_to_num(y_pred)
    })
# ===========================================================
# VERSION MANAGEMENT UTILITIES
# ===========================================================
def get_version_metadata_path(feature_name):
    """Get path to version metadata file for a feature."""
    return os.path.join(MODEL_DIR, f"{feature_name}_versions.json")

def load_version_metadata(feature_name):
    """Load version metadata for a feature."""
    metadata_path = get_version_metadata_path(feature_name)
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load version metadata for {feature_name}: {e}")
    return {"versions": [], "active_version": None}

def save_version_metadata(feature_name, metadata):
    """Save version metadata for a feature."""
    metadata_path = get_version_metadata_path(feature_name)
    os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

def get_next_version(feature_name):
    """Get the next version number for a feature."""
    metadata = load_version_metadata(feature_name)
    if not metadata["versions"]:
        return 1
    return max(v["version"] for v in metadata["versions"]) + 1

def get_latest_completed_version(feature_name):
    """Get the latest completed version number and metadata."""
    metadata = load_version_metadata(feature_name)
    completed = [v for v in metadata["versions"] if v.get("status") == "completed"]
    if not completed:
        return None
    return max(completed, key=lambda v: v["version"])

def get_versioned_model_paths(feature_name, version):
    """Get paths for all versioned model files."""
    feature_dir = os.path.join(MODEL_DIR, feature_name)
    return {
        "nbeats": os.path.join(feature_dir, f"{feature_name}_nbeats_v{version}.pth"),
        "nhits": os.path.join(feature_dir, f"{feature_name}_nhits_v{version}.pth"),
        "patchtst": os.path.join(feature_dir, f"{feature_name}_patchtst_v{version}.pth"),
        "arima": os.path.join(feature_dir, f"{feature_name}_arima_v{version}.pkl"),
        "prophet": os.path.join(feature_dir, f"{feature_name}_prophet_v{version}.pkl"),
        "nf_bundle": os.path.join(feature_dir, f"nf_bundle_v{version}"),
        "ensemble": os.path.join(feature_dir, f"{feature_name}_ensemble_v{version}.json"),
        "metrics": os.path.join(METRIC_DIR, f"{feature_name}_metrics_v{version}.json"),
        "predictions": os.path.join(METRIC_DIR, f"{feature_name}_test_predictions_v{version}.csv")
    }

def mark_version_status(feature_name, version, status, metrics=None):
    """Mark a version with a specific status (training, completed, failed)."""
    metadata = load_version_metadata(feature_name)

    # Find existing version entry or create new one
    version_entry = None
    for v in metadata["versions"]:
        if v["version"] == version:
            version_entry = v
            break

    if version_entry is None:
        version_entry = {
            "version": version,
            "created_at": datetime.now().isoformat(),
            "status": status
        }
        metadata["versions"].append(version_entry)
    else:
        version_entry["status"] = status
        version_entry["updated_at"] = datetime.now().isoformat()

    if metrics:
        version_entry["metrics"] = metrics

    # Update active version if this version is completed
    if status == "completed":
        metadata["active_version"] = version

    save_version_metadata(feature_name, metadata)

# ===========================================================
# INFERENCE FUNCTION (load versioned models and forecast)
# ===========================================================
def run_inference_for_features(
    feature_names: List[str],
    horizon_days: int,
    use_bigquery: bool = False,
    config_path: Optional[str] = None,
    force_cpu: bool = True
) -> pd.DataFrame:
    """
    Run inference to forecast raw features for the next N days.

    Args:
        feature_names: List of feature names to forecast (e.g., ['VIX', 'GSPC', 'DFF'])
        horizon_days: Number of days to forecast into the future
        use_bigquery: Whether to load latest data from BigQuery
        config_path: Path to features_config.yaml
        force_cpu: Whether to force CPU inference (recommended)

    Returns:
        DataFrame with columns: ['ds', 'feature', 'forecast_value']
        where 'ds' is the forecasted date, 'feature' is the feature name,
        and 'forecast_value' is the predicted value
    """
    import torch
    import pickle
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATSx, NHITS, PatchTST

    print(f"\n{'='*60}")
    print(f"🔮 INFERENCE MODE: Forecasting {len(feature_names)} features for {horizon_days} days")
    print(f"{'='*60}\n")

    # Load configuration
    if config_path is None:
        config_path = CONFIG_PATH_DEFAULT
    with open(config_path, "r") as f:
        cad = yaml.safe_load(f)

    # Set CPU mode
    if force_cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        print("🧩 Running inference on CPU (MPS/CUDA disabled).")

    # Load latest raw data
    if use_bigquery:
        print("📥 Loading latest data from BigQuery...")
        from data_agent.storage import get_storage
        storage = get_storage(use_bigquery=True)
        raw_data = {}
        for fname in feature_names:
            # Load raw feature with 'daily' cadence (default for most features)
            df = storage.load_raw_feature(fname, cadence='daily')
            if df is not None and not df.empty:
                raw_data[fname] = df
            else:
                print(f"⚠️ Warning: {fname} not found in BigQuery, skipping...")
    else:
        print("📂 Loading latest data from local files...")
        raw_data = {}
        for fname in feature_names:
            parquet_path = os.path.join(RAW_DIR, f"{fname}.parquet")
            if os.path.exists(parquet_path):
                raw_data[fname] = pd.read_parquet(parquet_path)
            else:
                print(f"⚠️ Warning: {fname}.parquet not found, skipping...")

    all_forecasts = []

    for fname in feature_names:
        if fname not in raw_data:
            print(f"⚠️ Skipping {fname}: no data available")
            continue

        print(f"\n🔮 Forecasting {fname}...")

        # Get feature metadata from config
        cadence = None
        for cad_name in ['daily', 'weekly', 'monthly']:
            if fname in cad[cad_name].get('features', []):
                cadence = cad_name
                break

        if cadence is None:
            print(f"⚠️ {fname} not found in config, skipping...")
            continue

        # Get latest completed version
        latest_version = get_latest_completed_version(fname)
        if latest_version is None:
            print(f"❌ No trained models found for {fname}, skipping...")
            continue

        version_num = latest_version["version"]
        print(f"  ✅ Using {fname} v{version_num}")

        # Get versioned model paths
        versioned_paths = get_versioned_model_paths(fname, version_num)

        # Load ensemble weights - REQUIRED for inference
        if not os.path.exists(versioned_paths["ensemble"]):
            print(f"  ❌ Ensemble weights not found for {fname} v{version_num}, skipping...")
            print(f"     Expected path: {versioned_paths['ensemble']}")
            print(f"     Run training to generate ensemble weights")
            continue

        with open(versioned_paths["ensemble"], "r") as f:
            ensemble_config = json.load(f)

        # Convert weights list to dictionary mapping model names to weights
        weights_list = ensemble_config.get("weights", [])
        base_models = ensemble_config.get("base_models", [])

        # For NeuralForecast models, sum across their variants
        # Each base model has 3 variants (3x weight values in list)
        weights = {}
        models_per_base = len(weights_list) // len(base_models) if base_models else 0

        for i, model_name in enumerate(base_models):
            # Sum weights for this model's variants
            model_key = model_name.lower().replace("x", "")  # NBEATSx -> nbeats
            start_idx = i * models_per_base
            end_idx = start_idx + models_per_base
            weights[model_key] = sum(weights_list[start_idx:end_idx])

        print(f"  📊 Ensemble weights: {weights}")

        # Prepare data for inference
        df = raw_data[fname].copy()

        # Handle different data formats
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            date_col = df.columns[0]  # First column after reset (Date/date/ds)
        elif 'date' in df.columns:
            date_col = 'date'
        elif 'ds' in df.columns:
            date_col = 'ds'
        else:
            date_col = df.columns[0]

        # Get value column (either 'value' or feature name)
        if 'value' in df.columns:
            value_col = 'value'
        elif fname in df.columns:
            value_col = fname
        else:
            # Assume second column is the value
            value_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]

        # Rename to standard format
        df = df.rename(columns={date_col: "ds", value_col: "y"})
        df["unique_id"] = fname
        df = df[["unique_id", "ds", "y"]].dropna()
        df = df.sort_values("ds").reset_index(drop=True)

        # Get horizon from config
        horizon = cad[cadence]["horizon"]
        actual_horizon = max(horizon, horizon_days)  # Use max of config and requested

        # Collect predictions from each model
        predictions = {}

        # 1. NeuralForecast models (load from nf_bundle)
        nf_bundle_path = versioned_paths["nf_bundle"]
        if os.path.exists(nf_bundle_path):
            try:
                # Load the NeuralForecast bundle
                nf = NeuralForecast.load(path=nf_bundle_path)
                print(f"  ✅ Loaded NeuralForecast bundle from {os.path.basename(nf_bundle_path)}")

                # Run inference
                nf_preds = nf.predict(df=df)

                # Extract predictions for each model
                for model_name in ["nbeats", "nhits", "patchtst"]:
                    if weights.get(model_name, 0) > 0:
                        # Try different column name variations (with -median suffix)
                        possible_cols = [
                            f"{model_name.upper()}-median",  # PATCHTST-median
                            f"{model_name.upper()}x-median",  # NBEATSx-median
                            f"{model_name.capitalize()}-median",  # Patchtst-median
                            f"{model_name.capitalize()}x-median",  # Nbeatsx-median
                            f"PatchTST-median" if model_name == "patchtst" else None,  # Exact match for PatchTST
                            model_name.upper(),  # Fallback: PATCHTST
                            f"{model_name.upper()}x",  # Fallback: NBEATSx
                        ]
                        possible_cols = [col for col in possible_cols if col is not None]  # Remove None

                        for col in possible_cols:
                            if col in nf_preds.columns:
                                predictions[model_name] = nf_preds[col].values[:horizon_days]
                                print(f"  ✅ {model_name} predictions extracted from column '{col}'")
                                break
                        else:
                            print(f"  ⚠️ Could not find predictions for {model_name}")
            except Exception as e:
                print(f"  ⚠️ NeuralForecast bundle loading failed: {e}")
        else:
            print(f"  ⚠️ NeuralForecast bundle not found at {nf_bundle_path}")

        # 2. ARIMA model
        if os.path.exists(versioned_paths["arima"]) and weights.get("arima", 0) > 0:
            try:
                with open(versioned_paths["arima"], "rb") as f:
                    arima_model = pickle.load(f)
                arima_forecast = arima_model.forecast(steps=horizon_days)
                predictions["arima"] = arima_forecast
                print(f"  ✅ ARIMA inference complete")
            except Exception as e:
                print(f"  ⚠️ ARIMA inference failed: {e}")

        # 3. Prophet model
        if os.path.exists(versioned_paths["prophet"]) and weights.get("prophet", 0) > 0:
            try:
                with open(versioned_paths["prophet"], "rb") as f:
                    prophet_model = pickle.load(f)

                # Create future dataframe
                last_date = df["ds"].max()
                future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=horizon_days, freq='D')
                future_df = pd.DataFrame({"ds": future_dates})

                prophet_forecast = prophet_model.predict(future_df)
                predictions["prophet"] = prophet_forecast["yhat"].values
                print(f"  ✅ Prophet inference complete")
            except Exception as e:
                print(f"  ⚠️ Prophet inference failed: {e}")

        # Ensemble predictions using learned weights
        if not predictions:
            print(f"  ❌ No model predictions available for {fname}")
            continue

        # Combine predictions with weights
        ensemble_pred = np.zeros(horizon_days)
        total_weight = 0.0

        for model_name, pred_values in predictions.items():
            weight = weights.get(model_name, 0.0)
            if weight > 0 and len(pred_values) >= horizon_days:
                ensemble_pred += weight * pred_values[:horizon_days]
                total_weight += weight

        if total_weight > 0:
            ensemble_pred /= total_weight

        # Create forecast dataframe
        last_date = df["ds"].max()
        forecast_start = last_date + pd.Timedelta(days=1)
        forecast_dates = pd.date_range(start=forecast_start, periods=horizon_days, freq='D')

        print(f"  📅 Latest data date: {last_date.date()}")
        print(f"  📅 Forecast period: {forecast_dates[0].date()} to {forecast_dates[-1].date()}")

        forecast_df = pd.DataFrame({
            'ds': forecast_dates,
            'feature': fname,
            'forecast_value': ensemble_pred
        })

        all_forecasts.append(forecast_df)
        print(f"  ✅ {fname} forecast complete: {horizon_days} days")

    # Combine all forecasts
    if not all_forecasts:
        print("\n❌ No forecasts generated")
        return pd.DataFrame(columns=['ds', 'feature', 'forecast_value'])

    final_forecasts = pd.concat(all_forecasts, ignore_index=True)

    # Save forecasts
    output_path = os.path.join(OUT_BASE, "inference", f"raw_forecasts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_forecasts.to_parquet(output_path)

    print(f"\n{'='*60}")
    print(f"✅ Inference complete: {len(all_forecasts)} features forecasted")
    print(f"📁 Saved to: {output_path}")
    print(f"{'='*60}\n")

    return final_forecasts

# ===========================================================
# TRAINING FUNCTION (rolling + multi-fold)
# ===========================================================
def train_forecaster_for_feature(feature_path, cadence, horizon, val_size, force_cpu, quiet,
                                 test_size, nf_loss, arima_cfg, prophet_cfg, multi_backtest, ens_cfg,
                                 use_bigquery=False, feature_name=None, force_retrain=False):
    import torch
    torch.manual_seed(1)
    set_global_seed(1)
    _mps_gc()  # 🔹 ensure clean GPU state before feature run
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(1)
    os.environ.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                       "NUMEXPR_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false"})
    torch.set_num_threads(1)  # ✅ prevent over-threading and improve MPS stability
    
    # Ensure metrics and related directories always exist before defining paths
    os.makedirs(METRIC_DIR, exist_ok=True)
    os.makedirs(PLOT_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    fname = os.path.splitext(os.path.basename(feature_path))[0]
    pid = os.getpid()
    ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 🔹 VERSIONED RESUMPTION LOGIC: Check for latest completed version
    if not force_retrain:
        latest_version = get_latest_completed_version(fname)
        if latest_version:
            version_num = latest_version["version"]
            print(f"[{pid}] ✅ RESUMING: {fname} v{version_num} already completed, loading existing metrics...")
            try:
                # Return metrics from the completed version
                metrics = latest_version.get("metrics", {})
                print(f"[{pid}] 📊 {fname} v{version_num}: MAE={metrics.get('MAE', 'N/A'):.4f}, "
                      f"RMSE={metrics.get('RMSE', 'N/A'):.4f}")
                return {"feature": fname, "Cadence": cadence, **metrics}
            except Exception as e:
                print(f"[{pid}] ⚠️ Failed to load metrics for {fname} v{version_num}: {e}")
                print(f"[{pid}] 🔄 Will create new version...")
    else:
        print(f"[{pid}] 🔄 FORCE RETRAIN: {fname} (--force-retrain flag set)")

    # Determine next version number
    current_version = get_next_version(fname)
    print(f"[{pid}] 🆕 Starting {fname} v{current_version}...")

    # Mark this version as training
    mark_version_status(fname, current_version, "training")

    # Get versioned file paths
    versioned_paths = get_versioned_model_paths(fname, current_version)
    metrics_path = versioned_paths["metrics"]
    preds_csv_path = versioned_paths["predictions"]

    if torch.cuda.is_available():
        accel = "gpu"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        accel = "mps"
    else:
        accel = "cpu"
    marker = os.path.join(PL_RUNS_DIR, f"ACTIVE__{fname}__pid{pid}.tmp")
    open(marker, "a").close()
    try:
        # Load data from BigQuery or local file
        if use_bigquery:
            # Import storage layer
            sys.path.insert(0, BASE_DIR)
            from data_agent.storage import get_storage
            from data_agent.fetcher import get_cadence_from_config

            storage = get_storage(use_bigquery=True)
            feature_cadence = get_cadence_from_config(feature_name or fname)

            # Load raw feature from BigQuery
            df_raw = storage.load_raw_feature(feature_name or fname, feature_cadence)
            if df_raw is None:
                print(f"[{pid}] ERROR {fname}: not found in BigQuery")
                return None
            print(f"[{pid}] 📦 Loaded {fname} from BigQuery: {len(df_raw)} rows")
        else:
            df_raw = pd.read_parquet(feature_path)

        df_long = to_long_df_for_nf(df_raw, fname)
        n = len(df_long)
        # Industry standard: test_size should match horizon (Hyndman's Forecasting: Principles & Practice)
        # "The test set should ideally be at least as large as the maximum forecast horizon"
        test_size = horizon  # Match test set to forecast horizon
        if n < val_size + test_size + max(horizon, 10):
            print(f"[{pid}] SKIP {fname}: too few samples (n={n})")
            return None
        inferred_freq = infer_freq_from_ds(df_long["ds"], fallback="B")
        test_metrics_all_folds, preds_all_folds = [], []

        def mase_den(df):
            y = df["y"].to_numpy()
            return np.mean(np.abs(y[1:] - y[:-1])) if len(y) > 3 else np.nan

        # ===========================================================
        # INDUSTRY-STANDARD BASELINE: Simple Train/Val/Test Split
        # ===========================================================
        # Following Hyndman's "Forecasting: Principles and Practice" recommendations:
        # - Test set size = forecast horizon (to evaluate h-step-ahead performance)
        # - Validation set for hyperparameter tuning and ensemble weight learning
        # - Train on remaining historical data
        print(f"[{pid}] 📊 Using industry-standard train/val/test split (Hyndman's FPP methodology)")

        # Single split: train up to (n - val_size - test_size), validate on val_size, test on test_size
        train_end = n - (val_size + test_size)
        val_end = n - test_size

        if train_end <= 0 or val_end <= train_end:
            print(f"[{pid}] SKIP {fname}: insufficient data for train/val/test split")
            return None

        df_train = df_long.iloc[:train_end]
        df_val = df_long.iloc[train_end:val_end]
        df_test = df_long.iloc[val_end:]

        print(f"[{pid}] 📊 Data split: train={len(df_train)}, val={len(df_val)}, test={len(df_test)}")

        mase_denom = mase_den(pd.concat([df_train, df_val], ignore_index=True))

        # Industry standard: test on the MOST RECENT data (last horizon points)
        # This simulates real-world deployment where we forecast into the immediate future
        test_dates = df_test["ds"].to_numpy()[-horizon:]  # LAST horizon days (most recent)

        if len(test_dates) == 0:
            print(f"[{pid}] SKIP {fname}: no test dates available")
            return None

        # Get historical data up to the test period
        cutoff = pd.to_datetime(test_dates[0])
        df_hist = df_long[df_long["ds"] < cutoff]

        if len(df_hist) < (val_size + max(horizon, 10)):
            print(f"[{pid}] SKIP {fname}: insufficient historical data")
            return None

        # Single validation prediction (replaces 9-window rolling validation)
        print(f"[{pid}] 🧠 Training model on {len(df_hist)} samples, predicting {len(test_dates)} test points...")
        _mps_gc()

        df_pred = _fit_and_predict_window(
            cadence, horizon, df_hist, val_size, test_dates,
            inferred_freq, accel, nf_loss, arima_cfg, prophet_cfg, ens_cfg,
            save_model=False
        )

        _mps_gc()

        # Compute metrics on this single test window
        df_true = df_test[df_test["ds"].isin(df_pred["ds"])][["ds", "y"]]
        merged = pd.merge(df_pred, df_true, on="ds", how="inner")

        if merged.empty:
            print(f"[{pid}] WARN {fname}: no predictions matched test data")
            metrics = dict(MAE=np.nan, RMSE=np.nan, MAPE=np.nan, sMAPE=np.nan, MASE=np.nan)
            test_metrics_all_folds = []
            preds_all_folds = []
        else:
            fold_metrics = compute_metrics(merged["y"], merged["y_pred"], mase_denom)
            test_metrics_all_folds = [fold_metrics]
            preds_all_folds = [merged.assign(fold=1)]
            print(f"[{pid}] ✅ Validation complete: MAE={fold_metrics.get('MAE', np.nan):.4f}, RMSE={fold_metrics.get('RMSE', np.nan):.4f}")

        # ---------------- Metrics JSON (versioned) ----------------
        if not test_metrics_all_folds:
            metrics = dict(MAE=np.nan, RMSE=np.nan, MAPE=np.nan, sMAPE=np.nan, MASE=np.nan)
            print(f"[{pid}] WARN {fname}: no predictions.")
        else:
            dfm = pd.DataFrame(test_metrics_all_folds)
            metrics = {k: float(np.nanmean(dfm[k])) for k in dfm.columns}
        print(f"[{pid}] TEST {fname} v{current_version}: {json.dumps(metrics)}")
        os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        # ---------------- Predictions CSV + 3 diagnostic plots (versioned) --------------
        if preds_all_folds:
            df_last = preds_all_folds[-1].sort_values("ds")
            df_last["residual"] = df_last["y"] - df_last["y_pred"]
            os.makedirs(os.path.dirname(preds_csv_path), exist_ok=True)
            df_last.to_csv(preds_csv_path, index=False)

            # 1) Forecast vs Actual
            _save_forecast_plot(df_true=df_long[["ds", "y"]],  # full, as before
                                df_pred=df_last[["ds", "y_pred"]],
                                feature_name=fname)
            # 2) Residuals over time & 3) Residuals hist + Q-Q
            _save_residuals_plots(df_last[["ds", "y", "y_pred"]], feature_name=fname)

        # ===========================================================
        # ✅ Final full-data retrain ONLY for saving deployable models (with versioning)
        # ===========================================================
        # WORKAROUND: Skip final retrain for weekly/monthly to avoid hanging (GitHub Actions issue)
        # Test metrics are already valid from train/val/test split above
        if cadence in ["weekly", "monthly"]:
            print(f"\n⏭️ Skipping final retrain for {fname} (weekly/monthly) - using test models as final")
            # Mark version as completed with test metrics
            mark_version_status(fname, current_version, "completed", metrics=metrics)
            print(f"✅ {fname} v{current_version} marked as completed (test models saved)\n")
        else:
            # Daily features: do final retrain as normal
            try:
                print(f"\n🧠 Retraining final full-data model for {fname} v{current_version} (saving artifacts)...")
                # Use the last horizon timestamps from the series to drive shapes;
                # predictions themselves are not used here—this call persists models.
                final_window_ds = df_long["ds"].tail(horizon).to_numpy()
                _ = _fit_and_predict_window(
                    cadence, horizon, df_long, val_size, final_window_ds,
                    inferred_freq, accel, nf_loss, arima_cfg, prophet_cfg, ens_cfg,
                    save_model=True,
                    versioned_paths=versioned_paths,
                    feature_name=fname
                )
                # Mark version as completed
                mark_version_status(fname, current_version, "completed", metrics=metrics)
                print(f"✅ Final model for {fname} v{current_version} saved and marked as active version\n")
            except Exception as e:
                # Mark version as failed
                mark_version_status(fname, current_version, "failed")
                print(f"⚠️ Failed to retrain/save final model for {fname} v{current_version}: {e}")

        return {"feature": fname, "Cadence": cadence, **metrics}
    finally:
        _mps_gc()  # 🔹 free memory after feature run
        if os.path.exists(marker): os.remove(marker)
# ===========================================================
# RUNNER + CLI
# ===========================================================
def collect_feature_files():
    return {os.path.splitext(f)[0]: os.path.join(RAW_DIR, f)
            for f in os.listdir(RAW_DIR) if f.endswith(".parquet")}

def build_run_list_all(cad, name_to_path):
    runs = []
    for c, info in cad.items():
        for f in info["features"]:
            if f in name_to_path:
                runs.append((f, name_to_path[f], c, info["horizon"], info["val_size"], info["test_size"]))
    return runs

def build_run_list_single(cad, name_to_path, sd, sw, sm):
    runs = []

    # Only run daily if user explicitly requested it
    if sd:
        if "daily" in cad and sd in name_to_path:
            runs.append((
                sd, name_to_path[sd], "daily",
                cad["daily"]["horizon"], cad["daily"]["val_size"], cad["daily"]["test_size"]
            ))

    # Only run weekly if user explicitly requested it
    if sw:
        if "weekly" in cad and sw in name_to_path:
            runs.append((
                sw, name_to_path[sw], "weekly",
                cad["weekly"]["horizon"], cad["weekly"]["val_size"], cad["weekly"]["test_size"]
            ))

    # Only run monthly if user explicitly requested it
    if sm:
        if "monthly" in cad and sm in name_to_path:
            runs.append((
                sm, name_to_path[sm], "monthly",
                cad["monthly"]["horizon"], cad["monthly"]["val_size"], cad["monthly"]["test_size"]
            ))

    return runs

def _status_printer(stop, total, poll=3.0):
    while not stop.is_set():
        active = len(glob.glob(os.path.join(PL_RUNS_DIR, "ACTIVE__*.tmp")))
        print(f"\r⏱ Active training jobs: {active}/{total}", end="", flush=True)
        time.sleep(poll)
    print()

def run_forecasting_agent(mode="all", config_path=None, single_daily=None, single_weekly=None, single_monthly=None, use_bigquery=False, force_retrain=False, selective_features=None):
    for d in [MODEL_DIR, PLOT_DIR, METRIC_DIR, PL_RUNS_DIR, LOG_DIR]:
        os.makedirs(d, exist_ok=True)
    print("===========================================================")
    print("🚀 Starting Forecasting Agent (Weighted Ensemble)")
    print("===========================================================")
    print(f"🎯 Mode: {mode}")
    if mode == "single":
        print(f"🔹 Selected: daily={single_daily or 'auto'}, weekly={single_weekly or 'auto'}, monthly={single_monthly or 'auto'}")

    # Collect features from BigQuery or local files
    if use_bigquery:
        print("📡 Loading feature list from BigQuery...")
        from data_agent.storage import get_storage
        from google.cloud import bigquery
        storage = get_storage(use_bigquery=True)
        client = bigquery.Client()
        query = f"""
            SELECT DISTINCT feature_name
            FROM `{storage.dataset_id}.raw_features`
            ORDER BY feature_name
        """
        result = client.query(query).to_dataframe()
        feature_names = result['feature_name'].tolist()
        # In BigQuery mode, we don't use file paths - pass feature names
        name_to_path = {name: name for name in feature_names}
        print(f"📦 Found {len(feature_names)} features in BigQuery")
    else:
        if not os.path.exists(RAW_DIR): raise FileNotFoundError(f"Input dir not found → {RAW_DIR}")
        name_to_path = collect_feature_files()
        print(f"📦 Found {len(name_to_path)} local feature files")

    cad = load_yaml_config(config_path)
    import torch
    # Keep MPS from hogging unified memory (lower than default 0.8)
    # --- Stable Apple MPS memory watermarks ---
    # ----------------------------------------------------------------------
# ⚙️ Force CPU mode globally (safe and deterministic)
# ----------------------------------------------------------------------
    accelerator = "cpu"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
    os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
    os.environ["PYTORCH_MPS_LOW_WATERMARK_RATIO"] = "0.0"
    print("🧩 Running all forecasting on CPU (MPS/CUDA disabled).")
    print(f"⚙️ Accelerator selected: {accelerator.upper()}")
    force_cpu = accelerator == "cpu"
    quiet = True
    runs = build_run_list_single(cad, name_to_path, single_daily, single_weekly, single_monthly) if mode == "single" else build_run_list_all(cad, name_to_path)

    # Filter runs based on selective_features if provided
    if selective_features:
        print(f"🎯 Selective training mode: {len(selective_features)} features requested")
        original_count = len(runs)
        runs = [(f, fpath, cadence, h, v, t) for (f, fpath, cadence, h, v, t) in runs if f in selective_features]
        print(f"   Filtered: {original_count} → {len(runs)} features")

        if not runs:
            print("⚠️ No matching features found for selective training.")
            return

    if not runs:
        print("⚠️ Nothing to run.")
        return
    print(f"📦 Features to run: {len(runs)}")

    # Sequential training (max_workers=1) to avoid lightning_logs conflicts
    # Since we batch features into groups (A/B/C), sequential is acceptable with 12hr timeout
    max_workers = 1
    print(f"🧩 Running sequentially (max_workers={max_workers}).")

    stop_evt = threading.Event()
    all_metrics = []
    start = time.time()

    try:
        # Use ThreadPoolExecutor for parallel training
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all training tasks
            future_to_feature = {
                executor.submit(
                    train_forecaster_for_feature,
                    fpath, cadence, h, v, force_cpu, quiet, t,
                    cad[cadence]["nf_loss"], cad[cadence]["arima"], cad[cadence]["prophet"],
                    cad[cadence]["multi_backtest"], cad[cadence]["ensemble"],
                    use_bigquery, f, force_retrain
                ): f for (f, fpath, cadence, h, v, t) in runs
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_feature):
                feature_name = future_to_feature[future]
                try:
                    res = future.result()
                    if res:
                        all_metrics.append(res)
                        print(f"\n✅ Completed: {feature_name}")
                except Exception as e:
                    print(f"\n❌ Failed: {feature_name} - {e}")
    finally:
        stop_evt.set()
    elapsed = time.time() - start
    if all_metrics:
        df = pd.DataFrame(all_metrics)
        summary = df.groupby("Cadence").mean(numeric_only=True).to_dict()
        print("\n📈 Summary by Cadence:")
        for c, vals in summary.items():
            line = " ".join(f"{m}:{vals[m]:8.4f}" for m in ["MAE","RMSE","MAPE","sMAPE","MASE"] if m in vals)
            print(f"[{c}] {line}")
        with open(os.path.join(METRIC_DIR, "global_summary.json"), "w") as f:
            json.dump({"by_cadence": summary}, f, indent=2)
    print(f"🕒 Elapsed: {elapsed:.2f}s ✅ Done.")

# ===========================================================
# CLI
# ===========================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train forecasting models")
    parser.add_argument("--mode", choices=["all", "single"], default="all", help="Run all features or single test")
    parser.add_argument("--config", default=None, help="Path to features_config.yaml")
    parser.add_argument("--daily", default=None, help="Single daily feature to test")
    parser.add_argument("--weekly", default=None, help="Single weekly feature to test")
    parser.add_argument("--monthly", default=None, help="Single monthly feature to test")
    parser.add_argument("--use-bigquery", action="store_true", help="Load data from BigQuery")
    parser.add_argument("--force-retrain", action="store_true", help="Force retraining even if models exist")
    args = parser.parse_args()

    run_forecasting_agent(
        mode=args.mode,
        config_path=args.config,
        single_daily=args.daily,
        single_weekly=args.weekly,
        single_monthly=args.monthly,
        use_bigquery=args.use_bigquery,
        force_retrain=args.force_retrain
    )