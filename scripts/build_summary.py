#!/usr/bin/env python3
"""
Build a merged docs/SUMMARY.md for mkdocs-literate-nav from three upstream summaries.

Features
--------
- Fixed order: Rulebook -> RAM 5 -> Organizational Handbook
- Rewrites relative links from each upstream summary so they point to:
    external/rulebook/...
    external/ram5/...
    external/handbook/...
- Preserves anchor fragments (#...) and external URLs
- Keeps Markdown link syntax [label](url) intact for literate-nav parsing
- Converts plain-path bullets like "- about.md" into links with auto labels
- Rewrites wildcard bullets (e.g., "- *.md", "- subdir/*.md") to the new prefix + wildcard
- Writes a fully structured docs/SUMMARY.md:
    # Home
    - [Home](index.md)
    # Knowledge
    ## Rulebook
    ...
    ## RAM 5
    ...
    ## Organizational Handbook
    ...
    # About
    - [About](about.md)

Usage (called by scripts/sync_external_content.py)
--------------------------------------------------
python scripts/build_summary.py \
  rulebook|/abs/src/rulebook/documentation|/abs/src/rulebook/documentation/SUMMARY.md \
  ram5|/abs/src/ram5/docs|/abs/src/ram5/docs/summary.md \
  handbook|/abs/src/handbook/OrganizationalHandbook|/abs/src/handbook/OrganizationalHandbook/summary.md
"""

from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Repository layout
REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUT_FILE = DOCS_DIR / "SUMMARY.md"

# Section order and titles
ORDER = ["rulebook", "ram5", "handbook"]
TITLE_MAP = {
    "rulebook": "Rulebook",
    "ram5": "RAM 5",
    "handbook": "Organizational Handbook",
}

# Regexes
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")  # [label](url)
LIST_ITEM_RE = re.compile(r"^(\s*[-*]\s+)(.+?)\s*$")  # captures indent/marker + content
HAS_WILDCARD_RE = re.compile(r"[*]")  # wildcard anywhere in the token

def is_external(href: str) -> bool:
    return href.startswith(("http://", "https://", "mailto:"))

def split_anchor(path: str) -> Tuple[str, str]:
    """Split an href into (path_part, anchor_with_hash or '')."""
    if "#" in path:
        p, frag = path.split("#", 1)
        return p, "#" + frag
    return path, ""

def rewrite_href(href: str, src_root: Path, section_key: str) -> str:
    """
    Rewrite a single href to the target docs/external/<section>/... location if it's relative.
    Preserve pure anchors and external URLs.
    """
    if href.startswith("#") or is_external(href):
        return href

    path_part, anchor = split_anchor(href)
    abs_path = (src_root / path_part).resolve()

    try:
        rel_in_source = abs_path.relative_to(src_root.resolve())
    except ValueError:
        # If it escapes src_root via "..", keep as-is
        return href

    new_path = posixpath.join("external", section_key, *rel_in_source.parts)
    return new_path + anchor

def filename_to_label(path: str) -> str:
    """
    Create a readable label from a file path:
    - take the final path segment (without extension and anchor)
    - replace '-', '_' with spaces and title-case it
    """
    p, _anchor = split_anchor(path)
    name = Path(p).name
    stem = Path(name).stem  # drop extension
    # common names -> friendlier labels
    if stem.lower() in {"readme", "index"}:
        stem = Path(p).parent.name or "Home"
    label = stem.replace("-", " ").replace("_", " ").strip()
    # Title-case but keep all-caps if already uppercase (e.g., RAM)
    label = " ".join(w if w.isupper() else w.capitalize() for w in label.split())
    return label or "Untitled"

def rewrite_links_in_line(line: str, src_root: Path, section_key: str) -> str:
    """
    - Rewrites Markdown links, preserving [label](url) structure.
    - Also normalizes plain-path list items into proper links or wildcard items.
    """

    # 1) Rewrite any explicit Markdown links, preserving the label
    def _sub(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        new_url = rewrite_href(url, src_root, section_key)
        return f"[{label}]({new_url})"
    line_after_links = MD_LINK_RE.sub(_sub, line)

    # 2) Handle list items that are just plain paths or contain wildcards
    m = LIST_ITEM_RE.match(line_after_links)
    if not m:
        return line_after_links  # headings, blank lines, etc. pass through

    lead, content = m.group(1), m.group(2)

    # If the content already contains a Markdown link after step 1, keep it
    if MD_LINK_RE.search(content):
        return line_after_links

    # Wildcards are allowed by literate-nav inside list items (not links)
    # e.g., "*.md", "subdir/*.md" -> rewrite the path prefix to external/<section>/...
    if HAS_WILDCARD_RE.search(content):
        # Attempt to rewrite wildcard path if it looks relative
        # For safety, only rewrite if it doesn't start with http(s) or "#"
        if not is_external(content) and not content.startswith("#"):
            # Split out any leading path before the wildcard; we join under external/<section>
            # Examples:
            #   "*.md"           -> external/<section>/*.md
            #   "sub/*.md"       -> external/<section>/sub/*.md
            #   "sub/deep/*.md"  -> external/<section>/sub/deep/*.md
            # We don't resolve actual files; literate-nav will expand the pattern.
            prefix, anchor = split_anchor(content)  # anchor unlikely with wildcard but safe
            # Normalize separators in 'prefix'
            parts = Path(prefix).parts
            new_token = posixpath.join("external", section_key, *parts) + anchor
            return f"{lead}{new_token}"
        return line_after_links

    # If content looks like a relative Markdown file, convert it to a link with a generated label
    # Recognize common Markdown extensions + optional '#fragment'
    if re.search(r"\.(md|markdown)(#[A-Za-z0-9._\-]+)?$", content, flags=re.IGNORECASE):
        new_url = rewrite_href(content, src_root, section_key)
        label = filename_to_label(content)
        return f"{lead}[{label}]({new_url})"

    # Otherwise, leave as-is (could be a pure section title without content on this line)
    return line_after_links

def process_upstream_summary(section_key: str, src_root: Path, summary_path: Path) -> str:
    """
    Read the upstream summary, rewrite links and list items, and return Markdown.
    """
    text = summary_path.read_text(encoding="utf-8")
    out_lines: List[str] = []
    for raw_line in text.splitlines():
        out_lines.append(rewrite_links_in_line(raw_line, src_root, section_key))
    # Ensure single trailing newline
    return "\n".join(out_lines).rstrip() + "\n"

def parse_triplets(args: Iterable[str]) -> Dict[str, Tuple[Path, Path]]:
    """
    Parse CLI args: "key|src_root|summary_path" into { key: (src_root_path, summary_path) }.
    """
    result: Dict[str, Tuple[Path, Path]] = {}
    for a in args:
        try:
            key, src_dir, summ = a.split("|", 2)
        except ValueError:
            raise SystemExit(
                f"Invalid argument '{a}'. Expected format: key|src_root|summary_path"
            )
        result[key] = (Path(src_dir), Path(summ))
    return result

def build_merged_summary(triplets: Dict[str, Tuple[Path, Path]]) -> str:
    """
    Compose the final SUMMARY.md content in the fixed order.
    """
    parts: List[str] = []

    # Home
    parts.append("# Home\n")
    parts.append("- [Home](index.md)\n")

    # Knowledge sections
    parts.append("\n# Knowledge\n")
    for key in ORDER:
        title = TITLE_MAP[key]
        parts.append(f"\n## {title}\n")
        if key in triplets:
            src_root, summ = triplets[key]
            parts.append(process_upstream_summary(key, src_root, summ))
        else:
            parts.append("- *(content not available)*\n")

    # About
    parts.append("\n# About\n")
    parts.append("- [About](about.md)\n")

    return "".join(parts)

def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    triplets = parse_triplets(sys.argv[1:])
    merged = build_merged_summary(triplets)
    OUT_FILE.write_text(merged, encoding="utf-8")
    print(f"[INFO] Wrote merged SUMMARY to {OUT_FILE}")

if __name__ == "__main__":
    main()