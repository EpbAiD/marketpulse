#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_explorer.py
Financial Data EDA and Visualization
=============================================================
Interactive exploration of fetched financial data:
- Time series plots
- Correlation heatmaps
- Distribution analysis
- Missing data visualization
- Feature statistics
=============================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import glob


def render():
    st.markdown("## 📊 Financial Data Explorer (EDA)")
    st.markdown("Interactive exploration and visualization of fetched and engineered financial data")
    st.markdown("---")

    # Data source selection
    data_source = st.selectbox(
        "Select Data Source",
        ["Raw Fetched Data", "Cleaned Data", "Engineered Features", "Selected Features"],
        index=1,
    )

    # Load data based on selection
    data_dir_map = {
        "Raw Fetched Data": "outputs/fetched/raw",
        "Cleaned Data": "outputs/fetched/cleaned",
        "Engineered Features": "outputs/engineered",
        "Selected Features": "outputs/selected",
    }

    data_dir = data_dir_map[data_source]

    if not os.path.exists(data_dir):
        st.error(f"❌ Data directory not found: {data_dir}")
        st.info("Run the pipeline first to generate data.")
        return

    # Get available features
    if data_source == "Selected Features":
        parquet_files = glob.glob(os.path.join(data_dir, "aligned_dataset.parquet"))
        if not parquet_files:
            st.warning("No selected features found. Run feature selection first.")
            return
        df = pd.read_parquet(parquet_files[0])
        available_features = list(df.columns)
    else:
        parquet_files = glob.glob(os.path.join(data_dir, "*.parquet"))
        if not parquet_files:
            st.warning(f"No data found in {data_dir}")
            return
        available_features = [os.path.basename(f).replace(".parquet", "") for f in parquet_files]

    st.success(f"✅ Found {len(available_features)} features in {data_source}")

    # ==================================================================
    # SECTION 1: Overview Statistics
    # ==================================================================
    st.markdown("### 📈 Dataset Overview")

    col1, col2, col3, col4 = st.columns(4)

    if data_source == "Selected Features":
        with col1:
            st.metric("Total Features", len(df.columns))
        with col2:
            st.metric("Total Observations", len(df))
        with col3:
            date_range = (df.index.min(), df.index.max())
            st.metric("Date Range", f"{date_range[0].date()} to {date_range[1].date()}")
        with col4:
            missing_pct = (df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
            st.metric("Missing Data %", f"{missing_pct:.2f}%")
    else:
        with col1:
            st.metric("Available Features", len(available_features))

    # ==================================================================
    # SECTION 2: Feature Selection & Visualization
    # ==================================================================
    st.markdown("---")
    st.markdown("### 📊 Time Series Visualization")

    # Multi-select features
    selected_features = st.multiselect(
        "Select features to plot",
        available_features,
        default=available_features[:min(3, len(available_features))],
        max_selections=10,
    )

    if not selected_features:
        st.warning("Please select at least one feature to visualize.")
        return

    # Load selected features data
    plot_data = {}
    if data_source == "Selected Features":
        for feat in selected_features:
            plot_data[feat] = df[feat]
    else:
        for feat in selected_features:
            feat_path = os.path.join(data_dir, f"{feat}.parquet")
            if os.path.exists(feat_path):
                temp_df = pd.read_parquet(feat_path)
                # Get first column if multiple
                plot_data[feat] = temp_df.iloc[:, 0]

    # Combine into DataFrame
    plot_df = pd.DataFrame(plot_data)

    # Plot type selection
    plot_type = st.radio(
        "Plot Type",
        ["Line Chart", "Normalized (100-index)", "Distribution", "Rolling Statistics"],
        horizontal=True,
    )

    if plot_type == "Line Chart":
        fig = go.Figure()
        for feat in selected_features:
            if feat in plot_df.columns:
                fig.add_trace(go.Scatter(
                    x=plot_df.index,
                    y=plot_df[feat],
                    name=feat,
                    mode='lines',
                ))
        fig.update_layout(
            title="Time Series - Selected Features",
            xaxis_title="Date",
            yaxis_title="Value",
            hovermode='x unified',
            height=600,
        )
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type == "Normalized (100-index)":
        # Normalize to 100 at start date
        normalized_df = (plot_df / plot_df.iloc[0]) * 100

        fig = go.Figure()
        for feat in selected_features:
            if feat in normalized_df.columns:
                fig.add_trace(go.Scatter(
                    x=normalized_df.index,
                    y=normalized_df[feat],
                    name=feat,
                    mode='lines',
                ))
        fig.update_layout(
            title="Normalized Time Series (Base 100)",
            xaxis_title="Date",
            yaxis_title="Index (100 = start)",
            hovermode='x unified',
            height=600,
        )
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type == "Distribution":
        # Histogram + KDE for each feature
        fig = make_subplots(
            rows=len(selected_features),
            cols=1,
            subplot_titles=selected_features,
            vertical_spacing=0.05,
        )

        for idx, feat in enumerate(selected_features, 1):
            if feat in plot_df.columns:
                fig.add_trace(
                    go.Histogram(x=plot_df[feat].dropna(), name=feat, nbinsx=50),
                    row=idx,
                    col=1,
                )

        fig.update_layout(
            title="Feature Distributions",
            height=300 * len(selected_features),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type == "Rolling Statistics":
        window = st.slider("Rolling Window (days)", 10, 252, 60)

        fig = make_subplots(
            rows=len(selected_features),
            cols=1,
            subplot_titles=[f"{f} - {window}d Rolling Mean & Std" for f in selected_features],
            vertical_spacing=0.05,
        )

        for idx, feat in enumerate(selected_features, 1):
            if feat in plot_df.columns:
                series = plot_df[feat].dropna()
                rolling_mean = series.rolling(window).mean()
                rolling_std = series.rolling(window).std()

                fig.add_trace(
                    go.Scatter(x=series.index, y=series, name=f"{feat} (actual)", opacity=0.3),
                    row=idx,
                    col=1,
                )
                fig.add_trace(
                    go.Scatter(x=rolling_mean.index, y=rolling_mean, name=f"{feat} (mean)"),
                    row=idx,
                    col=1,
                )

        fig.update_layout(
            title=f"Rolling Statistics ({window} days)",
            height=300 * len(selected_features),
            showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ==================================================================
    # SECTION 3: Correlation Analysis
    # ==================================================================
    if data_source == "Selected Features" or len(selected_features) > 1:
        st.markdown("---")
        st.markdown("### 🔗 Correlation Analysis")

        if len(selected_features) >= 2:
            corr_df = plot_df[selected_features].corr()

            fig = px.imshow(
                corr_df,
                text_auto=".2f",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                title="Correlation Heatmap",
            )
            fig.update_layout(height=600)
            st.plotly_chart(fig, use_container_width=True)

            # Highlight strong correlations
            st.markdown("#### Strong Correlations (|r| > 0.7)")
            strong_corr = []
            for i in range(len(corr_df.columns)):
                for j in range(i + 1, len(corr_df.columns)):
                    corr_val = corr_df.iloc[i, j]
                    if abs(corr_val) > 0.7:
                        strong_corr.append({
                            "Feature 1": corr_df.columns[i],
                            "Feature 2": corr_df.columns[j],
                            "Correlation": f"{corr_val:.3f}",
                        })

            if strong_corr:
                st.dataframe(pd.DataFrame(strong_corr), use_container_width=True)
            else:
                st.info("No strong correlations (|r| > 0.7) found among selected features.")

    # ==================================================================
    # SECTION 4: Summary Statistics
    # ==================================================================
    st.markdown("---")
    st.markdown("### 📋 Summary Statistics")

    if st.checkbox("Show detailed statistics"):
        stats_df = plot_df[selected_features].describe().T
        stats_df["missing_%"] = (plot_df[selected_features].isnull().sum() / len(plot_df) * 100).values
        st.dataframe(stats_df.style.format("{:.4f}"), use_container_width=True)

        # Download option
        csv = stats_df.to_csv()
        st.download_button(
            label="📥 Download Statistics as CSV",
            data=csv,
            file_name="feature_statistics.csv",
            mime="text/csv",
        )

    # ==================================================================
    # SECTION 5: Missing Data Visualization
    # ==================================================================
    if data_source in ["Raw Fetched Data", "Cleaned Data"]:
        st.markdown("---")
        st.markdown("### 🔍 Missing Data Analysis")

        if st.checkbox("Show missing data heatmap"):
            missing_df = plot_df[selected_features].isnull().astype(int)

            fig = px.imshow(
                missing_df.T,
                labels=dict(x="Date", y="Feature", color="Missing"),
                title="Missing Data Heatmap (White = Missing)",
                color_continuous_scale=["white", "red"],
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

            # Missing data summary
            missing_summary = pd.DataFrame({
                "Feature": selected_features,
                "Missing Count": plot_df[selected_features].isnull().sum().values,
                "Missing %": (plot_df[selected_features].isnull().sum() / len(plot_df) * 100).values,
            }).sort_values("Missing %", ascending=False)

            st.dataframe(missing_summary, use_container_width=True)
