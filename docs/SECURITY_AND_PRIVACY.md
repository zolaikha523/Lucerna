# Security and Privacy

## Controls
- Accounts with PBKDF2-HMAC-SHA256 (240,000 iterations, per-user salt); passwords ≥10 characters with 3 character classes, not containing the username.
- Lockout after `LUCERNA_LOGIN_MAX_FAILURES` failures for `LUCERNA_LOGIN_LOCK_MINUTES`.
- TOTP two-step verification with single-use recovery codes; enabled only after a confirmed code; disabling requires the password.
- Sessions validated on every page load; expire after `LUCERNA_SESSION_HOURS`; revocable per device; revoked on password reset or deactivation.
- RBAC enforced in the service layer (not only hidden buttons); denials are audited.
- Organisation and project isolation; members can only be added to projects of their organisation.
- Uploads: extension allow-list, size limit, content signature check, executable/script rejection, stored under random names outside the web root.
- Exports drop personal names and phone numbers by default; identifiers can be pseudonymised (HMAC keyed per project).
- PII patterns (phones, e-mails, ID numbers) detected in transcripts and redacted in report quotations by default.
- Audit log of security and data events without document or prompt content.
- External AI gate (see `docs/AI_CONFIGURATION.md`); Restricted projects never leave the machine.
- Streamlit hardened: XSRF protection on, listens on 127.0.0.1, error details hidden, usage statistics off.

## Responsibilities of the deploying organisation
- Encrypt the data drive (BitLocker) and back up to a separate, access-controlled location.
- Use HTTPS via a reverse proxy if Lucerna is served beyond the local computer.
- Obtain informed consent and follow your data-protection policy (e.g. IASC Operational Guidance on Data Responsibility).
- Review who has which role at least quarterly.

No formal certification or compliance is claimed.
