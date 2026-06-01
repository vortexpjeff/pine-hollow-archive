@echo off
REM Pine Hollow Bioacoustics Review App Launcher
REM Opens in http://localhost:8501 — paste this into your preferred browser

wsl -d Ubuntu --cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive ^
  bash -c "source ~/miniconda3/bin/activate && streamlit run scripts/review_app.py --server.headless true"

pause
