"""Guard the offline shell's size budget, and that it can actually be cached.

The PWA's whole argument for hand-written CSS and vendored dependencies is a
small, instantly-cacheable shell. Adding a 53 KB font spends a real part of that
budget, so the budget stops being an intention and becomes a check.

    python scripts/check_shell_size.py
    python scripts/check_shell_size.py --budget 150000 --verbose

**The budget is on transfer size, not file size.** Caddy serves text compressed,
so 36 KB of HTML costs about 7 KB on the wire while 54 KB of woff2 costs 54 KB —
it is already compressed. Budgeting raw bytes would treat those as equal and push
you to trim markup while ignoring the thing that actually dominates the download.
gzip -9 is used as a conservative stand-in; brotli, which Caddy prefers, does
slightly better.

Raw totals are still reported, because Cache Storage holds decompressed bytes and
that is what the shell occupies on the user's device.

Two failure modes, both real:

  * the shell grows past the budget, one reasonable-looking asset at a time
  * an entry in SHELL does not exist on disk — `cache.addAll()` rejects on a
    single 404 and the whole install fails, so one typo means no client ever
    caches anything and offline support silently disappears
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SW = WEB / "sw.js"

# Current wire size is ~93 KB. 130 KB leaves room for a few real additions
# without leaving so much that a careless one goes unnoticed.
DEFAULT_BUDGET = 130_000

# Formats that are already compressed; gzipping them again gains nothing and
# would make the estimate optimistic rather than conservative.
PRECOMPRESSED = (".woff2", ".woff", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".gz")


def shell_entries(source: str) -> list[str]:
    match = re.search(r"const SHELL = \[(.*?)\];", source, re.DOTALL)
    if not match:
        raise SystemExit(f"could not find `const SHELL = [...]` in {SW.name}")
    return re.findall(r"'([^']+)'", match.group(1))


def wire_size(path: Path) -> tuple[int, int, bool]:
    """Returns (raw, transfer, was_compressed)."""
    data = path.read_bytes()
    if path.suffix.lower() in PRECOMPRESSED:
        return len(data), len(data), False
    return len(data), len(gzip.compress(data, 9)), True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="transfer bytes")
    parser.add_argument("--verbose", action="store_true", help="list every entry")
    args = parser.parse_args()

    source = SW.read_text(encoding="utf-8")
    entries = shell_entries(source)
    version = re.search(r"const VERSION = '([^']+)'", source)

    raw_total = 0
    wire_total = 0
    missing: list[str] = []
    rows: list[tuple[str, int, int, bool]] = []

    for entry in entries:
        # '/' and '/index.html' are the same document; count it once.
        relative = "index.html" if entry == "/" else entry.lstrip("/")
        path = WEB / relative
        if not path.is_file():
            missing.append(entry)
            continue
        raw, wire, compressed = wire_size(path)
        rows.append((entry, raw, wire, compressed))
        if entry != "/":  # avoid double-counting the shell document
            raw_total += raw
            wire_total += wire

    if args.verbose or missing:
        print(f"  {'raw':>8}  {'wire':>8}")
        for entry, raw, wire, compressed in sorted(rows, key=lambda r: -r[2]):
            note = ""
            if entry == "/":
                note = "  (same file as /index.html, not counted)"
            elif not compressed:
                note = "  (already compressed)"
            print(f"  {raw:>8,}  {wire:>8,}  {entry}{note}")
        print()

    share = ""
    font = next((w for e, _, w, _ in rows if "woff2" in e for w in [w]), 0)
    if font and wire_total:
        share = f", the font is {font / wire_total:.0%} of it"

    print(f"  transfer  {wire_total:>8,}  ({wire_total / args.budget:.0%} of budget{share})")
    print(f"  on device {raw_total:>8,}  (Cache Storage holds decompressed bytes)")
    print(f"  shell cache version: {version.group(1) if version else 'UNKNOWN'}")

    if missing:
        print(
            f"\nFAIL {len(missing)} SHELL entr(ies) do not exist:\n"
            + "\n".join(f"  {m}" for m in missing)
            + "\n\ncache.addAll() rejects if any single request 404s, so this would\n"
            "leave every client with no cached shell and no offline support.",
            file=sys.stderr,
        )
        return 1

    if wire_total > args.budget:
        print(
            f"\nFAIL shell transfers {wire_total:,} bytes, over the {args.budget:,} budget "
            f"by {wire_total - args.budget:,}.\nEither drop something or raise the budget "
            "deliberately, with a reason.",
            file=sys.stderr,
        )
        return 1

    print("\nOK   shell is within budget and every entry exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
