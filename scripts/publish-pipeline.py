#!/usr/bin/env python3
"""Backward-compat shim → delegates to `python -m publisher`.

Cron entry point. Prefer `python -m publisher --config ...` for new callers.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from publisher.__main__ import main

sys.exit(main())
