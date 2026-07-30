"""Build the vendored Inter subset the web app ships.

The PWA has no CDN and no build step, so the font is a checked-in binary. A
checked-in binary nobody can regenerate is a liability, so this script is the
provenance: run it and you get byte-comparable output, or a clear error saying
why not.

    python scripts/build_font.py            # download, subset, write
    python scripts/build_font.py --check     # verify the committed file matches

Requires `fonttools` and `brotli`, which are dev-only:

    pip install fonttools brotli

Neither ever enters the runtime image — the output is 53 KB of woff2 and the
tools that made it stay on the machine that made it.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path

# Inter v4 variable, upstream. Pinned by URL rather than by version string
# because rsms.me serves the current release at a stable path; --check catches
# it if that ever silently changes underneath us.
SOURCE_URL = "https://rsms.me/inter/font-files/InterVariable.woff2"
OUTPUT = Path(__file__).resolve().parent.parent / "web" / "vendor" / "inter-4.1-latin.woff2"

# Latin-1 plus the specific non-ASCII characters the app actually renders.
# Everything here earns its place:
#   2013/2014  en and em dash — used in every empty state and hint
#   2018/2019/201C/201D  curly quotes
#   2026  the ellipsis in truncated text
#   00B7   the middle dot separating metadata ("rye · 1:5:5 · every 24 h")
#   2022   bullet
#   00D7   the multiplication sign, as in a vigour of "1.12x"
#   2192   right arrow, used in fork lineage
#   2605/2606  filled and hollow star, recipe rating
UNICODES = ",".join(
    [
        "U+0000-00FF",
        "U+2013",
        "U+2014",
        "U+2018",
        "U+2019",
        "U+201C",
        "U+201D",
        "U+2026",
        "U+00B7",
        "U+2022",
        "U+00D7",
        "U+2192",
        "U+2605",
        "U+2606",
    ]
)

# kern and liga are table stakes. calt drives Inter's contextual alternates.
# tnum is the one that matters most here: the proofing countdown reflows every
# second, and without tabular figures the digits jitter as they change.
LAYOUT_FEATURES = "kern,liga,calt,tnum"


def fetch() -> bytes:
    print(f"--> downloading {SOURCE_URL}")
    # An explicit User-Agent is required: the CDN answers 403 to urllib's
    # default ("Python-urllib/3.x"), which reads as a broken download rather
    # than a rejected one if you don't set it.
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "sourdough-tracker-build-font/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    print(f"    {len(data):,} bytes")
    return data


def subset(source: bytes) -> bytes:
    try:
        import brotli  # noqa: F401
        from fontTools import subset as ft_subset  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dev tooling
        raise SystemExit(
            f"missing build dependency ({exc.name}). Install with:\n"
            "    pip install fonttools brotli"
        ) from exc

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source.woff2"
        dst = Path(tmp) / "subset.woff2"
        src.write_bytes(source)

        print("--> subsetting")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "fontTools.subset",
                str(src),
                f"--output-file={dst}",
                "--flavor=woff2",
                f"--layout-features={LAYOUT_FEATURES}",
                f"--unicodes={UNICODES}",
                "--no-hinting",
                "--desubroutinize",
            ],
            check=True,
            capture_output=True,
        )
        return dst.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild and compare against the committed file instead of writing it.",
    )
    args = parser.parse_args()

    built = subset(fetch())
    digest = hashlib.sha256(built).hexdigest()

    if args.check:
        if not OUTPUT.exists():
            print(f"FAIL {OUTPUT} does not exist", file=sys.stderr)
            return 1
        current = OUTPUT.read_bytes()
        current_digest = hashlib.sha256(current).hexdigest()
        if current == built:
            print(f"OK   {OUTPUT.name} matches a fresh build ({len(built):,} bytes)")
            return 0
        print(
            f"FAIL {OUTPUT.name} differs from a fresh build\n"
            f"     committed {len(current):,} bytes  sha256 {current_digest[:16]}\n"
            f"     rebuilt   {len(built):,} bytes  sha256 {digest[:16]}\n"
            "     Upstream Inter may have been updated. Re-run without --check and\n"
            "     bump VERSION in web/sw.js so clients actually fetch it.",
            file=sys.stderr,
        )
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(built)
    print(f"--> wrote {OUTPUT}")
    print(f"    {len(built):,} bytes  sha256 {digest[:16]}")
    print()
    print("Remember to bump VERSION in web/sw.js: the shell cache does not")
    print("invalidate itself, and a redesign nobody fetches is a redesign nobody sees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
