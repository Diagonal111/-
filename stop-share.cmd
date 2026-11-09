@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" share.py --stop
pause
