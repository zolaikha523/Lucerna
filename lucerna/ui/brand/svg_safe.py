"""Safe handling of user-supplied SVG files.

SVG is XML that can carry scripts, event handlers, external references and entity tricks. Before an SVG is stored or
shown, DOCTYPE and ENTITY declarations are rejected outright, then it is parsed with
defusedxml when installed (no entities, no external DTDs), otherwise with the standard library parser. Scripts, foreignObject, event attributes,
external links and CSS imports are removed, and the result is re-serialised. Display is always through an <img> data
URI, where browsers never run scripts.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:                                   # preferred hardened parser; Lucerna's requirements files are protected, so it is optional
    from defusedxml import ElementTree as DET
except ImportError:                    # pragma: no cover — DOCTYPE/ENTITY are rejected before parsing, so stdlib expat is safe here
    DET = None

from .extract import BrandError

SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
FORBIDDEN_TAGS = {"script", "foreignobject", "iframe", "embed", "object", "audio", "video", "animate", "set", "animatemotion", "animatetransform", "handler"}
MAX_ELEMENTS = 20_000


def parse(data: bytes) -> ET.Element:
    if len(data) > 2_000_000:
        raise BrandError("The SVG is larger than 2 MB.")
    if re.search(rb"<!(DOCTYPE|ENTITY)", data, re.I):
        raise BrandError("SVG files with DOCTYPE or ENTITY declarations are not accepted.")
    try:
        root = DET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True) if DET else ET.fromstring(data)
    except Exception as exc:  # noqa: BLE001
        raise BrandError("The SVG could not be read as a valid image.") from exc
    if not isinstance(root.tag, str) or root.tag.split("}")[-1].lower() != "svg":
        raise BrandError("The file is not an SVG image.")
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        raise BrandError("The SVG is too complex.")
    return root


def _safe_ref(v: str) -> bool:
    v = v.strip().lower()
    return v.startswith("#") or v.startswith("data:image/png") or v.startswith("data:image/jpeg")


def sanitize(data: bytes) -> bytes:
    root = parse(data)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK)
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.split("}")[-1].lower() if isinstance(child.tag, str) else ""
            if not isinstance(child.tag, str) or tag in FORBIDDEN_TAGS:
                parent.remove(child)
    for el in root.iter():
        for k in list(el.attrib):
            name = k.split("}")[-1].lower()
            v = el.attrib[k]
            if name.startswith("on") or (name == "href" and not _safe_ref(v)):
                del el.attrib[k]
            elif name == "style" and re.search(r"url\(\s*['\"]?(?!#)|@import|expression\(|javascript:", v, re.I):
                del el.attrib[k]
        tag = el.tag.split("}")[-1].lower() if isinstance(el.tag, str) else ""
        if tag == "style" and el.text and re.search(r"@import|url\(\s*['\"]?(?!#)|javascript:", el.text, re.I):
            el.text = ""
    return ET.tostring(root, encoding="utf-8")
