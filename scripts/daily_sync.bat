@echo off
REM Daily sci99 -> Google Sheets sync (run by Task Scheduler)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python -X utf8 daily_sync.py
exit /b %ERRORLEVEL%
