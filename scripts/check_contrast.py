"""Fail if any colour pair the web app actually renders drops below WCAG AA.

The palette was audited once by hand and three pairs failed, one of them badly
(white on amber in dark mode, at 2.15:1 — below even the 3.0 large-text floor).
An audit you run once is a fact about the past, so this is the same computation
wired to an exit code.

    python scripts/check_contrast.py
    python scripts/check_contrast.py --verbose     # show passing pairs too

Values are parsed out of web/css/app.css rather than duplicated here. A token
renamed in the stylesheet and not here is a hard error, not a silent skip.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "web" / "css" / "app.css"

AA_NORMAL = 4.5
AA_LARGE = 3.0

# (foreground, background, where it renders, is the text large?)
# "Large" is 18.66px bold or 24px+ — only the countdown and the display figures
# qualify, and both are checked at the normal threshold anyway since they sit on
# the same grounds as body text.
PAIRS: list[tuple[str, str, str, bool]] = [
    ("text", "bg", "body copy", False),
    ("text", "surface", "text on a card", False),
    ("text", "surface-2", "text on a secondary button", False),
    ("muted", "bg", ".sub beneath the page", False),
    ("muted", "surface", ".sub inside a card", False),
    ("muted", "surface-2", ".pill default, sidebar hover", False),
    ("accent", "bg", "accent text on the page", False),
    ("accent", "surface", "accent text on a card", False),
    ("accent-deep", "accent-soft", ".pill.accent, active nav item", False),
    ("on-accent", "accent", "button.primary label", False),
    ("ok", "surface", ".pill.ok, ready countdown", False),
    ("warn", "surface", ".banner.offline", False),
    ("bad", "surface", ".pill.overdue, danger button", False),
    ("ok", "bg", "ready countdown on the page", False),
    ("bad", "bg", "danger text on the page", False),
]


def relative_luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def parse_themes(css: str) -> dict[str, dict[str, str]]:
    """Pull the two token blocks out of the stylesheet.

    Light comes from the `:root, :root[data-theme='light']` block and dark from
    `:root[data-theme='dark']`. The dark @media block is deliberately not parsed:
    it must be identical to the data-theme one, which is asserted separately —
    checking both would just report the same failure twice.
    """
    themes: dict[str, dict[str, str]] = {}
    for name, pattern in (
        ("light", r":root,\s*:root\[data-theme='light'\]\s*\{(.*?)\}"),
        ("dark", r":root\[data-theme='dark'\]\s*\{(.*?)\}"),
    ):
        match = re.search(pattern, css, re.DOTALL)
        if not match:
            raise SystemExit(f"could not find the {name} token block in {CSS.name}")
        themes[name] = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})", match.group(1)))
    return themes


def check_media_matches_attribute(css: str, dark: dict[str, str]) -> list[str]:
    """The OS-preference block and the explicit dark block must agree.

    They are two copies of one palette. If they drift, the theme toggle silently
    shows different colours than the device preference does.
    """
    match = re.search(
        r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.DOTALL
    )
    if not match:
        return ["no @media (prefers-color-scheme: dark) block found"]
    media = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})", match.group(1)))
    problems = []
    for token in sorted(set(media) | set(dark)):
        if media.get(token) != dark.get(token):
            problems.append(
                f"--{token}: @media says {media.get(token, 'unset')}, "
                f"[data-theme=dark] says {dark.get(token, 'unset')}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print passing pairs too.")
    args = parser.parse_args()

    css = CSS.read_text(encoding="utf-8")
    themes = parse_themes(css)

    failures: list[str] = []
    for theme, tokens in themes.items():
        print(f"\n{theme.upper()}")
        for fg, bg, where, large in PAIRS:
            if fg not in tokens or bg not in tokens:
                failures.append(f"{theme}: --{fg} or --{bg} is not defined")
                print(f"  MISSING  --{fg} on --{bg}")
                continue
            value = ratio(tokens[fg], tokens[bg])
            floor = AA_LARGE if large else AA_NORMAL
            ok = value >= floor
            if ok and not args.verbose:
                continue
            marker = "ok  " if ok else "FAIL"
            print(f"  {marker} {value:5.2f}  --{fg} on --{bg:<12} {where}")
            if not ok:
                failures.append(
                    f"{theme}: --{fg} on --{bg} is {value:.2f}, needs {floor} ({where})"
                )

    drift = check_media_matches_attribute(css, themes["dark"])

    print()
    if drift:
        print("Dark palette is defined twice and the copies disagree:")
        for problem in drift:
            print(f"  {problem}")
    if failures:
        print(f"{len(failures)} contrast failure(s):")
        for failure in failures:
            print(f"  {failure}")
    if failures or drift:
        return 1

    checked = len(PAIRS) * len(themes)
    print(f"All {checked} pairs pass WCAG AA, and both dark definitions agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
