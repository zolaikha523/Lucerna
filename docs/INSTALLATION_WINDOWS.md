# Installation on Windows 10/11

## Requirements
- Python 3.12 or 3.13 from python.org (tick **Add python.exe to PATH** during install).
- 8 GB RAM minimum; 16 GB recommended for gemma3:4b.
- Ollama (https://ollama.com) for AI features. Lucerna works without it, but AI coding and Q&A will report that the model cannot be reached.

## Steps
1. Unzip Lucerna to a folder, e.g. `D:\Lucerna`.
2. Double-click **`setup_windows.bat`**. It creates a private Python environment (`.venv`), installs the packages in
   `requirements.txt`, copies `.env.example` to `.env`, and prepares the database.
3. (Recommended) Edit `.env` to keep data on the D: drive — uncomment the `D:\LucernaData` lines.
4. Install Ollama, open a Command Prompt and run `ollama pull gemma3:4b`.
5. Double-click **`run_windows.bat`**. Your browser opens http://localhost:8501 (if not, open it manually).
6. On first start, create the system administrator account and your organisation.
7. Go to **Settings › AI & Models › Check connection** to confirm Ollama and the model are found.

## Upgrading from EvidenceQDA
Copy the old `data` folder into the Lucerna folder before the first start. If `data\evidenceqda.sqlite3` exists and
no Lucerna database exists yet, Lucerna uses that file and migrates it in place, keeping users, audit history and chats.
Take a copy of the old `data` folder first.

## Optional components
- OCR for scanned PDFs: install Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) and run
  `.venv\Scripts\pip install -r requirements-optional.txt`.
- Tests: `run_tests_windows.bat`.

## Nightly backups
Windows Task Scheduler → Create Basic Task → Daily → Start a program → `D:\Lucerna\backup_windows.bat`.
Set `LUCERNA_BACKUP_DIR` in `.env` to a different drive or network share.

## Access from other computers
By default Lucerna listens only on this computer (127.0.0.1). Serving it to a network requires HTTPS via a reverse
proxy (e.g. Caddy or IIS) and firewall rules; do not expose it directly. See `docs/SECURITY_AND_PRIVACY.md`.
