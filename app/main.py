"""Lucerna — From Data to Decisions.

Entry point: `python -m streamlit run app/main.py` (run_windows.bat does this for you).
The previous EvidenceQDA interface is preserved in app/legacy_evidenceqda_main.py for reference.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # python-dotenv is optional; environment variables still work
    pass

from lucerna import demo  # noqa: E402

if demo.enabled():   # public demo with synthetic data only (see lucerna/demo.py)
    demo.ensure_demo()

from lucerna.ui.app import main  # noqa: E402

main()
