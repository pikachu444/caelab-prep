@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_and_run_prep.ps1" %*
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo CAELab Prep failed to start. See the message above.
    pause
)
exit /b %result%
