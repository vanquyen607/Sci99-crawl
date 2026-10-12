@echo off
REM Start a scratch Chrome that carries YOUR echemi session (cookies copied from
REM your real profile) with the CDP port 9222, so the echemi scripts can attach
REM with --my-chrome. Your real Chrome is never touched.
REM Logic lives in cdp_browser.py (same code daily_sync uses).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -X utf8 cdp_browser.py
exit /b %ERRORLEVEL%
