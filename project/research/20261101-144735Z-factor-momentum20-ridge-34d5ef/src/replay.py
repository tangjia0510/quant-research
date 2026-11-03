#!/usr/bin/env python3
"""Rebuild historical pipeline in work; default dry-run, explicit --execute for compute."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from legacy_replay import main
if __name__ == '__main__': main(Path(__file__).resolve().parents[1].name)
