# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""The four tabs. Each page builds its own widgets, asks the window to run engine commands,
and redraws itself in update() from the state the window keeps (status, mods, health)."""
import time
from pathlib import Path

from gi.repository import Gio, GLib, Gtk, Pango

from .. import NOTICE, engine
from . import widgets
from .picker import Picker

ARCHIVE_EXT = {".zip", ".7z", ".rar"}
PICK_TRIGGERS = ("ships an installer with choices", "cannot tell where this mod's files go")
NEXUS_URL = "https://www.nexusmods.com/" + engine.NEXUS_GAME + "/mods/{}"
SORT_CHOICES = (("name", "Name (A to Z)"), ("recent", "Recently installed"), ("size", "Biggest first"), ("off", "Switched off first"))


class ModsPage(Gtk.Box):
    """The list of mods, each with an on/off switch."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win = win
        self.switches = []
        top = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text="Filter by name", hexpand=True)
        self.search.connect("search-changed", lambda *_: self.list.invalidate_filter())
        top.append(self.search)
        top.append(widgets.label("Sort", "dim", "small"))
        self.sort = Gtk.DropDown.new_from_strings([label for _, label in SORT_CHOICES])
        self.sort.set_tooltip_text("The order of the list. It is remembered.")
        keys = [k for k, _ in SORT_CHOICES]
        self.sort.set_selected(keys.index(win.cfg.get("sort")) if win.cfg.get("sort") in keys else 0)
        self.sort.connect("notify::selected", self.on_sort)
        top.append(self.sort)
        self.append(top)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("modlist")
        self.list.set_filter_func(lambda r: r.mod is None or self.search.get_text().lower() in r.mod["name"].lower())
        self.list.connect("row-selected", lambda *_: win.update_sensitivity())
        self.list.connect("row-activated", lambda *_: self.show_files())
        sc.set_child(self.list)
        self.append(sc)
        row = Gtk.Box(spacing=8)
        hint = widgets.label("The switch takes a mod out of the game without deleting it. Double-click a mod to list its files.",
                             "dim", "small")
        hint.set_hexpand(True)
        hint.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(hint)
        row.append(win.action(widgets.button("Remove", self.remove, "danger",
                                             "Take the selected mod out of the game and out of the list; its folder is kept under removed/"),
                              modifies=True, cond=lambda: self.selected() is not None))
        self.append(row)

    def selected(self):
        row = self.list.get_selected_row()
        return row.mod if row else None

    def sort_key(self):
        return SORT_CHOICES[self.sort.get_selected()][0]

    def on_sort(self, *_):
        self.win.cfg["sort"] = self.sort_key()
        engine.save_config(self.win.cfg)
        self.update()

    def sorted_mods(self):
        how = self.sort_key()
        if how == "off":       # switched-off mods first, then the rest, each group A to Z
            return sorted(engine.sort_rows(self.win.mods), key=lambda m: m["state"] != "disabled")
        return engine.sort_rows(self.win.mods, how)

    def set_switches_sensitive(self, ok):
        for sw in self.switches:
            sw.set_sensitive(ok)

    def update(self):
        keep = self.selected()["name"] if self.selected() else None
        self.list.remove_all()
        self.switches = []
        if not self.win.mods:
            self.list.append(widgets.empty_row("No mods yet. Use the Install tab to add one."))
        recent = self.sort_key() == "recent"
        for m in self.sorted_mods():
            row = Gtk.ListBoxRow()
            row.mod = m
            box = Gtk.Box(spacing=10)
            sw = Gtk.Switch(active=m["state"] != "disabled", valign=Gtk.Align.CENTER)
            sw.set_tooltip_text("On: the mod is part of the game. Off: kept in the store, taken out of the game.")
            sw.connect("state-set", self.on_switch, m["name"])
            self.switches.append(sw)
            box.append(sw)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            title = widgets.label(m["title"], ellipsize=Pango.EllipsizeMode.END)
            title.set_tooltip_text(m["name"])
            text.append(title)
            bits = ([f"version {m['version']}"] if m.get("version") else []) + [f"{m['files']} files", engine.human_size(m["size"])]
            if recent and m.get("added"):
                bits.append("installed " + time.strftime("%Y-%m-%d", time.localtime(m["added"])))
            text.append(widgets.label("   ".join(bits), "dim", "small"))
            box.append(text)
            if m.get("nexus_id"):
                b = widgets.button("Nexus page", lambda _b, i=m["nexus_id"]: Gio.AppInfo.launch_default_for_uri(NEXUS_URL.format(i), None),
                                   "tiny", "Open this mod's page on Nexus Mods, for example to look for an update")
                b.set_valign(Gtk.Align.CENTER)
                box.append(b)
            text_, kind = {"deployed": ("in game", "good"), "partial": ("partly in game", "warn"),
                           "not in game": ("not in game", "warn"), "disabled": ("off", "")}[m["state"]]
            box.append(widgets.badge(text_, kind))
            row.set_child(box)
            self.list.append(row)
            if m["name"] == keep:
                self.list.select_row(row)

    def on_switch(self, sw, wanted, name):
        if self.win.busy or self.win.game_is_running:
            return True   # refuse the change; the list is rebuilt from the real state anyway
        self.win.run(["enable" if wanted else "disable", "--", name], modifies=True)
        return False

    def show_files(self):
        if self.selected():
            self.win.run(["info", "--", self.selected()["name"]])

    def remove(self, *_):
        m = self.selected()
        if not m:
            return
        self.win.confirm(f"Remove \"{m['title']}\"?",
                         f"Its {m['files']} files are taken out of the game folder and the mod leaves the list. "
                         "The mod's folder is kept under removed/ in the store, not deleted. "
                         "To only switch it off for now, use its switch instead.",
                         "Remove", lambda: self.win.run(["remove", "--", m["name"]], modifies=True))


class InstallPage(Gtk.Box):
    """Pick a download, look at what it would do, install it."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win = win
        self.source = None
        self.monitor = None
        self.rescan_timer = 0
        row = Gtk.Box(spacing=8)
        row.append(widgets.section("Your downloads"))
        self.scan_label = widgets.label("", "path", ellipsize=Pango.EllipsizeMode.START)
        self.scan_label.set_hexpand(True)
        self.scan_label.set_tooltip_text("Change this folder on the Settings tab")
        row.append(self.scan_label)
        self.append(row)

        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=110)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("modlist")
        self.list.connect("row-selected", lambda _l, r: r is not None and r.path is not None and self.set_source(r.path))
        self.list.connect("row-activated", lambda *_: self.add(True))
        sc.set_child(self.list)
        self.append(sc)

        row = Gtk.Box(spacing=8)
        row.append(widgets.button("Browse", lambda *_: widgets.pick_file(win, "Choose a mod archive", win.scan_dir, self.browsed, ARCHIVE_EXT),
                                  tooltip="Pick a zip, 7z or rar from anywhere"))
        row.append(widgets.button("Folder", lambda *_: widgets.pick_folder(win, "Choose an unpacked mod folder", win.scan_dir, self.browsed),
                                  tooltip="Pick a mod that is already unpacked into a folder"))
        self.source_label = widgets.label("", "path", ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.source_label.set_hexpand(True)
        row.append(self.source_label)
        ready = lambda: self.source is not None and win.has_store()  # noqa: E731
        row.append(win.action(widgets.button("Dry run", lambda *_: self.add(True), None,
                                             "Show what would be installed, without changing anything"), cond=ready))
        row.append(win.action(widgets.button("Install", lambda *_: self.add(False), "primary",
                                             "Add the mod, put it in the game and verify the files"), modifies=True, cond=ready))
        self.append(row)
        self.set_source(None)

    # ---- the downloads folder

    def watch(self, path: Path):
        self.scan_label.set_label(str(path))
        if self.monitor:
            self.monitor.cancel()
        try:
            self.monitor = Gio.File.new_for_path(str(path)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect("changed", self.on_dir_changed)
        except GLib.Error:
            self.monitor = None
        self.update()

    def on_dir_changed(self, *_):
        if self.rescan_timer:
            GLib.source_remove(self.rescan_timer)

        def fire():
            self.rescan_timer = 0
            self.update()
            self.win.health_page.update()      # a step waiting for this download can light up
            return False
        self.rescan_timer = GLib.timeout_add(700, fire)

    def update(self):
        if self.source is not None and not self.source.exists():
            self.set_source(None)       # the chosen download was moved or deleted meanwhile
        keep = self.source
        self.list.remove_all()
        try:
            found = [p for p in self.win.scan_dir.iterdir() if p.is_file() and p.suffix.lower() in ARCHIVE_EXT]
        except OSError:
            found = []
        if not found:
            self.list.append(widgets.empty_row("No zip, 7z or rar files in this folder yet. Download a mod, or use Browse."))
        installed = {m["name"].lower() for m in self.win.mods}
        for p in sorted(found, key=lambda p: p.stat().st_mtime, reverse=True):
            st = p.stat()
            row = Gtk.ListBoxRow()
            row.path = p
            box = Gtk.Box(spacing=10)
            name = widgets.label(p.name, ellipsize=Pango.EllipsizeMode.MIDDLE)
            name.set_hexpand(True)
            box.append(name)
            if p.stem.lower() in installed:
                box.append(widgets.badge("installed", "good"))
            box.append(widgets.label(f"{engine.human_size(st.st_size)}   {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}",
                                     "dim", "small"))
            row.set_child(box)
            self.list.append(row)
            if keep == p:
                self.list.select_row(row)

    # ---- what to install

    def set_source(self, path):
        self.source = Path(path) if path else None
        if self.source:
            self.source_label.set_label(f"{'Folder' if self.source.is_dir() else 'Archive'}: {self.source}")
        else:
            self.source_label.set_label("Pick a download above, browse, or drop a file on the window.")
        self.win.update_sensitivity()

    def browsed(self, path: Path):
        self.list.unselect_all()
        self.set_source(path)

    def add(self, dry):
        win = self.win
        if self.source is None or win.busy or not win.has_store() or (not dry and win.game_is_running):
            return
        src = self.source
        stem = src.name if src.is_dir() else src.stem
        info = engine.parse_mod_name(stem)
        on = [m for m in win.mods if m["state"] != "disabled"]
        same = [m for m in on if m["name"] == stem]
        related = [m for m in on if info["nexus_id"] and m.get("nexus_id") == info["nexus_id"] and m["name"] != stem][:3]

        def go(flags):
            args = ["add"] + flags + (["--dry-run"] if dry else []) + ["--", str(src)]

            def done(code, lines):
                if code != 0 and any(t in "\n".join(lines) for t in PICK_TRIGGERS):
                    win.out("This download needs a choice before it can be installed. Opening the chooser.", "note")
                    Picker(win, src, stem, flags).present()
            win.run(args, done, modifies=not dry)

        if same:
            win.choose("Already installed",
                       f"\"{info['title']}\" is already in your mods, from this same download. Install it again over the existing one?",
                       ["Cancel", "Reinstall"], lambda i: go(["--replace"]))
        elif related:
            def answer(i):
                go([] if i == 1 else ["--update=" + related[i - 2]["name"]])
            win.choose("Update or add?",
                       f"\"{info['title']}\" (version {info['version']}) is from the same Nexus page as a mod you already have. "
                       "Updating replaces the old version. Adding keeps both, which is right for optional files and patches.",
                       ["Cancel", "Add as a separate mod"] +
                       [f"Update {m['title']} {m.get('version') or ''}".strip() for m in related], answer)
        else:
            go([])


class HealthPage(Gtk.Box):
    """One button that checks everything, and a card per result. A card for something that is not right lists what
    to do about it as numbered steps, with a button wherever the manager can do the step or take you to it."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win = win
        row = Gtk.Box(spacing=8)
        self.hint = widgets.label("", "dim", "small", wrap=True)
        self.hint.set_hexpand(True)
        row.append(self.hint)
        b = win.action(widgets.button("Run full check", lambda *_: win.full_check(), "primary",
                                      "Checks the setup, re-hashes every mod file in the game and reads the logs of the last launch"))
        b.set_valign(Gtk.Align.CENTER)
        row.append(b)
        self.append(row)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sc.set_child(self.cards)
        self.append(sc)
        self.registered = []      # buttons on the cards that the window switches on and off
        self.buttons = {}         # (check id, step number) -> button, for the cards shown now

    def update(self):
        for b in self.registered:
            self.win.forget(b)
        self.registered, self.buttons = [], {}
        widgets.clear(self.cards)
        checks = self.win.health + list(self.win.extra_checks.values())
        todo = [c for c in checks if c["status"] in ("fail", "warn")]
        if todo:
            self.hint.set_label(f"{len(todo)} thing{'s' if len(todo) != 1 else ''} to sort out before your mods will load properly. "
                                "Work through the entries marked PROBLEM and CHECK from the top; each lists its steps.")
        else:
            self.hint.set_label("Is everything in place for your mods to load? Game, Proton, launch options, frameworks, "
                                "the files themselves and the last launch.")
        order = {"fail": 0, "warn": 1, "ok": 2, "info": 3}
        for c in sorted(checks, key=lambda c: order.get(c["status"], 9)):
            card = Gtk.Box(spacing=10)
            card.add_css_class("card")
            text_, kind = {"ok": ("OK", "good"), "warn": ("CHECK", "warn"), "fail": ("PROBLEM", "bad"), "info": ("INFO", "")}[c["status"]]
            b = widgets.badge(text_, kind)
            b.set_valign(Gtk.Align.START)
            b.set_width_chars(8)
            card.append(b)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
            text.append(widgets.label(c["title"], "strong"))
            if c["detail"]:
                text.append(widgets.label(c["detail"], "dim", "small", wrap=True, selectable=True))
            steps = c.get("steps") or []
            for n, st in enumerate(steps, 1):
                line = Gtk.Box(spacing=10)
                line.set_margin_top(3)
                lab = widgets.label(f"{n}.  {st['text']}" if len(steps) > 1 else st["text"], "small", wrap=True, selectable=True)
                lab.set_hexpand(True)
                line.append(lab)
                button = self.action_button(st.get("action"))
                if button is not None:
                    button.set_valign(Gtk.Align.START)
                    line.append(button)
                    self.buttons[(c["id"], n)] = button
                text.append(line)
            if c["fix"] and not steps:
                text.append(widgets.label("What to do: " + c["fix"], "small", wrap=True, selectable=True))
            card.append(text)
            self.cards.append(card)

    def register(self, button, modifies=False, cond=None):
        self.registered.append(self.win.action(button, modifies=modifies, cond=cond))
        return button

    def waiting_download(self, nexus_id):
        """The newest archive in the downloads folder that comes from this Nexus page, or None."""
        try:
            found = [p for p in self.win.scan_dir.iterdir() if p.is_file() and p.suffix.lower() in ARCHIVE_EXT
                     and engine.parse_mod_name(p.stem)["nexus_id"] == nexus_id]
        except OSError:
            return None
        return max(found, key=lambda p: p.stat().st_mtime) if found else None

    def action_button(self, action):
        """The button for one step, or None if the step is only words."""
        if not action:
            return None
        win, kind, label = self.win, action["type"], action.get("label", "Do it")
        if kind == "copy":
            return widgets.button(label, lambda *_: self.copy(action["text"]), "tiny")
        if kind == "url":
            return widgets.button(label, lambda *_: Gio.AppInfo.launch_default_for_uri(action["url"], None), "tiny",
                                  "Opens in your web browser")
        if kind == "open":
            return widgets.button(label, lambda *_: Gio.AppInfo.launch_default_for_uri(Path(action["path"]).as_uri(), None), "tiny",
                                  "Opens in your file manager")
        if kind == "tab":
            return widgets.button(label, lambda *_: win.stack.set_visible_child_name(action["tab"]), "tiny")
        if kind == "steam":
            return widgets.button(label, lambda *_: self.steam(action["url"]), "tiny", "Opens in your Steam")
        if kind == "launch":
            return self.register(widgets.button(label, win.launch, "tiny"), cond=lambda: not win.game_is_running)
        if kind == "accept-build":
            return self.register(widgets.button(label, self.accept_build, "tiny",
                                                "Record the installed game version as the one the mods are for"), modifies=True)
        if kind == "run":
            return self.register(widgets.button(label, lambda *_: win.run(action["args"], modifies=True), "tiny primary"), modifies=True)
        if kind == "terminal":
            if engine.terminal_command(action["command"]) is None:      # no terminal program found: the command to paste
                return widgets.button("Copy the command", lambda *_: self.copy(action["command"]), "tiny", action["command"])
            return widgets.button(label, lambda *_: self.terminal(action["command"]), "tiny primary",
                                  "Opens a terminal window that runs:  " + action["command"] + "\nIt asks for your password there.")
        if kind == "install":
            archive = self.waiting_download(action["nexus_id"])
            if archive is None:
                b = widgets.button("Waiting for the download", lambda *_: None, "tiny",
                                   f"Lights up when the file is in {win.scan_dir}")
                b.set_sensitive(False)
                return b
            return self.register(widgets.button(label, lambda *_: self.install(archive), "tiny primary", archive.name),
                                 modifies=True, cond=win.has_store)
        return None

    def copy(self, text):
        self.win.get_clipboard().set(text)
        self.win.out("\ncopied: " + text, "note")

    def steam(self, url):
        try:
            engine.steam_open(url, self.win.status.get("game"))
            self.win.out("\nasked Steam to open " + url, "note")
        except OSError as e:
            self.win.out(f"\nerror: could not reach Steam: {e}", "err")

    def terminal(self, command):
        cmd = engine.terminal_command(command)
        try:
            engine.spawn_detached(cmd)
            self.win.out("\nopened a terminal running: " + command + "\nWhen it has finished, come back here; the check runs again by itself.", "note")
        except OSError as e:
            self.win.out(f"\nerror: could not open a terminal ({e}). Run this yourself: {command}", "err")

    def install(self, archive):
        """Install a download straight from a step, the same way the Install tab does."""
        page = self.win.install_page
        page.browsed(archive)
        page.add(False)

    def accept_build(self, *_):
        self.win.confirm("Accept the new game version?",
                         "Do this after updating the frameworks (RED4ext, Cyber Engine Tweaks, redscript, ArchiveXL, TweakXL, "
                         "Codeware) for the new game version. Until then, old frameworks can stop the game from starting.",
                         "Accept version", lambda: self.win.run(["accept-build"], modifies=True))


class SettingsPage(Gtk.Box):
    """The folders the manager works with, and the side picture."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.win = win
        self.values = {}
        fixed_store, fixed_game = bool(win.opts.store), bool(win.opts.game)

        b1 = widgets.button("Choose", lambda *_: widgets.pick_folder(win, "Choose the mod store folder", None,
                                                                     lambda p: win.save_setting("store", str(p))))
        b1.set_sensitive(not fixed_store)
        self.card("store", "Mod store", "Where the manager keeps every mod, one folder each. Best on the same disk as the game, "
                  "so files are shared instead of copied.", [b1])
        b2 = widgets.button("Choose", lambda *_: widgets.pick_folder(win, "Choose the 'Cyberpunk 2077' folder", None, self.game_chosen))
        b3 = widgets.button("Find through Steam", lambda *_: win.save_setting("game", None))
        b2.set_sensitive(not fixed_game)
        b3.set_sensitive(not fixed_game)
        self.card("game", "Game folder", "Found through your Steam libraries unless you choose one (for example a GOG copy run "
                  "through Heroic or Lutris).", [b2, b3])
        self.card("scan_dir", "Downloads folder", "The Install tab lists the mod archives in this folder.",
                  [widgets.button("Choose", lambda *_: widgets.pick_folder(win, "Choose your downloads folder", win.scan_dir, win.set_scan_dir))])
        self.card("artwork", "Side panel picture", "Swap the built-in picture for one of your own. Clear brings the built-in one back.",
                  [widgets.button("Choose", lambda *_: widgets.pick_file(win, "Choose a picture", None,
                                                                         lambda p: win.save_setting("artwork", str(p)), pictures=True)),
                   widgets.button("Clear", lambda *_: win.save_setting("artwork", None))])
        self.saved = self.card("saved", "Saved game settings", "This store carries saved settings (from a move from another computer). "
                               "Applying copies them into the game; what they replace is backed up under backups/ in the store.",
                               [win.action(widgets.button("Apply", self.apply_saved), modifies=True)])
        self.append(widgets.label(f"{NOTICE}\nSettings file: {engine.CONFIG}", "dim", "small", wrap=True, selectable=True))

    def card(self, key, title, explain, buttons):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")
        head = Gtk.Box(spacing=8)
        t = widgets.label(title, "strong")
        t.set_hexpand(True)
        head.append(t)
        for b in buttons:
            head.append(b)
        card.append(head)
        self.values[key] = widgets.label("", "path", selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
        card.append(self.values[key])
        card.append(widgets.label(explain, "dim", "small", wrap=True))
        self.append(card)
        return card

    def game_chosen(self, p: Path):
        if engine.is_game_dir(p):
            self.win.save_setting("game", str(p))
        else:
            self.win.out(f"error: {p} is not the game folder (no bin/x64/Cyberpunk2077.exe in it)", "err")

    def apply_saved(self, *_):
        self.win.confirm("Apply the saved settings?",
                         "The settings saved in the store replace the ones in the game. "
                         "The files they replace are backed up under backups/ in the store.",
                         "Apply settings", lambda: self.win.run(["settings"], modifies=True))

    def update(self):
        win, st = self.win, self.win.status
        self.values["store"].set_label(str(st.get("store", "")) + ("" if st.get("has_store") else "   (not set up yet)"))
        self.values["game"].set_label((st.get("game") or "not found") +
                                      ("" if win.cfg.get("game") or win.opts.game else "   (found through Steam)"))
        self.values["scan_dir"].set_label(str(win.scan_dir))
        self.values["artwork"].set_label(win.cfg.get("artwork") or "the built-in picture")
        n = st.get("settings_saved", 0)
        self.saved.set_visible(n > 0)
        self.values["saved"].set_label(f"{n} settings files")
