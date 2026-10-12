@echo off
REM Start a scratch Chrome that carries YOUR echemi session (cookies copied from
REM your real profile) with the CDP port 9222, so the echemi scripts can attach
REM with --my-chrome. Your real Chrome is never touched.
set "HERE=%~dp0"
set "P=%HERE%.mychrome_profile"
set "SRC=%LOCALAPPDATA%\Google\Chrome\User Data"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

powershell -NoProfile -Command "try { Invoke-WebRequest 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% equ 0 (
  echo port 9222 already open - nothing to do.
  exit /b 0
)

mkdir "%P%\Default\Network" 2>nul
copy /y "%SRC%\Local State" "%P%\" >nul
copy /y "%SRC%\Default\Network\Cookies*" "%P%\Default\Network\" >nul
copy /y "%SRC%\Default\Preferences" "%P%\Default\" >nul
if not exist "%P%\Default\Network\Cookies" (
  echo cookie copy FAILED - cannot build the CDP profile.
  exit /b 1
)
echo session cookies copied from your Chrome profile.

REM kill only a stale scratch chrome (never your own browser)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*.mychrome_profile*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Start-Sleep -Seconds 1"

start "" "%CHROME%" --user-data-dir="%P%" --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check https://www.echemi.com/

powershell -NoProfile -Command "$ok=$false; foreach ($i in 1..20) { try { Invoke-WebRequest 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Milliseconds 500 } }; if ($ok) { 'port 9222 OK' } else { 'port 9222 FAILED' }"
