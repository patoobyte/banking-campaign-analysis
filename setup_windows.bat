@echo off
setlocal
cd /d "%~dp0"
title Market Signal Setup

echo ========================================
echo Market Signal - Windows setup
echo ========================================

set "PYTHON_CMD="
where py >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD (
 where python >nul 2>&1 && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
 echo ERROR: Python was not found.
 echo Install Python 3.11 from https://www.python.org/downloads/
 echo Enable "Add python.exe to PATH", then run this file again.
 start "" "https://www.python.org/downloads/"
 pause
 exit /b 1
)

set "CHROME_FOUND="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_FOUND=1"
if not defined CHROME_FOUND (
 echo ERROR: Google Chrome is required for browser research.
 echo Install Chrome, then run this file again.
 start "" "https://www.google.com/chrome/"
 pause
 exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
 echo Creating isolated Python environment...
 %PYTHON_CMD% -m venv .venv
 if errorlevel 1 goto :failed
) else (
 echo Existing .venv found; updating it.
)

call ".venv\Scripts\activate.bat"
echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :failed

echo Installing Streamlit, LangChain, LangGraph, Playwright and all dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed

if not exist "data" mkdir "data"
if not exist "data\chrome-profile" mkdir "data\chrome-profile"
if not exist "reports" mkdir "reports"
if not exist "screenshots" mkdir "screenshots"

if not exist ".env" (
 copy /Y ".env.example" ".env" >nul
 echo.
 echo IMPORTANT: .env was created. Open it and replace NAVY_API_KEY=replace-me.
 start "" notepad.exe ".env"
)

echo Checking Python dependencies and source code...
python -m pip check
if errorlevel 1 goto :failed
python -m py_compile app.py backend.py agent_backend.py persistent_browser.py
if errorlevel 1 goto :failed

echo.
echo SETUP COMPLETE.
echo Edit .env if needed, then double-click run_windows.bat.
pause
exit /b 0

:failed
echo.
echo SETUP FAILED. Copy the error above and see TROUBLESHOOTING.txt.
pause
exit /b 1
