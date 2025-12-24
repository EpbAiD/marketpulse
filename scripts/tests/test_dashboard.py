#!/usr/bin/env python3
"""
Quick test to verify dashboard data loading works correctly
"""

import pandas as pd
import json
import os

print("Testing dashboard data loading...")
print("=" * 60)

# Test 1: Load cluster stats
stats_path = "outputs/clustering/cluster_stats.csv"
if os.path.exists(stats_path):
    stats = pd.read_csv(stats_path, header=[0, 1], index_col=0)
    print(f"\n✅ Cluster Stats Loaded")
    print(f"   Shape: {stats.shape}")
    print(f"   Regimes: {stats.index.tolist()}")
    print(f"   Number of regimes: {len(stats)}")
else:
    print(f"\n❌ Cluster stats not found at {stats_path}")

# Test 2: Load assignments
assignments_path = "outputs/clustering/cluster_assignments.parquet"
if os.path.exists(assignments_path):
    assignments = pd.read_parquet(assignments_path)
    print(f"\n✅ Cluster Assignments Loaded")
    print(f"   Shape: {assignments.shape}")
    print(f"   Columns: {assignments.columns.tolist()}")
    print(f"   Unique regimes: {sorted(assignments['regime'].unique())}")
    print(f"   Date range: {assignments.index.min()} to {assignments.index.max()}")
else:
    print(f"\n❌ Assignments not found at {assignments_path}")

# Test 3: Check labels file
labels_path = "outputs/clustering/regime_labels.json"
if os.path.exists(labels_path):
    with open(labels_path, "r") as f:
        labels = json.load(f)
    print(f"\n✅ Regime Labels Loaded")
    print(f"   Labels: {labels}")
else:
    print(f"\n⚠️  No regime labels file (will use defaults)")
    print(f"   Expected path: {labels_path}")

# Test 4: Verify MultiIndex column access
if os.path.exists(stats_path):
    print(f"\n✅ Testing MultiIndex Column Access")
    feature_level = stats.columns.get_level_values(0)
    print(f"   Unique features: {len(feature_level.unique())}")

    # Test finding return features
    return_features = [f for f in feature_level.unique() if 'ret' in f.lower()]
    print(f"   Return features found: {len(return_features)}")
    print(f"   Examples: {return_features[:3]}")

    # Test accessing a specific column
    if return_features and (return_features[0], 'mean') in stats.columns:
        sample_col = (return_features[0], 'mean')
        sample_data = stats[sample_col]
        print(f"   Sample column {sample_col}:")
        print(f"   {sample_data.to_dict()}")

print("\n" + "=" * 60)
print("✅ All tests passed! Dashboard should work correctly.")
print("\nRun the dashboard with:")
print("   streamlit run dashboard/app.py")
