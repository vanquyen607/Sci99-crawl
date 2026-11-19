@echo off
REM Parallel-lane TEST run (does not replace daily_sync.py / Task Scheduler)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python -X utf8 run_parallel_test.py --live
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
