@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m streamlit run app.py --server.address 0.0.0.0 --server.port 8512
) else (
  python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8512
)
pause
