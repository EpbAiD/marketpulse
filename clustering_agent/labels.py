"""Regime label loader.

Single source of truth for converting numeric HMM regime IDs (0/1/2) into
human-readable names. The mapping is derived at training time (see
`derive_regime_label_map` in clustering.py) and persisted to
`outputs/models/regime_label_map.json` so it stays in sync with whatever
arbitrary IDs that particular HMM training run happened to assign.

Use `get_regime_names()` everywhere instead of hardcoding a dict like
`{0: "Bull", 1: "Bear", 2: "Transitional"}` — the dict literal will silently
become wrong the next time the HMM is retrained and produces different IDs.
"""
import json
import os
from pathlib import Path
from typing import Dict


_BASE_DIR = Path(__file__).resolve().parent.parent
_LABEL_MAP_PATH = _BASE_DIR / "outputs" / "models" / "regime_label_map.json"


def get_regime_names() -> Dict[int, str]:
    """Return {regime_id (int): display name} from the trained-time mapping.

    Falls back to a generic identity-style dict if the JSON is missing
    (first-time setup, broken training run). Never raises — returning a
    usable but uninformative dict is preferable to crashing the dashboard
    or daily log.
    """
    if not _LABEL_MAP_PATH.exists():
        return {0: "Regime 0", 1: "Regime 1", 2: "Regime 2"}

    try:
        with open(_LABEL_MAP_PATH) as f:
            data = json.load(f)
    except Exception:
        return {0: "Regime 0", 1: "Regime 1", 2: "Regime 2"}

    out: Dict[int, str] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue  # skip _meta entries
        try:
            out[int(k)] = str(v)
        except (TypeError, ValueError):
            continue

    if not out:
        return {0: "Regime 0", 1: "Regime 1", 2: "Regime 2"}
    return out


def get_regime_colors() -> Dict[int, str]:
    """Return {regime_id (int): hex color} keyed by display name.

    Bull/Growing → green, Bear/Declining → red, anything else → blue.
    """
    names = get_regime_names()
    color_for = {}
    for rid, name in names.items():
        lower = name.lower()
        if "bull" in lower or "growing" in lower:
            color_for[rid] = "#2ecc71"  # green
        elif "bear" in lower or "declining" in lower:
            color_for[rid] = "#e74c3c"  # red
        else:
            color_for[rid] = "#3498db"  # blue
    return color_for
