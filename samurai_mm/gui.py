# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Start the window: `python -m samurai_mm.gui`. The window itself lives in samurai_mm/ui/."""
import sys

from .ui.window import main

if __name__ == "__main__":
    sys.exit(main())
