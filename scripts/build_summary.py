#!/usr/bin/env python3
"""
Generate docs/SUMMARY.md for mkdocs-literate-nav as a pure bullet list
(no Markdown headings), so the plugin can parse it deterministically.

Sections:
* [Home](index.md)
* Knowledge
    * Rulebook
        * <rewritten items from Rulebook/SUMMARY.md>
    * RAM 5
        * <rewritten items from RAM5/SUMMARY.md>
    * Organizational Handbook
        * <rewritten items from Handbook/summary.md>
* [About](about.md)
"""

from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUT_FILE = DOCS_DIR / "SUMMARY.md"

ORDER = ["rulebook", "ram5", "handbook"]
TITLE_MAP = {
    "rulebook": "Rulebook",
    "ram5": "RAM 5",
    "handbook": "Organizational Handbook",
}

# Match Markdown links: [label](href)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Match bullet items (leading spaces + '-' or '*' + space + content)
LIST_ITEM_RE = re.compile(r"^(\s*[-*]\s+)(.+?)\s*$")
# Any asterisk (wildcard) in the token
HAS_WILDCARD_RE = re.compile(r"\*")

def is_external(href: str) -> bool:
    return href.startswith(("http://", "https://", "mailto:"))

def split_anchor(path: str) -> Tuple[str, str]:
    if "#" in path:
        p, frag = path.split("#", 1)
        return p, "#" + frag
    return path, ""

def rewrite_href(href: str, src_root: Path, section_key: str) -> str:
    """Rewrite relative hrefs to external/<section>/...; keep pure anchors/external URLs."""
    if href.startswith("#") or is_external(href):
        return href
    path_part, anchor = split_anchor(href)
    abs_path = (src_root / path_part).resolve()
    try:
        rel_in_source = abs_path.relative_to(src_root.resolve())
    except ValueError:
        return href  # escapes the source root, leave as-is
    new_path = posixpath.join("external", section_key, *rel_in_source.parts)
    return new_path + anchor

def filename_to_label(path: str) -> str:
    """Generate a readable label from a filename (with special-casing index/readme)."""
    p, _ = split_anchor(path)
    stem = Path(p).stem or "Untitled"
    if stem.lower() in {"index", "readme"}:
        parent = Path(p).parent.name
        stem = parent if parent else "Home"
    words = stem.replace("-", " ").replace("_", " ").strip().split()
    return " ".join(w if w.isupper() else w.capitalize() for w in words) or "Untitled"

def normalize_item_token(token: str, src_root: Path, section_key: str) -> str:
    """
    Normalize a single list item 'token' to a proper Markdown link or wildcard path.
    Returns the content to put after the '* ' (without leading marker).
    """
    # If it’s already a Markdown link, rewrite href and keep label
    m = MD_LINK_RE.search(token)
    if m:
        label, url = m.group(1), m.group(2)
        new_url = rewrite_href(url, src_root, section_key)
        return f"{new_url}"

    # Wildcards (*.md or sub/*.md): rewrite prefix only
    if HAS_WILDCARD_RE.search(token) and not is_external(token) and not token.startswith("#"):
        prefix, anchor = split_anchor(token)
        parts = Path(prefix).parts
        return posixpath.join("external", section_key, *parts) + anchor

    # Plain markdown path -> convert to link (label from filename)
    if re.search(r"\.(md|markdown)(#[A-Za-z0-9._\-]+)?$", token, flags=re.IGNORECASE):
        new_url = rewrite_href(token, src_root, section_key)
        label = filename_to_label(token)
        return f"{new_url}"

    # Anything else (e.g., a bare section title inside upstream) – return empty to skip
    return ""

def collect_section_items(src_root: Path, summary_path: Path, section_key: str) -> List[str]:
    """
    Read the upstream SUMMARY and return normalized bullet items (each starts with 8 spaces + '* ').
    We only collect valid list items; headings and non-list lines are ignored.
    """
    out: List[str] = []
    for raw in summary_path.read_text(encoding="utf-8").splitlines():
        m = LIST_ITEM_RE.match(raw)
        if not m:
            # ignore headings / blank lines; we define the section header ourselves
            continue
        token = m.group(2).strip()
        normalized = normalize_item_token(token, src_root, section_key)
        if normalized:
            out.append(f"        * {normalized}")
    # Ensure at least a placeholder if nothing collected
    if not out:
        out.append("        * *(content not available)*")
    return out

def parse_triplets(args: Iterable[str]) -> Dict[str, Tuple[Path, Path]]:
    out: Dict[str, Tuple[Path, Path]] = {}
    for a in args:
        try:
            key, src_dir, summ = a.split("|", 2)
        except ValueError:
            raise SystemExit(f"Invalid argument '{a}'. Expected: key|src_root|summary_path")
        out[key] = (Path(src_dir), Path(summ))
    return out

def build_merged_summary(triplets: Dict[str, Tuple[Path, Path]]) -> str:
    lines: List[str] = []

    # Top-level items (no headings)
    lines.append("* [Home](index.md)")

    # Knowledge block with 3 subsections
    lines.append("* Knowledge")
    for key in ["rulebook", "ram5", "handbook"]:
        title = TITLE_MAP[key]
        lines.append(f"    * {title}")
        if key in triplets:
            src_root, summ = triplets[key]
            lines.extend(collect_section_items(src_root, summ, key))
        else:
            lines.append("        * *(content not available)*")

    # About
    lines.append("* [About](about.md)")

    return "\n".join(lines) + "\n"

def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    triplets = parse_triplets(sys.argv[1:])
    merged = build_merged_summary(triplets)
    OUT_FILE.write_text(merged, encoding="utf-8")
    print(f"[INFO] Wrote merged SUMMARY to {OUT_FILE}")

if __name__ == "__main__":
    main()