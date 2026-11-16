#!/usr/bin/env python3
"""Versioned case-definition adapter for the covariance/drag screen."""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "scripts/mpcc_prediction_research.py"
spec = importlib.util.spec_from_file_location("mpcc_prediction_research_covariance_impl", source)
impl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = impl
spec.loader.exec_module(impl)
impl.CONFIGS = ROOT / "config/research/mpcc_prediction_v1/covariance-screen-20261104-v1"
impl.__file__ = str(Path(__file__).resolve())
impl.main()
