#!/bin/bash
set -euo pipefail
cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
exec /usr/bin/python3 scripts/run_validation_desk.py --host 127.0.0.1 --port 8765
