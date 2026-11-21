# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""The window, in small parts: style, runner, widgets, variants, picker, setup, pages, window."""
try:
    import gi

    # Asked for here, once, so the modules of this package can be imported in any order.
    for _name, _version in (("Gtk", "4.0"), ("Gdk", "4.0"), ("Gsk", "4.0"), ("Graphene", "1.0")):
        gi.require_version(_name, _version)
except (ImportError, ValueError):
    pass      # no GTK 4 here: variants.py still works without it, and the window says what is missing when started
