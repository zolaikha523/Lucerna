@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pip install pytest >nul
python -m pytest tests -v
pause
