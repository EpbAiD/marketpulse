#!/usr/bin/env python3
"""
Market Regime Analysis - Institutional Dashboard
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import glob
import sys
import json

sys.path.append(str(Path(__file__).parent.parent))
from data_agent.storage import get_storage

# Try to import AlertSystem, but don't fail if orchestrator dependencies aren't available
try:
    from orchestrator.alerts import AlertSystem
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False
    AlertSystem = None

st.set_page_config(
    page_title="Market Regime Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .main {padding-top: 1rem;}
    h1 {font-weight: 300; font-size: 2.5rem;}
    h2 {font-weight: 400; font-size: 1.6rem; margin-top: 2.5rem; margin-bottom: 1rem;}
    h3 {font-weight: 400; font-size: 1.2rem;}
    .alert-box {
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid;
    }
    .alert-warning {
        background: #fff3cd;
        border-color: #ff9800;
    }
    .alert-success {
        background: #d4edda;
        border-color: #28a745;
    }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent.parent

def get_latest_file(pattern):
    files = glob.glob(str(BASE_DIR / pattern))
    return Path(max(files, key=lambda f: Path(f).stat().st_mtime)) if files else None

def load_data():
    """Load data from storage (BigQuery primary, local files fallback)"""
    data = {}
    storage = get_storage()

    # Try storage layer first for forecast data
    try:
        if hasattr(storage, 'get_latest_forecasts'):
            latest_forecasts = storage.get_latest_forecasts(limit=1)

            if len(latest_forecasts) > 0:
                forecast_id = latest_forecasts.iloc[0]['forecast_id']
                df = storage.get_forecast_by_id(forecast_id)
                df = df.rename(columns={'predicted_date': 'ds', 'predicted_regime': 'regime'})
                df['ds'] = pd.to_datetime(df['ds'])
                data['forecast'] = df.sort_values('ds').reset_index(drop=True)
                data['forecast_source'] = 'bigquery'
            else:
                # Fallback to CSV
                forecast_file = get_latest_file("outputs/inference/regime_forecast_*.csv")
                if forecast_file:
                    df = pd.read_csv(forecast_file)
                    df['ds'] = pd.to_datetime(df['ds'])
                    data['forecast'] = df
                    data['forecast_source'] = 'csv'
        else:
            # Local storage - use CSV
            forecast_file = get_latest_file("outputs/inference/regime_forecast_*.csv")
            if forecast_file:
                df = pd.read_csv(forecast_file)
                df['ds'] = pd.to_datetime(df['ds'])
                data['forecast'] = df
                data['forecast_source'] = 'csv'
    except Exception as e:
        # Fallback to CSV on any error
        forecast_file = get_latest_file("outputs/inference/regime_forecast_*.csv")
        if forecast_file:
            df = pd.read_csv(forecast_file)
            df['ds'] = pd.to_datetime(df['ds'])
            data['forecast'] = df
            data['forecast_source'] = 'csv'

    # Historical data (still from local)
    cluster_file = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
    if cluster_file.exists():
        df = pd.read_parquet(cluster_file)
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df.rename(columns={df.columns[0]: 'ds'}, inplace=True)
        df['ds'] = pd.to_datetime(df['ds'])
        data['history'] = df

    # Market data (still from local)
    market_files = list((BASE_DIR / "outputs" / "fetched" / "cleaned").glob("*.parquet"))
    if market_files:
        market_data = {}
        for f in market_files:
            df = pd.read_parquet(f)
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                df.rename(columns={df.columns[0]: 'ds'}, inplace=True)
            df['ds'] = pd.to_datetime(df['ds'])
            market_data[f.stem] = df
        data['market'] = market_data

    return data

# Load data
data = load_data()

if not data or 'forecast' not in data:
    st.warning("No forecast data available")
    st.stop()

forecast = data['forecast']
history = data.get('history')
market = data.get('market', {})

regime_names = {0: "Growing Market", 1: "Declining Market", 2: "Stable Market"}
regime_colors = {0: '#3498db', 1: '#e74c3c', 2: '#2ecc71'}

current = forecast.iloc[0]
current_regime = int(current['regime'])
current_conf = current['regime_probability']

st.title("Market Condition Forecast")
st.caption("Latest Market Outlook")

# === ALERTS ===
if ALERTS_AVAILABLE:
    try:
        # Use consolidated alert system from orchestrator
        alert_system = AlertSystem()
        alert_result = alert_system.check_for_alerts(period_days=7, min_confidence=0.6)
    except Exception as e:
        # Simple fallback if alerts fail
        alert_result = {
            'alert': False,
            'message': 'Alert system unavailable',
            'shifts': []
        }
else:
    # No alert system available (lightweight deployment)
    alert_result = {
        'alert': False,
        'message': 'No recent regime shifts detected',
        'shifts': []
    }

if alert_result['alert']:
    st.markdown(
        f"""<div class="alert-box alert-warning">
        <strong>⚠️ MARKET CHANGE DETECTED</strong><br>
        {alert_result['message']}<br>
        <small>{len(alert_result['shifts'])} weekly period shift(s) detected</small>
        </div>""",
        unsafe_allow_html=True
    )

    with st.expander("📋 View Alert Details"):
        for i, shift in enumerate(alert_result['shifts'], 1):
            st.markdown(f"""
            **Shift {i}**
            Previous: **{shift['previous_regime_name']}** ({shift['previous_confidence']*100:.1f}%)
            New: **{shift['new_regime_name']}** ({shift['new_confidence']*100:.1f}%)
            """)
else:
    st.markdown(
        f"""<div class="alert-box alert-success">
        <strong>✓ Market Conditions Stable</strong><br>
        {alert_result['message']}
        </div>""",
        unsafe_allow_html=True
    )

st.divider()

# === MODEL PERFORMANCE MONITORING ===
try:
    # Try to load validation results from storage
    storage = get_storage()
    if hasattr(storage, 'get_validation_summary'):
        validation_summary = storage.get_validation_summary()

        if validation_summary:
            st.subheader("🔧 Model Performance (Internal Validation)")
            st.caption("Forecast accuracy from SMAPE-based validation")

            col1, col2, col3 = st.columns(3)
            with col1:
                accuracy = (1 - validation_summary.get('avg_smape', 0) / 100) if validation_summary.get('avg_smape', 0) <= 100 else 0
                st.metric("Forecast Accuracy", f"{accuracy*100:.1f}%",
                         help="Based on SMAPE error metric")
            with col2:
                st.metric("Avg SMAPE", f"{validation_summary.get('avg_smape', 0):.1f}%",
                         help="Symmetric Mean Absolute Percentage Error")
            with col3:
                st.metric("Forecasts Validated", int(validation_summary.get('total_forecasts', 0)),
                         help="Number of past forecasts validated")
    else:
        # Fallback to local validation log
        validation_log_file = BASE_DIR / "outputs" / "validation_log.jsonl"

        if validation_log_file.exists():
            st.subheader("🔧 Model Performance (Internal Validation)")
            st.caption("Forecast accuracy from SMAPE-based validation")

            with open(validation_log_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    latest_validation = json.loads(lines[-1])
                    metrics = latest_validation.get('metrics', {})

                    col1, col2 = st.columns(2)
                    with col1:
                        avg_smape = metrics.get('avg_smape', 0)
                        accuracy = (1 - avg_smape / 100) if avg_smape <= 100 else 0
                        st.metric("Forecast Accuracy", f"{accuracy*100:.1f}%",
                                 help="Based on SMAPE error metric")
                    with col2:
                        st.metric("Forecasts Validated", int(metrics.get('total_forecasts', 0)),
                                 help="Number of past forecasts validated")
except Exception as e:
    pass  # Skip validation metrics if unavailable

st.divider()

# === CURRENT OUTLOOK ===
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

with col1:
    st.markdown(f"### {regime_names[current_regime]}")
    st.markdown(f"**Confidence:** {current_conf*100:.1f}%")

with col2:
    future_regimes = forecast.iloc[1:]['regime'].value_counts()
    if len(future_regimes) > 0:
        next_likely = int(future_regimes.index[0])
        next_pct = (future_regimes.iloc[0] / len(forecast.iloc[1:])) * 100
        st.metric("Next Likely", regime_names[next_likely], f"{next_pct:.0f}%")

with col3:
    days_ahead = len(forecast)
    st.metric("Forecast Days", days_ahead)

with col4:
    avg_conf = forecast['regime_probability'].mean()
    st.metric("Avg Confidence", f"{avg_conf*100:.1f}%")

# Forecast timeline
fig = go.Figure()
# Create day labels (Day 1, Day 2, etc.)
forecast['day_label'] = [f"Day {i+1}" for i in range(len(forecast))]
for regime_id in [0, 1, 2]:
    mask = forecast['regime'] == regime_id
    if mask.any():
        fig.add_trace(go.Scatter(
            x=forecast[mask]['day_label'],
            y=[regime_id] * mask.sum(),
            mode='markers',
            marker=dict(size=14, color=regime_colors[regime_id], symbol='square'),
            name=regime_names[regime_id],
            hovertemplate='%{x}<br>' + regime_names[regime_id] + '<extra></extra>'
        ))

fig.update_layout(
    height=180,
    margin=dict(l=20, r=20, t=10, b=20),
    xaxis=dict(title="Forecast Horizon"),
    yaxis=dict(
        tickmode='array',
        tickvals=[0, 1, 2],
        ticktext=['Growing Market', 'Declining Market', 'Stable Market']
    ),
    showlegend=False,
    hovermode='closest'
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# === TRANSITION MATRIX & EXPECTED DURATION ===
if history is not None and len(history) > 1:
    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("How Market Conditions Change Over Time")

        regimes = history['regime'].values
        transitions = np.zeros((3, 3))
        for i in range(len(regimes) - 1):
            transitions[int(regimes[i]), int(regimes[i + 1])] += 1

        row_sums = transitions.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans_probs = transitions / row_sums * 100

        fig = go.Figure(data=go.Heatmap(
            z=trans_probs,
            x=['Consolidation', 'Expansion', 'Compression'],
            y=['Consolidation', 'Expansion', 'Compression'],
            colorscale='Blues',
            text=np.round(trans_probs, 1),
            texttemplate='%{text}%',
            textfont={"size": 12},
            hovertemplate='%{y} → %{x}: %{z:.1f}%<extra></extra>'
        ))

        fig.update_layout(
            height=300,
            margin=dict(l=80, r=20, t=20, b=80),
            xaxis_title="Next Condition",
            yaxis_title="Current Condition"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Average Duration of Each Market Condition")

        durations = []
        for regime_id in [0, 1, 2]:
            persist = trans_probs[regime_id, regime_id]
            duration = 1 / (1 - persist/100) if persist < 100 else np.inf
            durations.append({
                'Market Type': regime_names[regime_id],
                'Stability': f"{persist:.1f}%",
                'Avg Duration (Days)': f"{duration:.1f}" if duration != np.inf else "∞"
            })

        df_duration = pd.DataFrame(durations)
        st.dataframe(df_duration, use_container_width=True, hide_index=True)

        st.markdown("**Current Market:**")
        persist_prob = trans_probs[current_regime, current_regime]
        exp_duration = 1 / (1 - persist_prob/100) if persist_prob < 100 else np.inf

        st.metric("Chance of Staying", f"{persist_prob:.1f}%")
        if exp_duration != np.inf:
            st.metric("Expected Duration", f"~{exp_duration:.0f} days")

st.divider()

# === RISK-RETURN PROFILE ===
if history is not None and 'GSPC' in market:
    st.subheader("Investment Returns in Different Market Conditions")

    sp500 = market['GSPC'].copy()
    sp500_col = [c for c in sp500.columns if c != 'ds'][0]
    sp500['return'] = sp500[sp500_col].pct_change()

    merged = pd.merge(history[['ds', 'regime']], sp500, on='ds', how='inner')

    metrics = []
    for regime_id in [0, 1, 2]:
        regime_data = merged[merged['regime'] == regime_id]
        if len(regime_data) > 0:
            returns = regime_data['return'].dropna()
            ann_return = returns.mean() * 252 * 100
            ann_vol = returns.std() * np.sqrt(252) * 100
            sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

            metrics.append({
                'Market Type': regime_names[regime_id],
                'Return': ann_return,
                'Risk': ann_vol,
                'Score': sharpe,
                'Days': len(regime_data)
            })

    metrics_df = pd.DataFrame(metrics)

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = go.Figure()

        for idx, row in metrics_df.iterrows():
            regime_id = [k for k, v in regime_names.items() if v == row['Market Type']][0]
            is_current = regime_id == current_regime

            fig.add_trace(go.Scatter(
                x=[row['Risk']],
                y=[row['Return']],
                mode='markers+text',
                marker=dict(
                    size=25 if is_current else 20,
                    color=regime_colors[regime_id],
                    opacity=1.0 if is_current else 0.6,
                    line=dict(width=3, color='black') if is_current else dict(width=0)
                ),
                text=[row['Market Type']],
                textposition="top center",
                name=row['Market Type'],
                hovertemplate=f"<b>{row['Market Type']}</b><br>" +
                             f"Return: {row['Return']:.1f}%<br>" +
                             f"Risk: {row['Risk']:.1f}%<br>" +
                             f"Score: {row['Score']:.2f}<extra></extra>"
            ))

        fig.update_layout(
            xaxis_title="Risk Level (%)",
            yaxis_title="Annual Return (%)",
            height=400,
            showlegend=False,
            hovermode='closest'
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.3)

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Summary Table**")

        display_df = metrics_df[['Market Type', 'Return', 'Risk', 'Score']].copy()
        display_df['Return'] = display_df['Return'].map('{:.1f}%'.format)
        display_df['Risk'] = display_df['Risk'].map('{:.1f}%'.format)
        display_df['Score'] = display_df['Score'].map('{:.2f}'.format)

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Current regime emphasis
        current_metrics = metrics_df[metrics_df['Market Type'] == regime_names[current_regime]].iloc[0]
        st.markdown(f"**Current Market ({regime_names[current_regime]}):**")
        st.metric("Quality Score", f"{current_metrics['Score']:.2f}")
        st.metric("Return-to-Risk", f"{current_metrics['Return']/current_metrics['Risk']:.2f}")

st.divider()

# === DRAWDOWN ANALYSIS ===
if 'GSPC' in market:
    st.subheader("Market Performance History")

    sp500 = market['GSPC'].copy()
    sp500_col = [c for c in sp500.columns if c != 'ds'][0]
    sp500['return'] = sp500[sp500_col].pct_change()
    sp500['cum'] = (1 + sp500['return']).cumprod()
    sp500['max'] = sp500['cum'].expanding().max()
    sp500['dd'] = (sp500['cum'] - sp500['max']) / sp500['max'] * 100

    if history is not None:
        sp500_regime = pd.merge(sp500, history[['ds', 'regime']], on='ds', how='left')
    else:
        sp500_regime = sp500.copy()

    recent = sp500_regime.tail(750)  # ~3 years
    # Add day index for x-axis
    recent = recent.reset_index(drop=True)
    recent['day_index'] = range(len(recent))

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.08,
        subplot_titles=("Growth Over Time (3-Year History)", "Losses by Market Condition")
    )

    # Cumulative return
    fig.add_trace(
        go.Scatter(
            x=recent['day_index'],
            y=recent['cum'] * 100,
            line=dict(color='#2c3e50', width=2),
            fill='tozeroy',
            fillcolor='rgba(52, 152, 219, 0.1)',
            name='Return',
            hovertemplate='Return: %{y:.1f}%<extra></extra>'
        ),
        row=1, col=1
    )

    # Drawdown by regime
    if 'regime' in recent.columns:
        for regime_id in [0, 1, 2]:
            regime_data = recent[recent['regime'] == regime_id]
            if len(regime_data) > 0:
                fig.add_trace(
                    go.Scatter(
                        x=regime_data['day_index'],
                        y=regime_data['dd'],
                        mode='markers',
                        marker=dict(size=3, color=regime_colors[regime_id]),
                        name=regime_names[regime_id],
                        hovertemplate='Loss: %{y:.2f}%<extra></extra>'
                    ),
                    row=2, col=1
                )

    fig.update_xaxes(title_text="", row=1, col=1)
    fig.update_xaxes(title_text="", row=2, col=1)
    fig.update_yaxes(title_text="Growth (%)", row=1, col=1)
    fig.update_yaxes(title_text="Loss (%)", row=2, col=1)
    fig.update_layout(height=550, margin=dict(l=20, r=20, t=40, b=20), showlegend=False)

    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Current Loss from Peak", f"{recent.iloc[-1]['dd']:.2f}%")

    with col2:
        st.metric("Worst Historical Loss", f"{sp500['dd'].min():.2f}%")

    with col3:
        # Max DD by current regime
        if 'regime' in merged.columns:
            regime_dd = merged[merged['regime'] == current_regime]['return'].dropna()
            regime_cum = (1 + regime_dd).cumprod()
            regime_max = regime_cum.expanding().max()
            regime_dd_pct = ((regime_cum - regime_max) / regime_max * 100).min()
            st.metric(f"Worst Loss in {regime_names[current_regime]}", f"{regime_dd_pct:.2f}%")

    with col4:
        days_from_peak = len(recent) - recent['cum'].idxmax()
        st.metric("Days from Peak", days_from_peak)

st.divider()

# === VOLATILITY REGIMES ===
if 'VIX' in market and history is not None:
    st.subheader("Market Fear Indicator")

    vix = market['VIX'].copy()
    vix_col = [c for c in vix.columns if c != 'ds'][0]

    vix_regime = pd.merge(history[['ds', 'regime']], vix, on='ds', how='inner')

    col1, col2 = st.columns([2, 1])

    with col1:
        # VIX distribution by regime
        fig = go.Figure()

        for regime_id in [0, 1, 2]:
            regime_data = vix_regime[vix_regime['regime'] == regime_id]
            if len(regime_data) > 0:
                fig.add_trace(go.Violin(
                    y=regime_data[vix_col],
                    name=regime_names[regime_id],
                    box_visible=True,
                    meanline_visible=True,
                    fillcolor=regime_colors[regime_id],
                    opacity=0.6,
                    line_color=regime_colors[regime_id]
                ))

        fig.update_layout(
            yaxis_title="VIX Level",
            height=350,
            showlegend=True,
            margin=dict(l=20, r=20, t=20, b=20)
        )

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Fear Levels by Market Type**")

        vix_stats = []
        for regime_id in [0, 1, 2]:
            regime_data = vix_regime[vix_regime['regime'] == regime_id]
            if len(regime_data) > 0:
                vix_stats.append({
                    'Market Type': regime_names[regime_id],
                    'Average': f"{regime_data[vix_col].mean():.1f}",
                    'Typical': f"{regime_data[vix_col].median():.1f}",
                    'Variability': f"{regime_data[vix_col].std():.1f}"
                })

        st.dataframe(pd.DataFrame(vix_stats), use_container_width=True, hide_index=True)

        # Current VIX
        current_vix = vix.iloc[-1][vix_col]
        st.metric("Current Fear Index", f"{current_vix:.2f}")

        # VIX percentile in current regime
        current_regime_vix = vix_regime[vix_regime['regime'] == current_regime][vix_col]
        if len(current_regime_vix) > 0:
            percentile = (current_regime_vix < current_vix).sum() / len(current_regime_vix) * 100
            st.metric("Compared to Similar Markets", f"{percentile:.0f}%")

st.divider()

# === CORRELATION MATRIX ===
if len(market) >= 3:
    st.subheader("Asset Relationships (Current Market)")

    key_assets = ['GSPC', 'VIX', 'DXY', 'DGS10', 'GOLD']
    available = [k for k in key_assets if k in market]

    if len(available) >= 2 and history is not None:
        regime_history = history[history['regime'] == current_regime]

        corr_data = {}
        for asset in available:
            asset_df = market[asset]
            col_name = [c for c in asset_df.columns if c != 'ds'][0]
            merged = pd.merge(regime_history[['ds']], asset_df, on='ds', how='inner')
            if len(merged) > 0:
                corr_data[asset] = merged[col_name].pct_change()

        if len(corr_data) > 1:
            corr_df = pd.DataFrame(corr_data).corr()

            fig = go.Figure(data=go.Heatmap(
                z=corr_df.values,
                x=corr_df.columns,
                y=corr_df.columns,
                colorscale='RdBu',
                zmid=0,
                zmin=-1,
                zmax=1,
                text=np.round(corr_df.values, 2),
                texttemplate='%{text}',
                textfont={"size": 11},
                hovertemplate='%{x} vs %{y}: %{z:.2f}<extra></extra>'
            ))

            fig.update_layout(
                height=400,
                margin=dict(l=80, r=20, t=20, b=80)
            )

            st.plotly_chart(fig, use_container_width=True)

st.divider()

# === ALLOCATION GUIDANCE ===
st.subheader("What This Means for Your Investments")

if history is not None and 'GSPC' in market:
    current_metrics = metrics_df[metrics_df['Market Type'] == regime_names[current_regime]].iloc[0]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Investment Level**")
        sharpe = current_metrics['Score']
        if sharpe > 1.0:
            sizing = "Invest More"
            color = "🟢"
        elif sharpe > 0.5:
            sizing = "Stay Balanced"
            color = "🟡"
        else:
            sizing = "Invest Less"
            color = "🔴"

        st.markdown(f"{color} **{sizing}** (Quality: {sharpe:.2f})")
        st.caption(f"Based on past {regime_names[current_regime]} conditions")

    with col2:
        st.markdown("**How Long to Hold**")
        if exp_duration != np.inf:
            st.markdown(f"**~{exp_duration:.0f} days**")
            st.caption(f"{persist_prob:.1f}% chance market stays same")
        else:
            st.markdown("**Long Time**")
            st.caption("Very stable conditions")

    with col3:
        st.markdown("**Watch For Changes**")
        next_likely_regime = np.argmax(trans_probs[current_regime, :])
        if next_likely_regime != current_regime:
            next_prob = trans_probs[current_regime, next_likely_regime]
            st.markdown(f"**{regime_names[next_likely_regime]}**")
            st.caption(f"Watch for: {next_prob:.1f}% chance")
        else:
            st.markdown("**Stay Put**")
            st.caption("No changes expected soon")
