@echo off
REM Double-click root launcher for SCI99 Sheets GUI
cd /d "%~dp0scripts"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw -X utf8 "%~dp0scripts\sci99_gui.py"
) else (
  python -X utf8 "%~dp0scripts\sci99_gui.py"
)
