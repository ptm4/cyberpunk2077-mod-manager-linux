# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Rebuilds the mascot pictures from tux.svg and the gear drawn in mascot.py.

    python3 dev/artwork/build.py [EXTRAS_FOLDER]

Needs only rsvg-convert (librsvg). Writes:
    samurai_mm/data/banner.png   the side picture in the window (640 x 720, shown at half that size)
    samurai_mm/data/icon.png     the app icon (512 x 512)
    docs/mascot.png              a large version for the README and for download pages
With EXTRAS_FOLDER it also writes files that are not part of the project: the mascot as one scalable SVG,
a large transparent cut-out, and a 1024-pixel icon.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import mascot  # noqa: E402


def render(svg_text, out: Path, tmp: Path):
    src = tmp / (out.stem + ".svg")
    src.write_text(svg_text)
    subprocess.run(["rsvg-convert", str(src), "-o", str(out)], check=True)
    print("wrote", out.relative_to(ROOT) if out.is_relative_to(ROOT) else out)


def main(extras=None):
    base = mascot.vector_base(HERE / "tux.svg")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        render(mascot.banner(base), ROOT / "samurai_mm" / "data" / "banner.png", tmp)
        render(mascot.icon(base), ROOT / "samurai_mm" / "data" / "icon.png", tmp)
        render(mascot.banner(base, 960, 1080), ROOT / "docs" / "mascot.png", tmp)
        if extras:
            extra = Path(extras)
            extra.mkdir(parents=True, exist_ok=True)
            (extra / "mascot.svg").write_text(mascot.banner(base, 960, 1080))
            (extra / "mascot-transparent.svg").write_text(mascot.cutout(base, 4))
            render(mascot.cutout(base, 8), extra / "mascot-transparent.png", tmp)
            render(mascot.icon(base, 1024), extra / "icon-1024.png", tmp)
            print("wrote", extra / "mascot.svg", "and", extra / "mascot-transparent.svg")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
