#!/usr/bin/env python3
"""
Concatenate and rewrite upstream summary files into docs/SUMMARY.md for mkdocs-literate-nav.

Behavior
--------
- Reads the triplets passed as CLI arguments: "key|src_root|summary_path"
  where:
    key in {"rulebook", "ram5", "handbook"}
    src_root is the absolute path to the source folder that will be copied into docs/external/<key>/
    summary_path is the absolute path to the summary file inside that source tree

- Rewrites relative links inside each upstream summary so they point to the new locations:
    rulebook  -> external/rulebook/...
    ram5      -> external/ram5/...
    handbook  -> external/handbook/...

- Preserves:
    * anchor fragments (#section)
    * external URLs (http/https/mailto)
    * headings and bullet structure

- Emits docs/SUMMARY.md that mkdocs-literate-nav can parse:
    # Home
    - index.md

    # Knowledge
    ## Rulebook
    <rewritten list>

    ## RAM 5
    <rewritten list>

    ## Organizational Handbook
    <rewritten list>

    # About
    - about.md

Notes
-----
- Only links inside upstream SUMMARY files are rewritten (pages themselves may still
  contain unrewritten relative links, which is fine for the nav; page content linking
  can be addressed later if required).
- The Markdown produced must contain *valid link syntax* [Label](rewritten_url), because
  mkdocs-literate-nav parses the nav from links inside lists and headings.

"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Repo layout
REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUT_FILE = DOCS_DIR / "SUMMARY.md"

# Fixed order for sections
ORDER = ["rulebook", "ram5", "handbook"]
TITLE_MAP = {
    "rulebook": "Rulebook",
    "ram5": "RAM 5",
    "handbook": "Organizational Handbook",
}

# Regex to capture Markdown links: [label](url)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def is_external(href: str) -> bool:
    """Return True if href is an absolute URL or mailto link."""
    return href.startswith(("http://", "https://", "mailto:"))

def normalize_and_join(src_root: Path, rel: str) -> Tuple[Path, str]:
    """
    Normalize a (possibly relative) path against src_root and split off an anchor.
    Returns (absolute_source_path, anchor_suffix) where anchor_suffix includes the leading '#'
    or '' if not present.
    """
    if "#" in rel:
        path_part, frag = rel.split("#", 1)
        anchor = "#" + frag
    else:
        path_part, anchor = rel, ""

    # Leave empty paths (e.g., just '#heading') to the caller to handle
    # Resolve against src_root (handles ./, ../, etc.)
    abs_path = (src_root / path_part).resolve()
    return abs_path, anchor

def rewrite_href(href: str, src_root: Path, section_key: str) -> str:
    """
    Rewrite a single href to the new docs/external/<section>/... location if it's relative.
    Preserve external links and pure anchors.
    """
    # Preserve external links and pure anchors
    if is_external(href) or href.startswith("#"):
        return href

    abs_path, anchor = normalize_and_join(src_root, href)

    # If the resolved path doesn't live under src_root (e.g., too many ../), keep as-is
    try:
        rel_in_source = abs_path.relative_to(src_root.resolve())
    except ValueError:
        return href  # outside of expected tree; do not rewrite

    # Build posix-style path for MkDocs
    new_path = posixpath.join("external", section_key, *rel_in_source.parts)
    return new_path + anchor

def rewrite_links_in_line(line: str, src_root: Path, section_key: str) -> str:
    """
    Rewrite all Markdown links in a line, but **preserve the label + Markdown syntax**.
    This is critical for mkdocs-literate-nav to parse the navigation.
    """
    def _sub(match: re.Match) -> str:
        label, url = match.group(1), match.group(2)
        new_url = rewrite_href(url, src_root, section_key)
        # Keep the Markdown link notation intact
        return f"[{label}]({new_url})"
    return LINK_RE.sub(_sub, line)

def process_upstream_summary(section_key: str, src_root: Path, summary_path: Path) -> str:
    """
    Read the upstream summary file, rewrite links, and return the resulting Markdown string.
    We do not alter headings or indentation; we only rewrite link destinations.
    """
    text = summary_path.read_text(encoding="utf-8")
    out_lines: List[str] = []
    for raw_line in text.splitlines():
        out_lines.append(rewrite_links_in_line(raw_line, src_root, section_key))
    # Ensure trailing newline so concatenations have spacing
    return "\n".join(out_lines).rstrip() + "\n"

def parse_triplets(args: Iterable[str]) -> Dict[str, Tuple[Path, Path]]:
    """
    Parse CLI args of the form key|src_root|summary_path into a dict:
        { key: (src_root_path, summary_path) }
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
    Compose the final SUMMARY.md content using the fixed section order.
    Missing sections are kept with a placeholder so the layout is deterministic.
    """
    parts: List[str] = []

    # Home
    parts.append("# Home\n")
    parts.append("- index.md\n")

    # Knowledge sections
    parts.append("\n# Knowledge\n")
    for key in ORDER:
        title = TITLE_MAP[key]
        parts.append(f"\n## {title}\n")
        if key in triplets:
            src_root, summ = triplets[key]
            parts.append(process_upstream_summary(key, src_root, summ))
        else:
            parts.append("\n- *(content not available)*\n")

    # About
    parts.append("\n# About\n")
    parts.append("- about.md\n")

    return "".join(parts)

def main() -> None:
    # Ensure docs directory exists
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse provided triplets
    triplets = parse_triplets(sys.argv[1:])

    # Build merged content
    merged = build_merged_summary(triplets)

    # Write output
    OUT_FILE.write_text(merged, encoding="utf-8")
    print(f"[INFO] Wrote merged SUMMARY to {OUT_FILE}")

if __name__ == "__main__":
    main()