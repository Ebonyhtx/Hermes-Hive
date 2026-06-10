#!/usr/bin/env python3
"""
Cross-platform HIVE daemon launcher.
Usage:
  python start.py          # Start daemon (default)
  python start.py stop     # Stop daemon
  python start.py status   # Check status

No shell scripts needed — works on Windows, macOS, Linux.
"""
import sys
from orchestrator.daemon import main

if __name__ == "__main__":
    main()
