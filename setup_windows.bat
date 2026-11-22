@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  Lucerna setup  -  From Data to Decisions
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 or 3.13 from python.org and tick "Add python.exe to PATH".
  goto fail
)
if not exist .venv (
  echo Creating a private Python environment in .venv ...
  python -m venv .venv
  if errorlevel 1 goto fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto fail
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env (
  copy .env.example .env >nul
  echo Created .env from .env.example. Edit it to move data to D:\ if you wish.
)
python -c "from lucerna import db; db.init(); print('Database ready:', __import__('lucerna.config', fromlist=['x']).settings().db_path)"
if errorlevel 1 goto fail
echo.
echo Setup complete.
echo  1. Install Ollama from https://ollama.com and run:  ollama pull gemma3:4b
echo  2. Double-click run_windows.bat
echo  Optional: pip install -r requirements-optional.txt  (OCR, tests)
pause
exit /b 0
:fail
echo.
echo Setup failed. Copy the messages above and share them for troubleshooting.
pause
exit /b 1
