"""Record or verify SHA-256 hashes of the protected engine files (everything outside the presentation layer).

    python tools/protected_hashes.py record  docs/design_baseline/protected_hashes.json
    python tools/protected_hashes.py verify  docs/design_baseline/protected_hashes.json

Protected: lucerna/** except lucerna/ui/** (the presentation layer), plus app/, tests/ engine tests, requirements,
Windows scripts and the .env example. Exit code 1 if any protected file was changed, added or removed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["lucerna/**/*.py", "lucerna/**/*.sql", "app/**/*.py", "requirements*.txt", "*.bat", ".env.example",
           "tests/test_lucerna.py", "tests/test_quality_gate.py", "tests/test_dashboard_engine.py"]
EXCLUDE_PREFIX = ("lucerna/ui/",)


def files() -> list[Path]:
    out = set()
    for pat in INCLUDE:
        for p in ROOT.glob(pat):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and "__pycache__" not in rel and not rel.startswith(EXCLUDE_PREFIX):
                out.add(p)
    return sorted(out)


def digest() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files()}


if __name__ == "__main__":
    mode, path = sys.argv[1], Path(sys.argv[2])
    now = digest()
    if mode == "record":
        path.write_text(json.dumps(now, indent=1, sort_keys=True), encoding="utf-8")
        print(f"recorded {len(now)} protected files")
    else:
        base = json.loads(path.read_text(encoding="utf-8"))
        changed = [f for f in base if f in now and now[f] != base[f]]
        removed = [f for f in base if f not in now]
        added = [f for f in now if f not in base]
        print(f"{len(base)} protected files checked: {len(changed)} changed, {len(removed)} removed, {len(added)} added")
        for k, lst in (("CHANGED", changed), ("REMOVED", removed), ("ADDED", added)):
            for f in lst:
                print(k, f)
        sys.exit(1 if changed or removed or added else 0)
