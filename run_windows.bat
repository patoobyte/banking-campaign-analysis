@echo off
setlocal
cd /d "%~dp0"
title Market Signal

if not exist ".venv\Scripts\python.exe" (
 echo ERROR: The project environment is missing.
 echo Double-click setup_windows.bat first.
 pause
 exit /b 1
)
if not exist ".env" (
 copy /Y ".env.example" ".env" >nul
 echo ERROR: .env was missing and has been created.
 echo Add your API key, save it, then run this file again.
 start "" notepad.exe ".env"
 pause
 exit /b 1
)
findstr /C:"NAVY_API_KEY=replace-me" ".env" >nul
if not errorlevel 1 (
 echo ERROR: Replace NAVY_API_KEY=replace-me in .env before starting.
 start "" notepad.exe ".env"
 pause
 exit /b 1
)

call ".venv\Scripts\activate.bat"
start "" http://localhost:8501
python -m streamlit run app.py --server.port 8501 --server.headless true

echo.
echo Market Signal stopped. If an error appears above, see TROUBLESHOOTING.txt.
pause
