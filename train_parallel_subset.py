#!/usr/bin/env python3
"""
Train a subset of forecasting features.
Usage: python train_parallel_subset.py --group [A|B|C]
"""
import argparse
import yaml
import shutil
from pathlib import Path
from forecasting_agent import forecaster


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--group', required=True, choices=['A', 'B', 'C'],
                        help='Which group to train (A=1-7, B=8-14, C=15-22)')
    args = parser.parse_args()

    # Load config
    with open('configs/features_config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Determine features based on group
    if args.group == 'A':
        # Features 1-7: First 7 daily features
        features_to_train = config['daily']['features'][:7]
        print(f"Group A: Training features 1-7")
    elif args.group == 'B':
        # Features 8-14: Next 7 daily features
        features_to_train = config['daily']['features'][7:14]
        print(f"Group B: Training features 8-14")
    else:  # C
        # Features 15-22: Remaining daily + weekly + monthly
        features_to_train = (
            config['daily']['features'][14:] +
            config['weekly']['features'] +
            config['monthly']['features']
        )
        print(f"Group C: Training features 15-22")

    print(f"Features to train ({len(features_to_train)}): {', '.join(features_to_train)}")

    # Train (lightning_logs cleanup now happens per-feature inside forecaster)
    forecaster.run_forecasting_agent(
        mode='all',
        config_path='configs/features_config.yaml',
        use_bigquery=True,
        force_retrain=True,
        selective_features=features_to_train
    )

    print(f"\n✅ Group {args.group} training completed!")


if __name__ == '__main__':
    main()
