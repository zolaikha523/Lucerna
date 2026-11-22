# Deployment Checklist

## Before go-live
- [ ] `setup_windows.bat` completed without errors; `run_windows.bat` opens Lucerna.
- [ ] `.env` reviewed: data paths on an encrypted drive (BitLocker on), backup folder on a separate drive/share.
- [ ] System administrator account uses a strong unique password and two-step verification.
- [ ] Organisation(s) and projects created; each project has a data classification.
- [ ] Users created with the least role they need; temporary passwords shared securely.
- [ ] Ollama installed; `ollama pull gemma3:4b`; AI & Models › Check connection is green.
- [ ] External AI left off (`LUCERNA_EXTERNAL_AI_ENABLED=0`) unless a terms review is recorded.
- [ ] Nightly `backup_windows.bat` scheduled; one restore tested.
- [ ] `run_tests_windows.bat` passes on the target machine.

## Pilot with real data
- [ ] Run AI coding on one real transcript; compare with manual coding; adjust batch size/timeouts.
- [ ] Check every quotation in the first report against the original transcript.
- [ ] Check indicator values against a manual calculation in Excel.

## Before sharing a report with a donor
- [ ] All methodology fields completed (no unintended "Not provided").
- [ ] Review steps completed by named reviewers; report approved (no DRAFT label).
- [ ] Quotations: verified, approved, no identifying details; translations checked.
- [ ] Limitations section reviewed; no causal claims from observational data.
