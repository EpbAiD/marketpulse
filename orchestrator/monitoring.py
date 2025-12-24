#!/usr/bin/env python3
"""
Monitoring and Autonomous Improvement Module

Monitors forecast performance and triggers retraining when needed.
Handles alerts, validation, and autonomous model improvement.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import Dict, Optional
import subprocess

# Import from data_agent
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from data_agent.storage import get_storage
from data_agent import validator


class PerformanceMonitor:
    """Monitors forecast performance using SMAPE-based validation"""

    def __init__(self, outputs_dir="outputs"):
        self.outputs_dir = Path(outputs_dir)
        self.metrics_log = self.outputs_dir / "model_performance_log.jsonl"
        self.storage = get_storage()

    def get_current_metrics(self) -> Optional[Dict]:
        """
        Get current validation metrics using SMAPE-based validation

        Returns:
            Dict with performance metrics
        """
        try:
            # Run validation analysis
            result = validator.run_validation_analysis(self.storage)

            if result['metrics']['total_forecasts'] == 0:
                return None

            # Build metrics structure
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'validation_type': 'smape_based_feature_validation',
                'avg_smape': result['metrics']['avg_smape'],
                'needs_retraining': result['metrics']['needs_retraining'],
                'total_forecasts': result['metrics']['total_forecasts'],
                'forecasts_need_retraining': result['metrics'].get('forecasts_need_retraining', 0),
                'sample_size': result['metrics']['total_forecasts']
            }

            return metrics

        except Exception as e:
            print(f"⚠️ Validation failed: {e}")
            return None

    def log_metrics(self, metrics: Dict) -> None:
        """Append metrics to log file"""
        self.metrics_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_log, 'a') as f:
            f.write(json.dumps(metrics) + '\n')

    def get_historical_metrics(self, lookback_days: int = 90) -> list:
        """Load historical performance metrics"""
        if not self.metrics_log.exists():
            return []

        cutoff = datetime.now() - timedelta(days=lookback_days)

        metrics = []
        with open(self.metrics_log, 'r') as f:
            for line in f:
                m = json.loads(line)
                if datetime.fromisoformat(m['timestamp']) > cutoff:
                    metrics.append(m)

        return metrics


class RetrainingAgent:
    """Autonomous retraining based on SMAPE-based performance degradation"""

    def __init__(self,
                 smape_threshold: float = 30.0,
                 critical_feature_threshold: float = 0.3,
                 min_sample_size: int = 3):
        """
        Args:
            smape_threshold: Trigger retraining if avg SMAPE exceeds this
            critical_feature_threshold: Retrain if >30% features exceed thresholds
            min_sample_size: Minimum forecasts needed to evaluate
        """
        self.monitor = PerformanceMonitor()
        self.smape_threshold = smape_threshold
        self.critical_feature_threshold = critical_feature_threshold
        self.min_sample_size = min_sample_size
        self.retrain_log = Path("outputs/retrain_log.jsonl")

    def should_retrain(self, current_metrics: Dict, historical_metrics: list) -> tuple:
        """
        Determine if retraining is needed based on SMAPE performance

        Returns:
            (should_retrain: bool, reason: str)
        """
        if current_metrics is None:
            return False, "No metrics available"

        if current_metrics['sample_size'] < self.min_sample_size:
            return False, f"Insufficient samples ({current_metrics['sample_size']} < {self.min_sample_size})"

        # Trigger 1: Direct signal from validator
        if current_metrics.get('needs_retraining', False):
            critical_pct = current_metrics.get('forecasts_need_retraining', 0) / current_metrics['total_forecasts'] * 100
            return True, f"Feature validator signals retraining ({critical_pct:.0f}% forecasts have critical errors)"

        # Trigger 2: Average SMAPE exceeds threshold
        avg_smape = current_metrics.get('avg_smape', 0)
        if avg_smape > self.smape_threshold:
            return True, f"Average SMAPE {avg_smape:.1f}% exceeds threshold {self.smape_threshold:.1f}%"

        # Trigger 3: SMAPE degraded from baseline
        if historical_metrics:
            baseline_smape = np.mean([m.get('avg_smape', 0) for m in historical_metrics[:10] if 'avg_smape' in m])
            if baseline_smape > 0:
                smape_increase = avg_smape - baseline_smape
                if smape_increase > 10.0:
                    return True, f"SMAPE degraded by {smape_increase:.1f}pp from baseline ({baseline_smape:.1f}% → {avg_smape:.1f}%)"

        return False, f"Performance acceptable: avg SMAPE {avg_smape:.1f}%"

    def trigger_retraining(self) -> Dict:
        """Trigger model retraining"""
        print("\n🔄 Triggering autonomous model retraining...")

        try:
            # Run training pipeline
            result = subprocess.run(
                ["python", "-m", "train_all_models"],
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour max
            )

            if result.returncode == 0:
                return {
                    'status': 'success',
                    'timestamp': datetime.now().isoformat(),
                    'output': result.stdout[-1000:]
                }
            else:
                return {
                    'status': 'failed',
                    'timestamp': datetime.now().isoformat(),
                    'error': result.stderr[-1000:]
                }

        except Exception as e:
            return {
                'status': 'failed',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }

    def run_check(self) -> Dict:
        """
        Run complete performance check and trigger retraining if needed

        Returns:
            Dict with check results
        """
        print("\n" + "=" * 80)
        print("AUTONOMOUS IMPROVEMENT AGENT")
        print("=" * 80)

        # Get current metrics
        print("\n[1/3] Evaluating current performance...")
        current_metrics = self.monitor.get_current_metrics()

        if current_metrics is None:
            print("   ℹ️  No validation data available yet")
            return {
                'action': 'no_action',
                'reason': 'no_metrics',
                'timestamp': datetime.now().isoformat()
            }

        print(f"   Average SMAPE: {current_metrics['avg_smape']:.2f}%")
        print(f"   Forecasts validated: {current_metrics['total_forecasts']}")

        # Log metrics
        self.monitor.log_metrics(current_metrics)

        # Get historical metrics
        print("\n[2/3] Checking against historical baseline...")
        historical_metrics = self.monitor.get_historical_metrics()
        print(f"   Historical metrics: {len(historical_metrics)} records")

        # Decide if retraining needed
        print("\n[3/3] Evaluating retraining decision...")
        should_retrain, reason = self.should_retrain(current_metrics, historical_metrics)

        result = {
            'current_metrics': {k: float(v) if isinstance(v, (float, int)) else v for k, v in current_metrics.items()},
            'should_retrain': bool(should_retrain),
            'reason': str(reason),
            'timestamp': str(datetime.now().isoformat())
        }

        if should_retrain:
            print(f"\n⚠️  RETRAIN RECOMMENDED: {reason}")
            print("\n   To trigger retraining, run: python train_all_models.py")

            # Log retraining recommendation
            self.retrain_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self.retrain_log, 'a') as f:
                f.write(json.dumps(result) + '\n')

            result['action'] = 'retrain_recommended'
        else:
            print(f"\n✅ NO RETRAINING NEEDED: {reason}")
            result['action'] = 'no_action'

        print("\n" + "=" * 80 + "\n")
        return result


if __name__ == "__main__":
    # Run monitoring check when called directly
    agent = RetrainingAgent()
    result = agent.run_check()

    # Print summary
    if result['action'] == 'retrain_recommended':
        print(f"⚠️  Retraining recommended: {result['reason']}")
    else:
        print(f"✅ System performing well: {result['reason']}")
