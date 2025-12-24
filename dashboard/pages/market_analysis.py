"""
Market Environment Analysis
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, timedelta
import glob

BASE_DIR = Path(__file__).parent.parent.parent


def get_latest_file(pattern):
    files = glob.glob(str(BASE_DIR / pattern))
    return Path(max(files, key=lambda f: Path(f).stat().st_mtime)) if files else None


def load_data():
    data = {}

    # Forecast
    forecast_file = get_latest_file("outputs/inference/regime_forecast_*.csv")
    if forecast_file:
        df = pd.read_csv(forecast_file)
        df['ds'] = pd.to_datetime(df['ds'] if 'ds' in df.columns else df['date'])
        data['forecast'] = df

    # Historical regimes
    cluster_file = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
    if cluster_file.exists():
        df = pd.read_parquet(cluster_file)
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df.rename(columns={df.columns[0]: 'ds'}, inplace=True)
        df['ds'] = pd.to_datetime(df['ds'] if 'ds' in df.columns else df.index)
        data['history'] = df

    # Market data
    market_files = list((BASE_DIR / "outputs" / "fetched" / "cleaned").glob("*.parquet"))
    if market_files:
        market_data = {}
        for f in market_files:
            name = f.stem
            df = pd.read_parquet(f)
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                if df.columns[0] != 'ds':
                    df.rename(columns={df.columns[0]: 'ds'}, inplace=True)
            elif 'ds' not in df.columns:
                # Assume first column is date
                df.rename(columns={df.columns[0]: 'ds'}, inplace=True)
            df['ds'] = pd.to_datetime(df['ds'])
            market_data[name] = df
        data['market'] = market_data

    return data


def render():
    data = load_data()

    if not data:
        st.warning("No data available")
        return

    st.title("Market Environment")
    st.caption(datetime.now().strftime('%B %d, %Y'))

    # Current state - just show what the data says
    if 'forecast' in data and 'history' in data and 'market' in data:

        # Get current regime classification
        forecast = data['forecast']
        current_regime = forecast.iloc[0]['regime'] if len(forecast) > 0 else None

        if current_regime is not None:
            regime_names = {0: "Consolidation", 1: "Expansion", 2: "Compression"}

            st.header(regime_names[current_regime])

            # Show market conditions, not model metrics
            if 'VIX' in data['market']:
                vix_latest = data['market']['VIX'].iloc[-1]['VIX']
                st.metric("VIX", f"{vix_latest:.1f}")

            st.divider()

            # Historical behavior in this regime
            st.subheader("Historical Characteristics")

            history = data['history']
            regime_history = history[history['regime'] == current_regime]

            if 'GSPC' in data['market']:
                sp500 = data['market']['GSPC'].copy()
                sp500['return'] = sp500['GSPC'].pct_change()

                # Merge
                merged = pd.merge(regime_history, sp500, on='ds', how='inner')

                if len(merged) > 0:
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        avg_return = merged['return'].mean() * 252 * 100  # Annualized
                        st.metric("Avg Annual Return", f"{avg_return:.1f}%")

                    with col2:
                        volatility = merged['return'].std() * np.sqrt(252) * 100
                        st.metric("Volatility", f"{volatility:.1f}%")

                    with col3:
                        st.metric("Sample Size", f"{len(merged)} days")

            st.divider()

            # Returns distribution
            st.subheader("Return Distribution")

            if 'GSPC' in data['market']:
                sp500 = data['market']['GSPC'].copy()
                sp500['return'] = sp500['GSPC'].pct_change() * 100

                # All regimes
                all_merged = pd.merge(history, sp500, on='ds', how='inner')

                fig = go.Figure()

                colors = ['#95a5a6', '#3498db', '#e74c3c']

                for regime in [0, 1, 2]:
                    regime_data = all_merged[all_merged['regime'] == regime]
                    if len(regime_data) > 0:
                        fig.add_trace(go.Violin(
                            y=regime_data['return'],
                            name=regime_names[regime],
                            box_visible=True,
                            meanline_visible=True,
                            fillcolor=colors[regime],
                            opacity=0.6
                        ))

                fig.update_layout(
                    yaxis_title="Daily Return (%)",
                    showlegend=True,
                    height=400,
                    margin=dict(l=20, r=20, t=20, b=20)
                )

                st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # Market structure
            st.subheader("Market Structure")

            # Show transitions
            regimes = history['regime'].values
            current = regimes[:-1]
            next_regime = regimes[1:]

            transitions = np.zeros((3, 3))
            for curr, nxt in zip(current, next_regime):
                transitions[int(curr), int(nxt)] += 1

            row_sums = transitions.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1
            probs = transitions / row_sums

            # Show as simple table
            trans_df = pd.DataFrame(
                probs * 100,
                columns=['→ Consolidation', '→ Expansion', '→ Compression'],
                index=['Consolidation', 'Expansion', 'Compression']
            )

            st.dataframe(trans_df.round(1), use_container_width=True)

            st.divider()

            # Drawdown context
            st.subheader("Drawdown Context")

            if 'GSPC' in data['market']:
                sp500 = data['market']['GSPC'].copy()
                sp500['return'] = sp500['GSPC'].pct_change()
                sp500['cum'] = (1 + sp500['return']).cumprod()
                sp500['max'] = sp500['cum'].expanding().max()
                sp500['dd'] = (sp500['cum'] - sp500['max']) / sp500['max'] * 100

                # Recent period
                recent = sp500.tail(500)

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=recent['ds'],
                    y=recent['dd'],
                    fill='tozeroy',
                    line=dict(color='#e74c3c', width=1),
                    fillcolor='rgba(231, 76, 60, 0.1)'
                ))

                fig.update_layout(
                    yaxis_title="Drawdown (%)",
                    height=300,
                    margin=dict(l=20, r=20, t=20, b=20),
                    showlegend=False
                )

                st.plotly_chart(fig, use_container_width=True)

                # Current drawdown
                current_dd = sp500.iloc[-1]['dd']
                max_dd = sp500['dd'].min()

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Current Drawdown", f"{current_dd:.1f}%")
                with col2:
                    st.metric("Max Drawdown (All-Time)", f"{max_dd:.1f}%")

            st.divider()

            # Historical regime timeline - just show the pattern
            st.subheader("Regime History")

            recent_history = history.tail(252)  # Last year

            colors = {0: '#95a5a6', 1: '#3498db', 2: '#e74c3c'}
            color_seq = [colors[r] for r in recent_history['regime']]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=recent_history['ds'],
                y=recent_history['regime'],
                mode='markers',
                marker=dict(
                    color=color_seq,
                    size=8,
                    symbol='square'
                ),
                hovertemplate='%{x}<br>Regime: %{y}'
            ))

            fig.update_layout(
                height=200,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(
                    tickmode='array',
                    tickvals=[0, 1, 2],
                    ticktext=['Consolidation', 'Expansion', 'Compression']
                ),
                showlegend=False
            )

            st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # Cross-asset correlations in this regime
            st.subheader("Cross-Asset Relationships")

            if len(data['market']) >= 2:
                # Get available assets
                assets = list(data['market'].keys())[:5]  # First 5

                # Calculate correlations in current regime
                regime_data = {}
                for asset in assets:
                    asset_df = data['market'][asset]
                    merged = pd.merge(regime_history, asset_df, on='ds', how='inner')
                    if len(merged) > 0 and asset in merged.columns:
                        regime_data[asset] = merged[asset].pct_change()

                if len(regime_data) > 1:
                    corr_df = pd.DataFrame(regime_data).corr()

                    fig = go.Figure(data=go.Heatmap(
                        z=corr_df.values,
                        x=corr_df.columns,
                        y=corr_df.columns,
                        colorscale='RdBu',
                        zmid=0,
                        text=np.round(corr_df.values, 2),
                        texttemplate='%{text}',
                        textfont={"size": 10}
                    ))

                    fig.update_layout(
                        height=400,
                        margin=dict(l=20, r=20, t=20, b=20)
                    )

                    st.plotly_chart(fig, use_container_width=True)
