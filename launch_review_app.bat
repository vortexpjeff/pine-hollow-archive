@echo off
REM Pine Hollow Bioacoustics Review App Launcher
REM Double-click this file to open the review app

wsl -d Ubuntu --cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive ^
  bash -c "source ~/miniconda3/bin/activate && streamlit run scripts/review_app.py"

pause
