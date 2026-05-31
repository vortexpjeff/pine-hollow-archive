#!/bin/bash
# Pine Hollow Bioacoustics Review App Launcher
# Run from WSL: bash launch_review_app.sh

cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive
source ~/miniconda3/bin/activate base 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null
streamlit run scripts/review_app.py --server.headless true
