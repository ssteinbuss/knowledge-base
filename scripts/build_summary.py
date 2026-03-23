#!/usr/bin/env python3
"""
Build a merged docs/SUMMARY.md for mkdocs-literate-nav from three upstream summaries.

- Order: Rulebook -> RAM 5 -> Organizational Handbook
- Rewrites relative links to docs/external/{rulebook|ram5|handbook}/...
- Preserves anchors (#...) and external URLs
- Keeps Markdown link syntax [label](url)
- Converts plain-path bullets into proper links with auto labels
- Leaves wildcard bullets (*.md) as bullets (with rewritten prefix)

Usage (called by sync_external_content.py):
  python scripts/build_summary.py \
    rulebook|<src>/documentation|<src>/documentation/SUMMARY.md \
    ram5|<src>/docs|<src>/docs/SUMMARY.md \
    handbook|<src>/OrganizationalHandbook|<src>/OrganizationalHandbook/SUMMARY.md
"""

from __future__ import annotations

import re
import posixpath
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

# Markdown link: [label](url)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Bullet list item: captures leading marker/indent + content
LIST_ITEM_RE = re.compile(r"^(\s*[-*]\s+)(.+?)\s*$")
# Any wildcard asterisk in the token
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
        # Escapes src_root; best-effort: leave unchanged
        return href

    new_path = posixpath.join("external", section_key, *rel_in_source.parts)
    return new_path + anchor

def filename_to_label(path: str) -> str:
    """Generate a readable label from a file path/anchor."""
    p, _ = split_anchor(path)
    seg = Path(p).stem or "Untitled"
    # Special cases
    if seg.lower() in {"readme", "index"}:
        parent = Path(p).parent.name
        seg = parent if parent else "Home"
    seg = seg.replace("-", " ").replace("_", " ").strip()
    # Title-case words unless they are already ALLCAPS (e.g., RAM)
    return " ".join(w if w.isupper() else w.capitalize() for w in seg.split()) or "Untitled"

def rewrite_links_in_line(line: str, src_root: Path, section_key: str) -> str:
    """
    - Rewrites Markdown links while preserving label+syntax.
    - Converts plain-path bullets into Markdown links.
    - Leaves wildcard bullets as bullets (rewriting their prefix only).
    """

    # 1) Rewrite explicit Markdown links
    def _sub(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        new_url = rewrite_href(url, src_root, section_key)
        return f"[{label}]({new_url})"
    line2 = MD_LINK_RE.sub(_sub, line)

    # 2) Normalize list items that are plain paths or wildcards
    m = LIST_ITEM_RE.match(line2)
    if not m:
        return line2

    lead, content = m.group(1), m.group(2)

    # If already contains a Markdown link (after step 1), keep as-is
    if MD_LINK_RE.search(content):
        return line2

    # Wildcards (*.md or subdir/*.md) – rewrite path prefix only
    if HAS_WILDCARD_RE.search(content) and not is_external(content) and not content.startswith("#"):
        prefix, anchor = split_anchor(content)
        parts = Path(prefix).parts  # keep directory structure; literate-nav will expand wildcard
        new_token = posixpath.join("external", section_key, *parts) + anchor
        return f"{lead}{new_token}"

    # Plain Markdown file path -> convert to a proper link with generated label
    if re.search(r"\.(md|markdown)(#[A-Za-z0-9._\-]+)?$", content, flags=re.IGNORECASE):
        new_url = rewrite_href(content, src_root, section_key)
        label = filename_to_label(content)
        return f"{lead}[{label}]({new_url})"

    # Otherwise it might be a section title bullet – leave unchanged
    return line2

def process_upstream_summary(section_key: str, src_root: Path, summary_path: Path) -> str:
    text = summary_path.read_text(encoding="utf-8")
    out: List[str] = []
    for raw_line in text.splitlines():
        out.append(rewrite_links_in_line(raw_line, src_root, section_key))
    return "\n".join(out).rstrip() + "\n"

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
    parts: List[str] = []

    # Home
    parts.append("# Home\n")
    parts.append("- index.md\n")

    # Knowledge
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
    parts.append("- about.md\n")

    return "".join(parts)

def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    triplets = parse_triplets(sys.argv[1:])
    merged = build_merged_summary(triplets)
    OUT_FILE.write_text(merged, encoding="utf-8")
    print(f"[INFO] Wrote merged SUMMARY to {OUT_FILE}")

if __name__ == "__main__":
    main()