#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from datetime import datetime, timezone

# Match Markdown links: [label](path)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Match list items like: * path.md
PLAIN_ITEM_RE = re.compile(r"^\s*[*-]\s+(.+)$")

def extract_md_paths_from_summary(summary_text: str) -> list[str]:
    """Extract .md paths from a literate-nav SUMMARY list, preserving order and de-duplicating."""
    candidates: list[str] = []

    for line in summary_text.splitlines():
        # Any explicit markdown link
        for m in MD_LINK_RE.finditer(line):
            href = m.group(2).strip()
            path = href.split("#", 1)[0]
            if path.lower().endswith(".md"):
                candidates.append(path)

        # Path-only items (in case contributors use them)
        m2 = PLAIN_ITEM_RE.match(line)
        if m2:
            token = m2.group(1).strip()
            token_path = token.split("#", 1)[0]
            if token_path.lower().endswith(".md"):
                candidates.append(token_path)

    # De-dup preserving order
    seen = set()
    out: list[str] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def list_all_md_files(docs_dir: Path) -> list[Path]:
    """All markdown files under docs, sorted for stable append order."""
    files = [p for p in docs_dir.rglob("*.md") if p.is_file()]
    return sorted(files, key=lambda p: p.as_posix().lower())

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs-dir", default="docs")
    ap.add_argument("--summary", default="docs/SUMMARY.md")
    ap.add_argument("--out", default="exports/knowledge-base.md")
    ap.add_argument("--title", default="Knowledge Base")
    ap.add_argument("--version", required=True)
    args = ap.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    summary_path = Path(args.summary).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary_text = summary_path.read_text(encoding="utf-8", errors="ignore")
    ordered_rel_paths = extract_md_paths_from_summary(summary_text)

    ordered_files: list[Path] = []
    seen: set[Path] = set()

    # 1) Add files in SUMMARY order
    for rel in ordered_rel_paths:
        p = (docs_dir / rel).resolve()
        if p.exists() and p.is_file() and p.suffix.lower() == ".md":
            if p not in seen:
                ordered_files.append(p)
                seen.add(p)

    # 2) Add remaining markdown files (scope = ALL)
    for p in list_all_md_files(docs_dir):
        # Skip the nav file itself and any external summary files
        rel = p.relative_to(docs_dir).as_posix().lower()
        if rel == "summary.md":
            continue
        if rel.startswith("external/") and rel.endswith("/summary.md"):
            continue
        if p not in seen:
            ordered_files.append(p)
            seen.add(p)

    # 3) Write a single book markdown
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts: list[str] = []
    parts.append("---")
    parts.append(f"title: \"{args.title}\"")
    parts.append(f"date: \"{now}\"")
    parts.append(f"version: \"{args.version}\"")
    parts.append("---")
    parts.append("")
    parts.append(f"# {args.title}")
    parts.append("")
    parts.append(f"**Version:** {args.version}  ")
    parts.append(f"**Generated:** {now}")
    parts.append("")
    parts.append("---")
    parts.append("")

    for p in ordered_files:
        rel = p.relative_to(docs_dir).as_posix()
        # Section marker for readability in exports
        parts.append(f"\n\n# {rel}\n")
        parts.append(p.read_text(encoding="utf-8", errors="ignore"))
        parts.append("\n\n---\n")

    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"[INFO] Wrote export book: {out_path}")

if __name__ == "__main__":
    main()