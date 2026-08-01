"""Build the web-ready images from the sources in `images/`.

The PWA has no build step, so `web/img/` holds checked-in binaries. A checked-in
binary nobody can regenerate is a liability, so this is the provenance — the same
arrangement as `scripts/build_font.py`.

    python scripts/build_images.py            # resize, convert, write
    python scripts/build_images.py --check    # verify the committed files match

Requires Pillow, which is dev-only:

    pip install pillow

WebP at quality 80 is roughly a 5x saving on the source JPEG at the sizes the app
actually displays. The originals stay in `images/` untouched; nothing reads them
at runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "images"
OUTPUT_DIR = ROOT / "web" / "img"

WEBP_QUALITY = 80


@dataclass(frozen=True, slots=True)
class Asset:
    source: str
    output: str
    size: int
    """Square edge in CSS pixels, before device pixel ratio."""

    note: str
    crop: tuple[int, int, int, int] | None = None
    """(left, top, right, bottom) in source pixels, applied before resizing."""


# Only what the app actually renders. Every entry here costs bytes a cold visitor
# may pay for, so adding one is a decision rather than a convenience.
ASSETS: tuple[Asset, ...] = (
    Asset(
        source="1kuooGk_.jpg",
        output="loaf-hero.webp",
        size=320,
        note="sign-in hero, displayed at 132px; 320 covers a 2x screen",
        # A centre crop of the full square puts the photograph's own horizon --
        # dark olive above, white below -- straight through the circular mask,
        # which reads as a badly cropped photo rather than a medallion. These
        # numbers are the loaf's measured bounding box (x 90-552, y 182-532)
        # squared off with 4% padding, so the circle is filled with bread.
        crop=(81, 117, 561, 597),
    ),
)


def build(asset: Asset) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dev tooling
        raise SystemExit("missing build dependency. Install with:\n    pip install pillow") from exc

    source = SOURCE_DIR / asset.source
    if not source.is_file():
        raise SystemExit(f"source missing: {source}")

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        if asset.crop:
            rgb = rgb.crop(asset.crop)
        # Resize through a square target so a non-square source is scaled rather
        # than silently letterboxed.
        resized = rgb.resize((asset.size, asset.size), Image.LANCZOS)
        buffer = io.BytesIO()
        # method=6 is the slowest, smallest setting. This runs once, by hand.
        resized.save(buffer, "WEBP", quality=WEBP_QUALITY, method=6)
        return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild and compare against the committed files instead of writing them.",
    )
    args = parser.parse_args()

    failures = 0
    total = 0

    for asset in ASSETS:
        built = build(asset)
        total += len(built)
        target = OUTPUT_DIR / asset.output
        digest = hashlib.sha256(built).hexdigest()[:16]

        if args.check:
            if not target.is_file():
                print(f"FAIL {asset.output} does not exist", file=sys.stderr)
                failures += 1
                continue
            if target.read_bytes() != built:
                print(
                    f"FAIL {asset.output} differs from a fresh build\n"
                    f"     committed {target.stat().st_size:,} bytes\n"
                    f"     rebuilt   {len(built):,} bytes  sha256 {digest}\n"
                    "     Re-run without --check, and bump VERSION in web/sw.js.",
                    file=sys.stderr,
                )
                failures += 1
                continue
            print(f"OK   {asset.output:<20} {len(built):>7,} bytes")
        else:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            target.write_bytes(built)
            print(f"--> {asset.output:<20} {len(built):>7,} bytes  sha256 {digest}  {asset.note}")

    print(f"\n     {total:>7,} bytes total")

    if failures:
        return 1
    if not args.check:
        print()
        print("These are lazily loaded, not part of the service worker SHELL: a sign-in")
        print("illustration is not what a cold visitor needs before the app renders.")
        print("Bump VERSION in web/sw.js anyway - index.html changed alongside them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
