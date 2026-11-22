@echo off
rem Creates a Lucerna backup ZIP in LUCERNA_BACKUP_DIR. Schedule it in Windows Task Scheduler for nightly backups.
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); from lucerna import db; db.init(); from lucerna.services import backup; print('Backup written:', backup.create_backup('scheduled-backup'))"
if errorlevel 1 (echo Backup FAILED & exit /b 1)
endlocal
