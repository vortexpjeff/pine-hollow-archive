@echo off
REM Pine Hollow Field Validation Desk — private localhost only
start "" http://localhost:8765
wsl -d Ubuntu --cd /mnt/c/Users/Jeffrey/Desktop/pine-hollow-archive /usr/bin/python3 scripts/run_validation_desk.py --host 127.0.0.1 --port 8765
pause
