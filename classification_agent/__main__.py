#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
classification_agent Entrypoint
===========================================================
Usage:
    python -m classification_agent
===========================================================
"""

from .classifier import train_regime_classifier

if __name__ == "__main__":
    train_regime_classifier()