# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Small building blocks shared by the pages."""
from pathlib import Path

from gi.repository import Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango


class Picture(Gtk.Widget):
    """A picture shown at a fixed width. The full-size image is kept and scaled while drawing, so it stays
    sharp on high-density screens instead of being shrunk to the logical size first. Taller pictures are
    cropped to max_height around their middle."""

    def __init__(self, texture: Gdk.Texture, width: int, max_height: int):
        super().__init__()
        self.texture = texture
        self.w = width
        self.full_h = max(1, round(width * texture.get_height() / max(1, texture.get_width())))
        self.h = min(self.full_h, max_height)
        self.set_halign(Gtk.Align.CENTER)
        self.set_overflow(Gtk.Overflow.HIDDEN)

    def do_measure(self, orientation, for_size):
        n = self.w if orientation == Gtk.Orientation.HORIZONTAL else self.h
        return n, n, -1, -1

    def do_snapshot(self, snapshot):
        rect = Graphene.Rect().init(0, -(self.full_h - self.h) / 2, self.w, self.full_h)
        snapshot.append_scaled_texture(self.texture, Gsk.ScalingFilter.TRILINEAR, rect)


def load_picture(path: Path, width: int, max_height: int):
    """A Picture for the image file at path, or None if it cannot be read."""
    try:
        return Picture(Gdk.Texture.new_from_filename(str(path)), width, max_height)
    except GLib.Error:
        return None


def button(label, on_click, kind=None, tooltip=None):
    b = Gtk.Button(label=label)
    b.add_css_class("cpbtn")
    for k in (kind or "").split():
        b.add_css_class(k)
    if tooltip:
        b.set_tooltip_text(tooltip)
    b.connect("clicked", on_click)
    return b


def label(text="", *classes, wrap=False, selectable=False, **props):
    lab = Gtk.Label(label=text, xalign=0, selectable=selectable, **props)
    if wrap:
        lab.set_wrap(True)
        lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lab.set_max_width_chars(60)
    for c in classes:
        lab.add_css_class(c)
    return lab


def section(text):
    return label(text.upper(), "section")


def badge(text, kind=""):
    lab = Gtk.Label(label=text, valign=Gtk.Align.CENTER)
    lab.add_css_class("badge")
    if kind:
        lab.add_css_class(kind)
    return lab


def empty_row(text):
    """A row that only says the list is empty. It cannot be selected; its `mod` and `path` are None."""
    row = Gtk.ListBoxRow(selectable=False, activatable=False)
    row.mod = row.path = None
    lab = label(text, "dim")
    lab.set_xalign(0.5)
    lab.set_margin_top(18)
    lab.set_margin_bottom(18)
    row.set_child(lab)
    return row


def clear(box):
    child = box.get_first_child()
    while child:
        box.remove(child)
        child = box.get_first_child()


def choose(parent, title, detail, buttons, then):
    """Ask a question with several answers; then(index) gets the pressed button, index 0 is always Cancel."""
    d = Gtk.AlertDialog(message=title, detail=detail, buttons=buttons, cancel_button=0, default_button=0, modal=True)

    def cb(dlg, res):
        try:
            i = dlg.choose_finish(res)
        except GLib.Error:
            return
        if i > 0:
            then(i)
    d.choose(parent, None, cb)


def pick_folder(parent, title, start: Path, then):
    d = Gtk.FileDialog(title=title, modal=True)
    d.set_initial_folder(Gio.File.new_for_path(str(start if start and Path(start).is_dir() else Path.home())))

    def cb(dlg, res):
        try:
            chosen = dlg.select_folder_finish(res)
        except GLib.Error:
            return
        then(Path(chosen.get_path()))
    d.select_folder(parent, None, cb)


def pick_file(parent, title, start: Path, then, suffixes=None, pictures=False):
    d = Gtk.FileDialog(title=title, modal=True)
    f = Gtk.FileFilter()
    filters = Gio.ListStore.new(Gtk.FileFilter)
    if pictures:
        f.set_name("Pictures")
        f.add_pixbuf_formats()
    else:
        f.set_name("Mod archives (zip, 7z, rar)")
        for ext in suffixes or ():
            f.add_suffix(ext.lstrip("."))
    filters.append(f)
    every = Gtk.FileFilter()
    every.set_name("All files")
    every.add_pattern("*")
    filters.append(every)
    d.set_filters(filters)
    d.set_default_filter(f)
    if start:
        d.set_initial_folder(Gio.File.new_for_path(str(start if Path(start).is_dir() else Path.home())))

    def cb(dlg, res):
        try:
            chosen = dlg.open_finish(res)
        except GLib.Error:
            return
        then(Path(chosen.get_path()))
    d.open(parent, None, cb)
