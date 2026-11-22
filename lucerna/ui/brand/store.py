"""Per-dashboard organisation branding: safe storage of logos and backgrounds, and the design system for a dashboard.

Everything is stored inside the dashboard's existing `branding_json` through `generator.update_meta`, so the brand
travels with save, reopen, rename, duplicate, theme change, presentation mode and versioning. No schema change.

    branding = {
      "logo": "org" | "custom" | "none",
      "logo_path": <PNG/JPEG stored by generator.save_logo; also used by PDF/Word exports>,
      "logo_svg": <file name of a sanitised SVG under data_dir/branding; screen only>,
      "brand": {"extracted": {...swatches...}, "custom": {"primary", "secondary", "accent"}, "background": "auto" | ...,
                "bg_image": <file name>, "tagline": str, "org_name": str, "logo_sha": str},
    }

File names never leave the server: the viewer embeds images as data URIs.
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import secrets
from functools import lru_cache
from pathlib import Path

from ...config import settings
from ...quant import generator
from ...security.rbac import CurrentUser, require
from . import design, extract, svg_safe
from .extract import BrandError

BG_MAX_BYTES = 4_000_000
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _dir() -> Path:
    d = settings().data_dir / "branding"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_file(name: str | None) -> Path | None:
    """Resolve a stored file name inside the branding folder only (no paths, no traversal)."""
    if not name or not _NAME_RE.match(name):
        return None
    p = (_dir() / name).resolve()
    if p.parent != _dir().resolve() or not p.exists():
        return None
    return p


def store_logo(user: CurrentUser, project_id: int, data: bytes) -> dict:
    """Validate and store an uploaded logo; returns the branding keys to save and the extracted colours."""
    require(user, "dashboard.edit", project_id)
    if not data:
        raise BrandError("The file is empty.")
    kind = extract.kind_of(data)
    colours = extract.extract(data)
    sha = hashlib.sha256(data).hexdigest()[:16]
    if kind == "svg":
        clean = svg_safe.sanitize(data)
        name = f"project_{int(project_id)}_{secrets.token_hex(6)}.svg"
        (_dir() / name).write_bytes(clean)
        keys = {"logo": "custom", "logo_path": None, "logo_svg": name}
    else:
        try:
            path = generator.save_logo(user, project_id=project_id, data=data)   # PNG/JPEG: also used by exports
        except generator.GenerationError as exc:
            raise BrandError(str(exc)) from exc
        keys = {"logo": "custom", "logo_path": path, "logo_svg": None}
    return {"keys": keys, "extracted": colours, "sha": sha}


def store_background(user: CurrentUser, project_id: int, data: bytes) -> str:
    """Re-encode an uploaded background photo (PNG/JPEG) as a metadata-free JPEG, max 1920 px wide."""
    require(user, "dashboard.edit", project_id)
    if not data or len(data) > BG_MAX_BYTES:
        raise BrandError("The background image must be a PNG or JPEG under 4 MB.")
    if extract.kind_of(data) == "svg":
        raise BrandError("Use a PNG or JPEG photo for the background.")
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise BrandError("The background image could not be read.") from exc
    if img.width * img.height > 60_000_000:
        raise BrandError("The background image is too large.")
    img = img.convert("RGB")
    img.thumbnail((1920, 1920))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True)
    name = f"bg_{int(project_id)}_{secrets.token_hex(6)}.jpg"
    (_dir() / name).write_bytes(out.getvalue())
    return name


# ---------------------------------------------------------------- reading a dashboard's brand

def logo(d: dict) -> tuple[bytes | None, str | None]:
    """(bytes, mime) of the logo shown on screen for this dashboard, or (None, None)."""
    b = d.get("branding") or {}
    if b.get("logo", "org") == "none":
        return None, None
    if b.get("logo") == "custom" and b.get("logo_svg"):
        p = _safe_file(b["logo_svg"])
        return (p.read_bytes(), "image/svg+xml") if p else (None, None)
    data = generator.logo_bytes(d)
    if not data:
        return None, None
    return data, ("image/png" if data[:4] == b"\x89PNG" else "image/jpeg")


def data_uri(data: bytes | None, mime: str | None) -> str | None:
    if not data or not mime:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@lru_cache(maxsize=32)
def _bg_uri(name: str) -> str | None:
    p = _safe_file(name)
    return data_uri(p.read_bytes(), "image/jpeg") if p else None


def background_uri(d: dict) -> str | None:
    name = ((d.get("branding") or {}).get("brand") or {}).get("bg_image")
    return _bg_uri(name) if name else None


@lru_cache(maxsize=64)
def _extract_cached(data: bytes) -> dict | None:
    try:
        return extract.extract(data)
    except BrandError:
        return None


def extracted(d: dict) -> dict | None:
    """Colours of this dashboard's logo: saved at upload time, else read from the organisation logo (cached)."""
    b = d.get("branding") or {}
    br = b.get("brand") or {}
    if br.get("use_logo_colours") is False:
        return None
    if b.get("logo") == "custom" and br.get("extracted"):
        return br["extracted"]
    data, _ = logo(d)
    return _extract_cached(data) if data else None


def custom_colours(d: dict) -> dict:
    c = (((d.get("branding") or {}).get("brand") or {}).get("custom") or {})
    return {k: v for k, v in c.items() if k in ("primary", "secondary", "accent") and isinstance(v, str) and HEX_RE.match(v)}


def design_for(d: dict, theme_key: str) -> dict:
    br = (d.get("branding") or {}).get("brand") or {}
    bg = br.get("background") or "auto"
    if bg == "image" and not background_uri(d):
        bg = "auto"
    return design.build(extracted(d), theme_key, custom=custom_colours(d), background=bg)
