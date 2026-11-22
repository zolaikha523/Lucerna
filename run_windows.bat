@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else (
  echo No .venv found - using the system Python. Run setup_windows.bat first for a clean install.
)
if not exist .env if exist .env.example copy .env.example .env >nul
echo Starting Lucerna on http://localhost:8501  (close this window to stop it)
python -m streamlit run app\main.py --server.port 8501 --server.address 127.0.0.1
if errorlevel 1 pause
endlocal
