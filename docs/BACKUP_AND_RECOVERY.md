# Backup and Recovery

## What a backup contains
A ZIP named `lucerna_backup_YYYYMMDD_HHMMSS.zip` in `LUCERNA_BACKUP_DIR` with:
`database/lucerna.sqlite3` (consistent online snapshot), and optionally `uploads/`, `analytic/`, `outputs/`.
Existing backups are never overwritten or deleted by Lucerna.

## Making backups
- On demand: **Settings › Privacy & System › Backups › Create backup now** (system administrator).
- Scheduled: Windows Task Scheduler running `backup_windows.bat` daily. Point `LUCERNA_BACKUP_DIR` at another drive or share.
- Remove old backups yourself according to your retention policy.

## Restoring
1. Stop Lucerna (close the `run_windows.bat` window).
2. Keep a copy of the current data folder.
3. Unzip the backup. Copy `database\lucerna.sqlite3` to the `LUCERNA_DB` path, and the `uploads`, `analytic`, `outputs`
   folders into the matching `LUCERNA_*_DIR` folders.
4. Start Lucerna and check a project, a dataset preview, a document and a report download.

## Test your restore
Restore a backup into a separate folder (set `LUCERNA_DATA_DIR`/`LUCERNA_DB` to it in a copy of `.env`) at least once a quarter.
