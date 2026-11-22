# Troubleshooting

| Symptom | Fix |
|---|---|
| `setup_windows.bat` says Python not found | Install Python 3.12/3.13 with "Add to PATH", reopen the folder, run setup again |
| `pip install` fails on pyarrow/scipy | Use 64-bit Python 3.12 or 3.13; update pip; check the internet/proxy |
| Browser does not open | Open http://localhost:8501 manually; check the black window for errors |
| "Cannot reach Ollama at …" | Start the Ollama app (or `ollama serve`); check `OLLAMA_URL` |
| "Model 'gemma3:4b' is not installed" | `ollama pull gemma3:4b` |
| "The model did not answer within …" | Raise `OLLAMA_TIMEOUT_SECONDS`, keep `MAX_SEGMENTS_PER_LLM_BATCH=1`, close other programs, or use a smaller model |
| "Ollama ran out of memory" | Set `OLLAMA_NUM_GPU=0` (CPU) or use a smaller model |
| AI coding job failed midway | Coding & Codebook › **Resume last interrupted run** continues from the checkpoint |
| Upload rejected "does not match a real .xlsx file" | The file is renamed or corrupt; re-save it from Excel |
| Scanned PDF gives no text | Install Tesseract and `requirements-optional.txt`; OCR text then needs manual quote verification |
| Dari/Pashto letters unjoined in PDF | Known limitation; use the Word report |
| Locked out after failed sign-ins | Wait `LUCERNA_LOGIN_LOCK_MINUTES` or ask an administrator to reset the password |
| Signed out after refreshing the page | Expected; sign in again |
| A chart says "No records match the current filters" | Clear filters/cross-filter |
| "Database is locked" | Close SQLite browsers that have the database open for writing |
