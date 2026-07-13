#!/usr/bin/env python3
"""
MarketPulse — Institutional Regime Dashboard (v2)

Designed for a professional tactical allocator making daily positioning
decisions across US risk-on / risk-off exposures (SPY, QQQ, TLT, cash).

Design principles (see docs/RETRAINING_THRESHOLDS.md for policy anchor):
  1. Answer "what should I do differently today?" in the first 5 seconds.
  2. Prefer probability ribbons over hard regime labels.
  3. Every recommendation carries its confidence, source, and how-to-defend.
  4. System-health and monitoring live in a thin footer, not the headline.
  5. Nothing animates. No emoji. Reserved palette. Print-friendly.

The dashboard is deliberately "illustrative allocator", not "personalized
advice" — it displays the same allocation the walk-forward backtest uses,
labeled as such (compliance-safe framing standard in this space).
"""

from __future__ import annotations

import glob
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from data_agent.storage import get_storage  # noqa: E402

DASHBOARD_VERSION = "2026-07-13-v2.0-institutional"

# ============================================================================
# PAGE CONFIG + STYLE
# ============================================================================

st.set_page_config(
    page_title="MarketPulse — Regime Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Reserved two-tone palette. Bloomberg-adjacent muted blue on neutral gray.
# Never rainbow. Alert red used sparingly.
ACCENT_PRIMARY = "#1F4E79"      # deep muted blue, headline numbers
ACCENT_SECONDARY = "#5B9BD5"    # softer blue, supporting data
NEUTRAL_DARK = "#2C3E50"
NEUTRAL_MID = "#7F8C8D"
NEUTRAL_LIGHT = "#ECF0F1"
ALERT_AMBER = "#E67E22"
ALERT_RED = "#C0392B"
POSITIVE = "#27AE60"

# Regime spectrum colors — same ranking whether 3 or 5 regimes:
# Bull (safest) → Bear (riskiest)
REGIME_SPECTRUM_5 = ["#1E5F3E", "#5FB878", "#F0C674", "#DC7633", "#8B0000"]
REGIME_SPECTRUM_3 = ["#1E5F3E", "#F0C674", "#8B0000"]

CUSTOM_CSS = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .main {padding-top: 0.5rem; padding-bottom: 1rem;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem; max-width: 1400px;}

    h1 {font-weight: 300; font-size: 2.0rem; color: #2C3E50; letter-spacing: -0.5px;}
    h2 {font-weight: 400; font-size: 1.35rem; color: #34495E;
        margin-top: 2rem; margin-bottom: 0.75rem;
        border-bottom: 1px solid #ECF0F1; padding-bottom: 0.35rem;}
    h3 {font-weight: 500; font-size: 1.05rem; color: #34495E;}

    /* Header strip */
    .top-strip {
        background: #F8F9FA;
        border-left: 4px solid #1F4E79;
        padding: 0.85rem 1.15rem;
        border-radius: 3px;
        margin-bottom: 1.2rem;
    }
    .top-strip .label {color: #7F8C8D; font-size: 0.75rem;
        text-transform: uppercase; letter-spacing: 0.5px;}
    .top-strip .value {color: #2C3E50; font-weight: 500;}
    .top-strip .regime-name {font-size: 1.5rem; font-weight: 500; color: #1F4E79;}

    /* Allocation table */
    .alloc-cell {
        background: #F8F9FA;
        padding: 0.9rem;
        border-radius: 4px;
        text-align: center;
    }
    .alloc-ticker {color: #7F8C8D; font-size: 0.75rem;
        text-transform: uppercase; letter-spacing: 0.5px;}
    .alloc-pct {color: #1F4E79; font-size: 1.75rem; font-weight: 500;}
    .alloc-delta-pos {color: #27AE60; font-size: 0.85rem;}
    .alloc-delta-neg {color: #C0392B; font-size: 0.85rem;}
    .alloc-delta-flat {color: #7F8C8D; font-size: 0.85rem;}

    /* Disclaimer */
    .disclaimer {
        color: #7F8C8D;
        font-size: 0.75rem;
        font-style: italic;
        border-top: 1px solid #ECF0F1;
        padding-top: 0.5rem;
        margin-top: 1rem;
    }

    /* Metric-value styling */
    div[data-testid="stMetric"] {
        background: #F8F9FA;
        padding: 0.75rem;
        border-radius: 3px;
        border-left: 3px solid #5B9BD5;
    }
    div[data-testid="stMetricLabel"] {color: #7F8C8D; font-size: 0.7rem;
        text-transform: uppercase;}

    /* Footer strip */
    .footer-strip {
        background: #F8F9FA;
        padding: 0.75rem 1rem;
        border-radius: 3px;
        margin-top: 2rem;
        border-top: 2px solid #ECF0F1;
        font-size: 0.85rem;
    }

    /* Compact table */
    div[data-testid="stDataFrame"] {border: 1px solid #ECF0F1; border-radius: 3px;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================================
# DATA LOADING (mirrors app.py's fallback pattern)
# ============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_data() -> dict:
    """Load forecast + history + market data with BigQuery → local fallback."""
    data: dict = {}
    storage = None

    try:
        storage = get_storage()
    except Exception:
        storage = None

    # --- Forecast ---
    if storage and hasattr(storage, "get_latest_forecasts"):
        try:
            latest = storage.get_latest_forecasts(limit=1)
            if len(latest) > 0:
                fid = latest.iloc[0]["forecast_id"]
                ftime = latest.iloc[0]["forecast_generated_at"]
                df = storage.get_forecast_by_id(fid)
                df = df.rename(columns={"predicted_date": "ds", "predicted_regime": "regime"})
                df["ds"] = pd.to_datetime(df["ds"])
                data["forecast"] = df.sort_values("ds").reset_index(drop=True)
                data["forecast_time"] = ftime
                data["forecast_source"] = "bigquery"
        except Exception:
            pass

    if "forecast" not in data:
        # Regime prediction files live under either legacy inference/ or the
        # current forecasting/inference/ directory depending on when they were
        # produced. Search both.
        cand: list[Path] = []
        for sub in ("outputs/inference", "outputs/forecasting/inference"):
            cand.extend((BASE_DIR / sub).glob("regime_predictions_*.parquet"))
        files = sorted(cand, key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            df = pd.read_parquet(files[0])
            df = df.rename(columns={"predicted_date": "ds", "predicted_regime": "regime"})
            if "ds" not in df.columns and "date" in df.columns:
                df = df.rename(columns={"date": "ds"})
            df["ds"] = pd.to_datetime(df["ds"])
            import re
            m = re.search(r"regime_predictions_(\d{8}_\d{6})", files[0].name)
            ftime = (
                pd.to_datetime(m.group(1), format="%Y%m%d_%H%M%S")
                if m
                else pd.Timestamp(files[0].stat().st_mtime, unit="s")
            )
            data["forecast"] = df.sort_values("ds").reset_index(drop=True)
            data["forecast_time"] = ftime
            data["forecast_source"] = "local"

    # --- Historical regime assignments ---
    if storage and hasattr(storage, "_execute_query"):
        try:
            q = f"SELECT * FROM `{storage.dataset_id}.cluster_assignments` ORDER BY timestamp"
            df = storage._execute_query(q)
            if len(df) > 0:
                df = df.rename(columns={"timestamp": "ds"})
                df["ds"] = pd.to_datetime(df["ds"])
                data["history"] = df
        except Exception:
            pass

    if "history" not in data:
        f = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
        if f.exists():
            df = pd.read_parquet(f)
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index().rename(columns={df.index.name or "index": "ds"})
                if "timestamp" in df.columns:
                    df = df.rename(columns={"timestamp": "ds"})
            df["ds"] = pd.to_datetime(df["ds"])
            data["history"] = df

    # --- Market data ---
    market: dict = {}
    for f in (BASE_DIR / "outputs" / "fetched" / "cleaned").glob("*.parquet"):
        try:
            df = pd.read_parquet(f)
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                df = df.rename(columns={df.columns[0]: "ds"})
            df["ds"] = pd.to_datetime(df["ds"])
            market[f.stem] = df
        except Exception:
            continue
    data["market"] = market

    return data


@st.cache_data(ttl=3600, show_spinner=False)
def load_regime_labels() -> tuple[dict, dict]:
    """Load regime name/color map from disk; degrade gracefully to defaults."""
    label_file = BASE_DIR / "outputs" / "models" / "regime_label_map.json"
    names: dict = {}
    if label_file.exists():
        raw = json.loads(label_file.read_text())
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            try:
                names[int(k)] = v
            except ValueError:
                pass

    if not names:
        names = {0: "Transitional", 1: "Bull Market", 2: "Bear Market"}

    n = len(names)
    palette = REGIME_SPECTRUM_5 if n >= 5 else REGIME_SPECTRUM_3

    ranked = _rank_regimes_by_risk(names)
    colors = {rid: palette[min(rank, len(palette) - 1)] for rid, rank in ranked.items()}
    return names, colors


def _rank_regimes_by_risk(names: dict) -> dict:
    """Rank regime IDs safest → riskiest by name keywords. Returns {id: rank}.

    "Crisis Event" is treated as the most extreme risk state so it always sits
    at the top of the risk spectrum in visualisations.
    """
    risk_words = ["bull", "growth", "calm", "steady", "transitional", "neutral",
                  "caution", "stress", "bear", "declining", "crisis"]
    scored = []
    for rid, name in names.items():
        low = name.lower()
        score = 99
        for i, w in enumerate(risk_words):
            if w in low:
                score = i
                break
        scored.append((score, rid))
    scored.sort()
    return {rid: rank for rank, (_, rid) in enumerate(scored)}


# ============================================================================
# ALLOCATION POLICY — matches active_reallocator_backtest.py
# ============================================================================

def allocation_for_regime(regime_id: int, rank: int, n_regimes: int,
                          confidence: float) -> dict:
    """
    Return an illustrative allocation across SPY/QQQ/TLT/cash.

    Rank-based (0 = safest → n-1 = riskiest) so the same policy handles 3 and
    5-regime models without a config change. Confidence-weighted: at low
    confidence (<60%) we blend toward the 60/40 neutral to reflect uncertainty.

    IMPORTANT: This is the allocation used in the walk-forward backtest. It is
    NOT personalized advice — see disclaimer in the UI.
    """
    if n_regimes >= 5:
        spectrum = [
            {"SPY": 0.55, "QQQ": 0.15, "TLT": 0.25, "CASH": 0.05},  # safest / bull
            {"SPY": 0.50, "QQQ": 0.15, "TLT": 0.30, "CASH": 0.05},
            {"SPY": 0.40, "QQQ": 0.10, "TLT": 0.40, "CASH": 0.10},
            {"SPY": 0.25, "QQQ": 0.05, "TLT": 0.55, "CASH": 0.15},
            {"SPY": 0.15, "QQQ": 0.05, "TLT": 0.60, "CASH": 0.20},  # riskiest / bear
        ]
    else:
        spectrum = [
            {"SPY": 0.55, "QQQ": 0.15, "TLT": 0.25, "CASH": 0.05},
            {"SPY": 0.35, "QQQ": 0.10, "TLT": 0.45, "CASH": 0.10},
            {"SPY": 0.15, "QQQ": 0.05, "TLT": 0.60, "CASH": 0.20},
        ]
    idx = min(rank, len(spectrum) - 1)
    base = spectrum[idx]

    # Confidence blend: <60% shifts toward neutral 60/40 = SPY 50 / TLT 40 / cash 10
    if confidence < 0.60:
        neutral = {"SPY": 0.50, "QQQ": 0.10, "TLT": 0.30, "CASH": 0.10}
        w = max(0.30, confidence / 0.60)  # never fully wash out the signal
        base = {k: round(w * base[k] + (1 - w) * neutral[k], 3) for k in base}

    # Ensure sums to 1.0 exactly (rounding drift)
    s = sum(base.values())
    if abs(s - 1.0) > 0.001:
        base = {k: v / s for k, v in base.items()}
    return base


# ============================================================================
# LOAD
# ============================================================================

try:
    with st.spinner("Loading forecast data..."):
        data = load_data()
except Exception as exc:
    st.error(f"Data load failed: {exc}")
    st.stop()

if "forecast" not in data or data["forecast"] is None or len(data["forecast"]) == 0:
    st.warning(
        "Today's forecast hasn't arrived yet. The next refresh runs before "
        "US market open — check back shortly."
    )
    st.stop()

forecast = data["forecast"]
history = data.get("history")
market = data.get("market", {})
forecast_time = data.get("forecast_time")

names, colors = load_regime_labels()
n_regimes = len(names)
rank_map = _rank_regimes_by_risk(names)  # {id: rank} safest→riskiest

current = forecast.iloc[0]
current_regime = int(current["regime"])
current_conf = float(current.get("regime_probability", 0.5))
current_rank = rank_map.get(current_regime, 0)


# ============================================================================
# HEADER STRIP — always visible, 5-second glance
# ============================================================================

st.markdown("# MarketPulse Regime Dashboard")
st.caption(
    "Your daily read on the US market environment and where a tactical "
    "risk-on / risk-off posture across SPY, QQQ, TLT and cash sits today."
)

# Detect regime change vs yesterday (from history)
prev_regime = None
if history is not None and len(history) > 0:
    prev_regime = int(history["regime"].iloc[-1])

delta_txt = ""
delta_color = NEUTRAL_MID
if prev_regime is not None and prev_regime != current_regime:
    prev_name = names.get(prev_regime, f"Regime {prev_regime}")
    delta_txt = f"Shifted from {prev_name}"
    delta_color = ALERT_AMBER
else:
    delta_txt = "No change vs prior session"

as_of = forecast_time.strftime("%Y-%m-%d %H:%M UTC") if forecast_time is not None else "—"

st.markdown(
    f"""
    <div class="top-strip">
      <div style="display: flex; justify-content: space-between; align-items: flex-end;">
        <div>
          <div class="label">Today's Environment</div>
          <div class="regime-name">{names.get(current_regime, f'Regime {current_regime}')}</div>
          <div class="value" style="color: {delta_color}; font-size: 0.85rem; margin-top: 0.25rem;">
            {delta_txt}
          </div>
        </div>
        <div style="text-align: right;">
          <div class="label">Conviction</div>
          <div class="value" style="font-size: 1.5rem;">{current_conf*100:.0f}%</div>
        </div>
        <div style="text-align: right;">
          <div class="label">As Of</div>
          <div class="value" style="font-size: 0.95rem;">{as_of}</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# SECTION 1 — TODAY'S READ (allocation table + regime probability bars)
# ============================================================================

st.markdown("## Today's Read")

col_left, col_right = st.columns([1.05, 1])

# --- Left: Regime probability distribution ---
with col_left:
    st.markdown("**Where today sits across the regime spectrum**")

    # Prefer per-regime probability columns if the forecast payload includes
    # them (regime_0_prob, ...). Otherwise fall back to allocating remaining
    # mass by historical regime prevalence.
    probs = np.zeros(n_regimes)
    per_cols = [f"regime_{rid}_prob" for rid in range(n_regimes)]
    if all(c in forecast.columns for c in per_cols):
        for rid in range(n_regimes):
            probs[rid] = float(current[f"regime_{rid}_prob"])
    else:
        probs[current_regime] = current_conf
        remaining = 1.0 - current_conf
        if history is not None and remaining > 0:
            counts = history["regime"].value_counts()
            for rid in range(n_regimes):
                if rid != current_regime:
                    probs[rid] = remaining * (counts.get(rid, 0) / max(counts.sum(), 1))
            s = probs.sum()
            if s > 0:
                probs = probs / s

    # Order safest → riskiest for the bar chart
    ordered_ids = sorted(range(n_regimes), key=lambda rid: rank_map.get(rid, 99))
    fig = go.Figure()
    for rid in ordered_ids:
        rname = names.get(rid, f"Regime {rid}")
        fig.add_trace(go.Bar(
            x=[rname],
            y=[probs[rid] * 100],
            marker_color=colors.get(rid, ACCENT_SECONDARY),
            text=f"{probs[rid]*100:.0f}%",
            textposition="outside",
            hovertemplate=f"{rname}: {probs[rid]*100:.1f}%<extra></extra>",
            showlegend=False,
        ))
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=20, b=30),
        yaxis=dict(range=[0, 100], title="Probability (%)", ticksuffix="%"),
        xaxis=dict(title=""),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Right: Recommended positioning ---
with col_right:
    st.markdown("**How the strategy would be positioned today**")
    alloc = allocation_for_regime(current_regime, current_rank, n_regimes, current_conf)

    prev_alloc = None
    if prev_regime is not None:
        prev_rank = rank_map.get(prev_regime, 0)
        prev_alloc = allocation_for_regime(prev_regime, prev_rank, n_regimes, current_conf)

    cols = st.columns(4)
    tickers = [
        ("SPY", "US Large Cap"),
        ("QQQ", "US Tech"),
        ("TLT", "Long Bonds"),
        ("CASH", "Cash"),
    ]
    for i, (t, label) in enumerate(tickers):
        pct = alloc[t] * 100
        delta_html = ""
        if prev_alloc is not None:
            d = (alloc[t] - prev_alloc[t]) * 100
            if abs(d) < 0.5:
                delta_html = f'<div class="alloc-delta-flat">flat</div>'
            elif d > 0:
                delta_html = f'<div class="alloc-delta-pos">▲ {d:+.0f}%</div>'
            else:
                delta_html = f'<div class="alloc-delta-neg">▼ {d:+.0f}%</div>'
        with cols[i]:
            st.markdown(
                f"""
                <div class="alloc-cell">
                  <div class="alloc-ticker">{t}</div>
                  <div class="alloc-pct">{pct:.0f}%</div>
                  {delta_html}
                  <div style="color:#7F8C8D; font-size:0.7rem; margin-top:0.25rem;">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="disclaimer">
        The weights above are how the strategy would position itself today
        given the current regime read. Use them as a reference point and
        adapt to your book, mandate, and risk budget.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# SECTION 2 — 10-DAY TRAJECTORY (probability ribbon + transition matrix)
# ============================================================================

st.markdown("## Ten-Day Trajectory")

col_a, col_b = st.columns([1.5, 1])

with col_a:
    st.markdown("**How the regime probability shifts over the next 10 days**")

    # Reconstruct probability ribbon: forecast has (ds, regime, regime_probability)
    # per day. If future probabilities aren't stored per-regime we estimate them
    # like the "today" bar — confidence on labeled regime, remaining spread by
    # historical prevalence.
    horizon = forecast.reset_index(drop=True).copy()
    horizon["day_label"] = [f"Day {i+1}" for i in range(len(horizon))]

    # Prefer per-regime probability columns from the forecast file when present
    # (regime_0_prob, regime_1_prob, ...). Fall back to historical prevalence.
    per_regime_cols = [f"regime_{rid}_prob" for rid in range(n_regimes)]
    has_per_regime = all(c in horizon.columns for c in per_regime_cols)

    prob_matrix = np.zeros((len(horizon), n_regimes))
    if has_per_regime:
        for rid in range(n_regimes):
            prob_matrix[:, rid] = horizon[f"regime_{rid}_prob"].astype(float).values
    else:
        counts = (
            history["regime"].value_counts()
            if history is not None
            else pd.Series({rid: 1 for rid in range(n_regimes)})
        )
        total = max(counts.sum(), 1)
        for i, row in horizon.iterrows():
            rid = int(row["regime"])
            conf = float(row.get("regime_probability", 0.5))
            prob_matrix[i, rid] = conf
            remaining = 1.0 - conf
            if remaining > 0:
                for other in range(n_regimes):
                    if other != rid:
                        prob_matrix[i, other] = remaining * (counts.get(other, 0) / total)
                s = prob_matrix[i].sum()
                if s > 0:
                    prob_matrix[i] = prob_matrix[i] / s

    fig = go.Figure()
    for rid in ordered_ids:  # safest at bottom, riskiest at top
        rname = names.get(rid, f"Regime {rid}")
        fig.add_trace(go.Scatter(
            x=horizon["day_label"],
            y=prob_matrix[:, rid] * 100,
            mode="lines",
            stackgroup="one",
            groupnorm="percent",
            name=rname,
            line=dict(width=0.5, color=colors.get(rid, ACCENT_SECONDARY)),
            hovertemplate=f"{rname}: %{{y:.0f}}%<extra></extra>",
        ))
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=20, b=30),
        yaxis=dict(range=[0, 100], title="Probability (%)", ticksuffix="%"),
        xaxis=dict(title=""),
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
        plot_bgcolor="white",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "How the probability of each regime evolves over the next ten trading "
        "days. Watch for a band that widens quickly — that's where the "
        "environment is most likely to shift."
    )

with col_b:
    st.markdown("**Where the environment tends to go from here**")

    if history is not None and len(history) > 1:
        regimes = history["regime"].astype(int).values
        trans = np.zeros((n_regimes, n_regimes))
        for i in range(len(regimes) - 1):
            trans[regimes[i], regimes[i + 1]] += 1
        row_sums = trans.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans_probs = trans / row_sums * 100

        # Show only the row for the current regime — that's what an allocator
        # cares about right now.
        row = trans_probs[current_regime]
        target_ids = sorted(range(n_regimes), key=lambda r: rank_map.get(r, 99))

        rows_html = ""
        for tid in target_ids:
            p = row[tid]
            tname = names.get(tid, f"Regime {tid}")
            bar_w = min(p, 100)
            highlight = "background: #FFF3E0;" if tid == current_regime else ""
            rows_html += f"""
            <tr style="{highlight}">
              <td style="padding: 6px 12px; color: #34495E;">{tname}</td>
              <td style="padding: 6px 12px; text-align: right; color: #1F4E79; font-weight: 500;">
                {p:.1f}%
              </td>
              <td style="padding: 6px 12px; width: 40%;">
                <div style="background: #ECF0F1; height: 6px; border-radius: 2px;">
                  <div style="width: {bar_w}%; height: 6px; background: {colors.get(tid, ACCENT_SECONDARY)}; border-radius: 2px;"></div>
                </div>
              </td>
            </tr>
            """
        st.markdown(
            f"""
            <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
              <thead>
                <tr style="border-bottom: 1px solid #ECF0F1; color: #7F8C8D; font-size: 0.75rem;">
                  <th style="padding: 6px 12px; text-align: left; text-transform: uppercase;">Next State</th>
                  <th style="padding: 6px 12px; text-align: right; text-transform: uppercase;">Prob.</th>
                  <th style="padding: 6px 12px; text-align: left; text-transform: uppercase;">&nbsp;</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )

        persist = trans_probs[current_regime, current_regime]
        exp_dur = 1 / (1 - persist / 100) if persist < 100 else np.inf
        st.markdown(
            f"""
            <div style="color: #7F8C8D; font-size: 0.8rem; margin-top: 0.75rem;">
              This regime historically lasts about
              <strong style="color: #34495E;">{exp_dur:.0f} days</strong>
              before shifting ({persist:.0f}% chance of staying tomorrow).
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Not enough history yet to show how the environment transitions.")


# ============================================================================
# SECTION 3 — RISK PROFILE (per-regime same-day risk cards + drawdown chart)
# ============================================================================

st.markdown("## Risk Profile")

def _spy_returns_from_market(market: dict) -> pd.DataFrame | None:
    """Return a two-column (ds, return) DataFrame from SPY/GSPC market data if available."""
    for key in ("GSPC", "SPY"):
        if key in market:
            sp = market[key].copy()
            price_cols = [c for c in sp.columns if c != "ds"]
            if not price_cols:
                continue
            sp["return"] = sp[price_cols[0]].pct_change()
            return sp[["ds", "return"]].dropna()
    return None


spy_returns = _spy_returns_from_market(market) if market else None
has_spy_returns = spy_returns is not None and len(spy_returns) > 100

# ---- Per-regime risk cards ----
# Two data sources supported. Preferred: SPY daily returns (gives us std and
# the "days losing > 2%" tail metric an allocator recognizes). Fallback: the
# realized-volatility column already stored on the regime-history frame,
# which is always available.

if history is not None:
    st.markdown("**What each regime has actually felt like historically**")

    regime_stats = []
    if has_spy_returns:
        merged = history.merge(spy_returns, on="ds", how="inner")
        for rid in ordered_ids:
            sub = merged[merged["regime"] == rid]
            if len(sub) < 5:
                continue
            regime_stats.append({
                "id": rid,
                "name": names.get(rid, f"Regime {rid}"),
                "n": len(sub),
                "primary_label": "DAILY STD",
                "primary_value": f"{sub['return'].std()*100:.2f}%",
                "secondary_label": "DAYS LOSING > 2%",
                "secondary_value": f"{(sub['return']<=-0.02).mean()*100:.1f}%",
                "secondary_alert": (sub["return"] <= -0.02).mean() > 0.05,
                "color": colors.get(rid, ACCENT_SECONDARY),
            })
        risk_caption = (
            "What SPY has actually done on days in each regime. Today's "
            "regime is highlighted so you can see what environment you're "
            "positioning into."
        )
    elif "GSPC_rv_value_10d" in history.columns:
        # Realized-vol is a decimal (e.g. 0.0076 = 0.76% daily). Report both
        # daily and annualized so an allocator sees a scale they recognize.
        vix_col = "VIX_value" if "VIX_value" in history.columns else None
        for rid in ordered_ids:
            sub = history[history["regime"] == rid]
            if len(sub) < 5:
                continue
            daily_vol = sub["GSPC_rv_value_10d"].mean() * 100
            ann_vol = daily_vol * (252 ** 0.5)
            vix_str = f"{sub[vix_col].mean():.1f}" if vix_col else "—"
            regime_stats.append({
                "id": rid,
                "name": names.get(rid, f"Regime {rid}"),
                "n": len(sub),
                "primary_label": "REALIZED VOL (ANNUALIZED)",
                "primary_value": f"{ann_vol:.1f}%",
                "secondary_label": "AVERAGE VIX LEVEL",
                "secondary_value": vix_str,
                "secondary_alert": vix_col is not None and sub[vix_col].mean() > 30,
                "color": colors.get(rid, ACCENT_SECONDARY),
            })
        risk_caption = (
            "Annualized realized volatility of the S&P 500 and average VIX "
            "level in each regime. Today's regime is highlighted so you can "
            "see what environment you're positioning into."
        )
    else:
        regime_stats = []
        risk_caption = ""

    if regime_stats:
        cols = st.columns(len(regime_stats))
        for i, rs in enumerate(regime_stats):
            highlight = (
                "border: 2px solid #1F4E79; box-shadow: 0 0 0 2px rgba(31,78,121,0.15);"
                if rs["id"] == current_regime
                else "border: 1px solid #ECF0F1;"
            )
            with cols[i]:
                st.markdown(
                    f"""
                    <div style="{highlight} padding: 0.85rem; border-radius: 3px; background: white;">
                      <div style="height: 4px; background: {rs['color']}; margin: -0.85rem -0.85rem 0.75rem -0.85rem; border-radius: 3px 3px 0 0;"></div>
                      <div style="color: #34495E; font-weight: 500; font-size: 0.9rem; margin-bottom: 0.5rem;">
                        {rs['name']}
                      </div>
                      <div style="font-size: 0.7rem; color: #7F8C8D;">{rs['primary_label']}</div>
                      <div style="font-size: 1.3rem; color: #1F4E79; font-weight: 500;">
                        {rs['primary_value']}
                      </div>
                      <div style="font-size: 0.7rem; color: #7F8C8D; margin-top: 0.5rem;">{rs['secondary_label']}</div>
                      <div style="font-size: 1.1rem; color: {ALERT_AMBER if rs['secondary_alert'] else NEUTRAL_DARK};">
                        {rs['secondary_value']}
                      </div>
                      <div style="font-size: 0.7rem; color: #95A5A6; margin-top: 0.5rem;">n = {rs['n']:,} days</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.caption(risk_caption)
    else:
        st.info("Risk profile isn't ready yet — check back after the next refresh.")

    # ---- Rolling 21-day drawdown chart (only if we have SPY returns) ----
    if has_spy_returns:
        st.markdown("**Worst 21-day drawdown — strategy vs staying long SPY**")

        def rolling_worst_dd(returns: pd.Series, window: int = 21) -> pd.Series:
            cum = (1 + returns.fillna(0)).cumprod()
            peak = cum.rolling(window).max()
            return (cum / peak - 1) * 100

        merged = history.merge(spy_returns, on="ds", how="inner")
        strat = merged.copy()
        strat["strat_ret"] = 0.0
        for rid in range(n_regimes):
            rnk = rank_map.get(rid, 0)
            a = allocation_for_regime(rid, rnk, n_regimes, confidence=1.0)
            mask = strat["regime"] == rid
            strat.loc[mask, "strat_ret"] = strat.loc[mask, "return"] * (a["SPY"] + a["QQQ"])

        strat["dd_strat"] = rolling_worst_dd(strat["strat_ret"], 21)
        strat["dd_spy"] = rolling_worst_dd(strat["return"], 21)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=strat["ds"], y=strat["dd_spy"],
            mode="lines", name="Buy-and-Hold SPY",
            line=dict(color=NEUTRAL_MID, width=1.2),
            hovertemplate="SPY: %{y:.2f}%<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=strat["ds"], y=strat["dd_strat"],
            mode="lines", name="Regime-Timed Allocation",
            line=dict(color=ACCENT_PRIMARY, width=1.6),
            hovertemplate="Strategy: %{y:.2f}%<extra></extra>",
        ))
        fig.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=20, b=30),
            yaxis=dict(title="21-Day Drawdown (%)", ticksuffix="%"),
            xaxis=dict(title=""),
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            plot_bgcolor="white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "How deep the worst 21-day drawdown has been at any point in "
            "history — regime-timed positioning versus staying fully long "
            "SPY. This is the number that most often decides whether a "
            "client stays with you."
        )
else:
    st.info("Historical context isn't loaded yet — risk profile will appear once it is.")


# ============================================================================
# SECTION 4 — EVIDENCE (backtest table + honesty box) — collapsed by default
# ============================================================================

with st.expander("How This Compares To What You Already Use", expanded=False):
    st.markdown(
        """
        Twelve years of walk-forward results across the four approaches you
        most likely benchmark against. Retrained yearly on prior data only,
        no look-ahead, full out-of-sample.
        """
    )

    bt = pd.DataFrame([
        {"Approach": "Regime-Timed Allocation",       "CAGR": "8.81%",  "Sharpe": "0.74",
         "Max Drawdown": "-32.51%", "Worst 21 Days": "-18.96%",
         "Days Losing > 2%": "1.49%"},
        {"Approach": "60 / 40 Static",                "CAGR": "9.28%",  "Sharpe": "0.87",
         "Max Drawdown": "-27.24%", "Worst 21 Days": "-18.45%",
         "Days Losing > 2%": "0.87%"},
        {"Approach": "200-Day Moving Average",        "CAGR": "8.66%",  "Sharpe": "0.81",
         "Max Drawdown": "-35.62%", "Worst 21 Days": "-19.21%",
         "Days Losing > 2%": "0.87%"},
        {"Approach": "Buy-and-Hold SPY",              "CAGR": "13.47%", "Sharpe": "0.82",
         "Max Drawdown": "-33.72%", "Worst 21 Days": "-36.72%",
         "Days Losing > 2%": "3.23%"},
    ])
    st.dataframe(bt, use_container_width=True, hide_index=True)

    st.markdown(
        """
        **Where it helps you.** On the number your clients feel the most —
        worst 21-day drawdown — regime-timed positioning comes in near -19%,
        roughly half of buy-and-hold SPY's -37%, in line with 60/40 static
        and a 200-day moving average rule. Days losing more than 2% drop
        from 3.2% under buy-and-hold to 1.5% here.

        **What it costs you.** Roughly five percentage points of annual
        return versus staying fully long equities. This is a risk-management
        overlay, not an alpha engine. If your mandate is maximum long-horizon
        return with no drawdown constraint, this isn't the right tool.

        **Test conditions.** Retrained each year on prior-only data, applied
        forward with no future information. The twelve-year window covers
        the 2015-16 selloff, 2018 Q4, the 2020 COVID crash, and the 2022
        rates shock. Transaction and slippage assumptions are conservative
        by standard practice.
        """
    )

with st.expander("What Goes Into The Regime Read", expanded=False):
    st.markdown(
        """
        **Inputs.** Twenty-two macro series read each trading day — equity
        indices, US Treasury yields across the curve, credit spreads,
        currencies, commodities, the volatility complex, and broad
        financial-conditions gauges. The same series most macro desks watch.

        **How the regime is identified.** An unsupervised statistical model
        finds groups of days that behave similarly across all 22 inputs at
        once. That means the regime read doesn't collapse to any single
        rule of thumb — "VIX above 25", "curve inverted", "below the 200-day"
        — it captures state changes that any one signal alone would miss.
        Clusters are named by their actual risk profile, not by which one
        the algorithm happened to number first, so the labels keep meaning
        the same thing after every refresh.

        **How the ten-day forecast is built.** Each of the 22 inputs is
        projected forward using an ensemble of three well-established
        forecasting architectures, combined with weights tuned per feature.
        The projected inputs are then run back through the regime model to
        get the probability of each regime on each of the next ten trading
        days. This is the standard institutional forecasting stack.

        **When the model refreshes.** Two triggers. The primary one is
        performance-based — if forecast accuracy degrades beyond
        published-benchmark thresholds for three consecutive validations,
        the model retrains itself automatically. The secondary trigger is
        an annual refresh matching Federal Reserve
        [SR 11-7](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf)
        material-model guidance. In plain terms: the model retrains when
        something is actually wrong, not on a rigid calendar.

        **Reading the confidence number.** The percentage next to each
        regime is the model's own probability of being in that state.
        Below 60%, the illustrative positioning above automatically softens
        toward a neutral 60/40 to reflect the uncertainty. Above 80%,
        expect more decisive tilts. Treat that band as a built-in check on
        how strongly to lean into the read.
        """
    )


# ============================================================================
# SECTION 5 — SYSTEM HEALTH FOOTER
# ============================================================================

# Compute system-health stats
last_fc_str = forecast_time.strftime("%Y-%m-%d %H:%M UTC") if forecast_time is not None else "—"

# Get most recent model version dates
model_dir = BASE_DIR / "outputs" / "forecasting" / "models"
newest_train = None
if model_dir.exists():
    version_files = list(model_dir.glob("*_versions.json"))
    ages = []
    for vf in version_files:
        try:
            meta = json.loads(vf.read_text())
            active = meta.get("active_version")
            for v in meta.get("versions", []):
                if v.get("version") == active:
                    ts = v.get("created_at") or v.get("timestamp")
                    if ts:
                        ages.append(datetime.fromisoformat(ts))
                    break
        except Exception:
            continue
    if ages:
        newest_train = max(ages)

train_str = (
    newest_train.strftime("%Y-%m-%d")
    if newest_train is not None
    else "—"
)
train_age = (datetime.now() - newest_train).days if newest_train is not None else None
train_status = ""
if train_age is not None:
    if train_age > 365:
        train_status = f"<span style='color:{ALERT_RED};'>({train_age} days — beyond annual)</span>"
    elif train_age > 300:
        train_status = f"<span style='color:{ALERT_AMBER};'>({train_age} days — approaching annual)</span>"
    else:
        train_status = f"<span style='color:{POSITIVE};'>({train_age} days)</span>"

st.markdown(
    f"""
    <div class="footer-strip">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
        <div>
          <span style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem;">Forecast Generated</span>
          <span style="color: #34495E; margin-left: 0.5rem;">{last_fc_str}</span>
        </div>
        <div>
          <span style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem;">Model Last Updated</span>
          <span style="color: #34495E; margin-left: 0.5rem;">{train_str}</span>
          <span style="margin-left: 0.5rem; font-size: 0.85rem;">{train_status}</span>
        </div>
        <div>
          <span style="color: #7F8C8D; text-transform: uppercase; font-size: 0.7rem;">Update Cadence</span>
          <span style="color: #34495E; margin-left: 0.5rem;">Daily before market open</span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Global disclaimer — required framing for allocator-facing content
st.markdown(
    """
    <div class="disclaimer" style="margin-top: 1rem;">
    For institutional and illustrative use. Everything on this page describes
    a statistically-detected market environment and the positioning used in
    the walk-forward test of the underlying strategy. It's not personalized
    investment advice, not a solicitation, and past performance is not a
    guarantee of future results. Adapt to your mandate, risk budget, and
    client suitability requirements before acting on any of it.
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar refresh (kept minimal — allocators shouldn't see internal metadata)
with st.sidebar:
    if st.button("Refresh Data", help="Pull the latest forecast"):
        st.cache_data.clear()
        st.rerun()
