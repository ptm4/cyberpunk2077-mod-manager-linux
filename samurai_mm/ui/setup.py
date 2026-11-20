"""The welcome step on first start: confirm or choose the three folders the manager works with."""
import json
import os
from pathlib import Path

from gi.repository import Gtk, Pango

from .. import engine
from . import widgets


class SetupDialog(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Welcome", transient_for=win, modal=True, default_width=640, default_height=-1)
        self.add_css_class("cp")
        self.win = win
        cfg = win.cfg
        self.game = engine.find_game(required=False)
        self.game_chosen = bool(cfg.get("game"))
        self.store_chosen = bool(cfg.get("store"))
        self.store = Path(cfg.get("store") or engine.suggest_store(self.game)).expanduser()
        self.scan = win.scan_dir

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=16,
                        margin_start=18, margin_end=18)
        self.set_child(outer)
        outer.append(widgets.label("Samurai Mod Manager", "picker-title"))
        outer.append(widgets.label("Before anything else, check these three folders. Nothing is changed until you continue, "
                                   "and you can change them later on the Settings tab.", "dim", wrap=True))
        self.rows = {}
        for key, title, pick in (
                ("game", "Where the game is installed", lambda *_: self.pick("Choose the 'Cyberpunk 2077' folder", self.game, self.set_game)),
                ("store", "Where your mods are kept", lambda *_: self.pick("Choose the mod store folder", self.store.parent, self.set_store)),
                ("scan", "Where your downloads land", lambda *_: self.pick("Choose your downloads folder", self.scan, self.set_scan))):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.add_css_class("card")
            head = Gtk.Box(spacing=8)
            t = widgets.label(title, "strong")
            t.set_hexpand(True)
            head.append(t)
            head.append(widgets.button("Choose", pick))
            card.append(head)
            value = widgets.label("", "path", selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
            note = widgets.label("", "dim", "small", wrap=True)
            card.append(value)
            card.append(note)
            self.rows[key] = (value, note)
            outer.append(card)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.go = widgets.button("Continue", self.on_continue, "primary")
        row.append(self.go)
        outer.append(row)
        self.show_values()

    def pick(self, title, start, then):
        widgets.pick_folder(self, title, start, then)

    def set_game(self, p: Path):
        if engine.is_game_dir(p):
            self.game, self.game_chosen = p, True
            if not self.store_chosen:
                self.store = engine.suggest_store(p)      # keep the store on the game's disk
            self.show_values()
        else:
            self.rows["game"][1].set_label(f"{p} is not the game folder: it has no bin/x64/Cyberpunk2077.exe. Choose the folder named "
                                           "'Cyberpunk 2077'.")
            self.rows["game"][1].add_css_class("state-bad")

    def set_store(self, p: Path):
        self.store, self.store_chosen = p, True
        self.show_values()

    def set_scan(self, p: Path):
        self.scan = p
        self.show_values()

    def show_values(self):
        value, note = self.rows["game"]
        note.remove_css_class("state-bad")
        if self.game:
            value.set_label(str(self.game))
            note.set_label("You chose this folder." if self.game_chosen else "Found through your Steam library. Choose another if this is not the one you play.")
        else:
            value.set_label("not found")
            note.set_label("No Steam library has the game. Choose the folder named 'Cyberpunk 2077' (the one that holds bin, archive and r6).")
            note.add_css_class("state-bad")
        value, note = self.rows["store"]
        value.set_label(str(self.store))
        manifest = self.store / "manifest.json"
        if manifest.is_file():
            try:
                man = json.loads(manifest.read_text(encoding="utf-8-sig"))
                count = len(man.get("mods", [])) + len(man.get("disabled", {}).get("mods", []))
                note.set_label(f"There is already a mod store here with {count} mods. It will be used as it is.")
            except (OSError, ValueError):
                note.set_label("There is a mod store here, but its list could not be read.")
        else:
            try:
                probe = self.store
                while not probe.exists() and probe != probe.parent:
                    probe = probe.parent
                same = self.game is None or os.stat(probe).st_dev == os.stat(self.game).st_dev
            except OSError:
                same = True
            note.set_label("A new, empty store will be created here." + ("" if same else
                           " It is on a different disk than the game, so every mod file will take space twice. That works; "
                           "choose a folder on the game's disk to avoid it."))
        value, note = self.rows["scan"]
        value.set_label(str(self.scan))
        note.set_label("The Install tab lists the zip, 7z and rar files in this folder.")
        self.go.set_sensitive(self.game is not None)

    def on_continue(self, *_):
        cfg = self.win.cfg
        if self.game_chosen:
            cfg["game"] = str(self.game)
        cfg["store"] = str(self.store)
        cfg["scan_dir"] = str(self.scan)
        cfg["setup_done"] = True
        engine.save_config(cfg)
        self.close()
        self.win.after_setup(self.scan, create_store=not (self.store / "manifest.json").is_file())
