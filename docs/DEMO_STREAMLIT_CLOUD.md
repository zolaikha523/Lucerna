# Public demo on Streamlit Community Cloud (optional)

This is for showing Lucerna with **synthetic data only**. Never put real or personal data in a public demo.

1. Push the repository to GitHub. In Streamlit Community Cloud choose **New app**, pick the repository, and set:
   - **Main file path:** `app/main.py`
   - **Python version:** 3.13, 3.12 or 3.11 (the 91 tests also pass on 3.11)
2. Under **Advanced settings › Secrets** add one line: `LUCERNA_DEMO_MODE = "1"`
3. Deploy. On the first start (about 20–60 seconds) Lucerna builds the synthetic demo workspace (see `tests/seed_demo.py`).
   The login page then shows the demo sign-in: `admin` / `Lucerna-Demo-2026!`.

How it behaves:
- Community Cloud storage is temporary. When the app restarts, the demo is rebuilt from scratch, and anything
  visitors added is gone.
- The demo credentials are public, so a visitor could change the admin password until the next restart.
- There is no Ollama on Community Cloud. The optional "Reword with local AI" and the AI coding features report that
  the model is unavailable. Everything else, including dashboard generation, works without AI.
- Demo mode only seeds a database that has **no users**. It never touches an existing installation, but do not set
  `LUCERNA_DEMO_MODE` on a real installation, because the login page would advertise the demo sign-in.

Tested here: a local run with `LUCERNA_DEMO_MODE=1` and an empty data folder seeded the demo, showed the notice, and
signed in. A deployment to Community Cloud itself was **not** performed from this build environment.
