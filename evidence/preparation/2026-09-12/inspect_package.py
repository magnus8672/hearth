"""Inspect the delivered Hearth design package without modifying its sources.

Run from the repository root with Python 3.12. Standard library only.
This validates documents/assets, not application behavior or hardware support.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zlib


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("inspection.json")
sources = sorted(
    [p for p in ROOT.iterdir() if p.is_file()]
    + [p for name in ("phases", "diagrams", "brand") for p in (ROOT / name).rglob("*") if p.is_file()]
)
errors = []


def relative(path):
    return path.relative_to(ROOT).as_posix()


def check_link(source, target):
    target = target.strip().strip("<>")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path:
        return
    resolved = (source.parent / unquote(parts.path)).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.exists():
        errors.append({"file": relative(source), "broken_local_link": target})


class LocalLinks(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                check_link(ROOT / "brand/index.html", value)


def png_dimensions(blob):
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG signature")
    offset = 8
    size = None
    ended = False
    while offset < len(blob):
        length = struct.unpack_from(">I", blob, offset)[0]
        kind = blob[offset + 4:offset + 8]
        data = blob[offset + 8:offset + 8 + length]
        expected = struct.unpack_from(">I", blob, offset + 8 + length)[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected:
            raise ValueError("PNG chunk CRC mismatch")
        if kind == b"IHDR":
            size = struct.unpack_from(">II", data)
        offset += 12 + length
        if kind == b"IEND":
            ended = True
            break
    if not size or not ended or offset != len(blob):
        raise ValueError("Incomplete PNG structure")
    return list(size)


def luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722)))


mermaid = []
pngs = []
svg_count = 0
for path in sources:
    try:
        if path.suffix == ".md":
            content = path.read_text(encoding="utf-8")
            for target in re.findall(r"!?\[[^\]]*\]\(([^)\n]+)\)", content):
                check_link(path, target)
            if len(re.findall(r"^```", content, re.M)) % 2:
                errors.append({"file": relative(path), "error": "Unbalanced code fences"})
            for index, _ in enumerate(re.findall(r"^```mermaid\s*$", content, re.M), 1):
                diagram = ROOT / "diagrams" / f"{path.stem}-{index}.svg"
                mermaid.append(relative(diagram))
                if not diagram.is_file():
                    errors.append({"file": relative(path), "missing_diagram": relative(diagram)})
        elif path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".svg":
            document = ET.parse(path)
            if document.getroot().tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError("Unexpected SVG root")
            svg_count += 1
        elif path.suffix == ".png":
            pngs.append({"file": relative(path), "dimensions": png_dimensions(path.read_bytes())})
    except Exception as exc:
        errors.append({"file": relative(path), "error": str(exc)})

LocalLinks().feed((ROOT / "brand/index.html").read_text(encoding="utf-8"))
tokens = json.loads((ROOT / "brand/tokens/hearth-tokens.json").read_text())
report = json.loads((ROOT / "brand/tokens/contrast-report.json").read_text())
contrast = []
for row in report["checks"]:
    palette = tokens["colors"][row["theme"]]
    values = sorted([luminance(palette[row["foreground"]]), luminance(palette[row["background"]])])
    ratio = (values[1] + 0.05) / (values[0] + 0.05)
    passed = ratio >= row["minimum"]
    contrast.append({**row, "recomputed_ratio": ratio, "recomputed_pass": passed})
    if not passed or round(ratio, 3) != row["ratio"] or passed != row["pass"]:
        errors.append({"contrast_mismatch": row})

css = (ROOT / "brand/tokens/hearth.css").read_text()
selectors = {
    "default_light": (r":root\s*\{([^}]+)\}", "light"),
    "explicit_light": (r':root\[data-theme="light"\]\s*\{([^}]+)\}', "light"),
    "explicit_dark": (r':root\[data-theme="dark"\]\s*\{([^}]+)\}', "dark"),
    "system_dark": (r':root:not\(\[data-theme="light"\]\)\s*\{([^}]+)\}', "dark"),
}
for name, (pattern, theme) in selectors.items():
    block = re.search(pattern, css).group(1)
    values = dict(re.findall(r"--hearth-([\w-]+):\s*(#[A-Fa-f0-9]{6})", block))
    if values != tokens["colors"][theme]:
        errors.append({"css_token_mismatch": name})

catalog = json.loads((ROOT / "brand/icons/catalog.json").read_text())
sprite = ET.parse(ROOT / "brand/icons/hearth-icons.svg")
symbols = {el.attrib["id"] for el in sprite.iter() if el.tag.endswith("}symbol")}
inline_text = (ROOT / "brand/previews/icons-inline.js").read_text()
inline_icons = json.loads(inline_text.partition("=")[2].strip().removesuffix(";"))
for entry in catalog:
    if not (ROOT / "brand/icons" / entry["file"]).is_file() or entry["symbol"] not in symbols:
        errors.append({"invalid_icon_entry": entry})
    standalone = ET.parse(ROOT / "brand/icons" / entry["file"]).getroot()
    inline = ET.fromstring(inline_icons[entry["name"]])
    # Standalone icons are informative; gallery copies are decorative.
    # Compare their drawing geometry, preserving the intentional ARIA differences.
    if standalone.attrib["viewBox"] != inline.attrib["viewBox"] or [ET.tostring(child) for child in standalone] != [ET.tostring(child) for child in inline]:
        errors.append({"inline_icon_mismatch": entry["name"]})
brand_data = json.loads((ROOT / "brand/previews/brand-data.json").read_text())
if brand_data["palette"] != tokens["colors"] or set(brand_data["icons"]) != set(inline_icons):
    errors.append({"preview_data_mismatch": True})

ico = (ROOT / "brand/logos/hearth.ico").read_bytes()
reserved, kind, count = struct.unpack_from("<HHH", ico)
ico_sizes = []
if (reserved, kind) != (0, 1):
    errors.append({"ico_header_invalid": True})
for index in range(count):
    width, height, _, _, _, _, length, offset = struct.unpack_from("<BBBBHHII", ico, 6 + 16 * index)
    dimensions = [width or 256, height or 256]
    if png_dimensions(ico[offset:offset + length]) != dimensions:
        errors.append({"ico_frame_mismatch": index})
    ico_sizes.append(dimensions)

gates = re.findall(r"^\| ([ESCA]\d{2}) \|", (ROOT / "09-VALIDATION-AND-RELEASE.md").read_text(encoding="utf-8"), re.M)
result = {
    "inspected_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Delivered design/brand sources only; no application, provider, browser interaction, or hardware acceptance test",
    "status": "PASS" if not errors else "FAIL",
    "file_count": len(sources),
    "extension_counts": dict(Counter(p.suffix for p in sources)),
    "markdown_files": [relative(p) for p in sources if p.suffix == ".md"],
    "mermaid_count": len(mermaid),
    "matching_diagram_files": mermaid,
    "parsed_svg_count": svg_count,
    "brand_logo_icon_svg_count": sum(p.suffix == ".svg" and p.parent.name in ("icons", "logos") for p in sources),
    "icon_catalog_count": len(catalog),
    "contrast_check_count": len(contrast),
    "contrast_checks": contrast,
    "css_palette_blocks_checked": list(selectors),
    "png_chunk_validation": pngs,
    "ico_frame_dimensions": ico_sizes,
    "gate_ids": gates,
    "gate_counts": dict(Counter(gate[0] for gate in gates)),
    "errors": errors,
    "source_inventory": [{"file": relative(p), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
}
OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key not in ("source_inventory", "contrast_checks", "markdown_files", "png_chunk_validation", "matching_diagram_files", "gate_ids")}, indent=2))
sys.exit(1 if errors else 0)
