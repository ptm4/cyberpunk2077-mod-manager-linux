"""The main window: side panel, the four tabs, the output pane, and the state they all share.

The window holds no mod logic. Every action runs the engine as a separate process
(see runner.py) and shows what it prints, so the window and the command line always
behave the same and the window never freezes.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import __version__, engine  # noqa: E402
from . import widgets  # noqa: E402
from .pages import HealthPage, InstallPage, ModsPage, SettingsPage  # noqa: E402
from .runner import Runner  # noqa: E402
from .setup import SetupDialog  # noqa: E402
from .style import CSS  # noqa: E402

APP_ID = "io.github.ptm4.SamuraiModManager"
DATA = Path(__file__).resolve().parent.parent / "data"
ARTWORK = DATA / "samurai.png"     # the side picture unless the user picks another
STEAM_RUN = "steam://rungameid/" + engine.APPID


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, opts):
        super().__init__(application=app, title="Samurai Mod Manager", default_width=1200, default_height=820)
        self.add_css_class("cp")
        self.opts = opts
        self.cfg = engine.load_config()
        self.scan_dir = Path(self.cfg.get("scan_dir") or Path.home() / "Downloads").expanduser()
        self.game_is_running = False
        self.actions = []        # (widget, changes the game?, extra condition or None)
        self.status = {}         # from `status --json`
        self.mods = []           # from `list --json`
        self.health = []         # from `doctor --json`
        self.extra_checks = {}   # results of the full check: files and logs
        self.put_back = False    # what the side panel's mods button does right now
        self.runner = Runner(self.out, self.on_busy,
                             (["--store", opts.store] if opts.store else []) + (["--game", opts.game] if opts.game else []))

        hb = Gtk.HeaderBar()
        self.spinner = Gtk.Spinner()
        hb.pack_end(self.spinner)
        self.set_titlebar(hb)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        self.banner = widgets.label("The game is running. Close it before changing mods; checks and dry runs still work.", "banner")
        self.banner.set_visible(False)
        root.append(self.banner)
        self.setup_bar = Gtk.Box(spacing=12, visible=False)
        self.setup_bar.add_css_class("banner")
        self.setup_text = widgets.label("", wrap=True)
        self.setup_text.set_hexpand(True)
        self.setup_bar.append(self.setup_text)
        self.setup_button = widgets.button("Set up", lambda *_: self.run(["init"], modifies=True), "primary")
        self.setup_bar.append(self.setup_button)
        root.append(self.setup_bar)
        body = Gtk.Box(vexpand=True)
        root.append(body)
        body.append(self.build_sidebar())

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, hexpand=True, position=470,
                          shrink_start_child=False, shrink_end_child=False)
        body.append(paned)
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=12, margin_start=16, margin_end=16,
                      margin_bottom=10)
        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.mods_page = ModsPage(self)
        self.install_page = InstallPage(self)
        self.health_page = HealthPage(self)
        self.settings_page = SettingsPage(self)
        for page, name, title in ((self.mods_page, "mods", "Mods"), (self.install_page, "install", "Install"),
                                  (self.health_page, "health", "Health"), (self.settings_page, "settings", "Settings")):
            self.stack.add_titled(page, name, title)
        top.append(Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.START))
        top.append(self.stack)
        paned.set_start_child(top)
        paned.set_end_child(self.build_output())

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self.on_drop)
        self.add_controller(drop)

        self.out(f"samurai-mm {__version__}", "note")
        self.install_page.watch(self.scan_dir)
        self.check_game()
        GLib.timeout_add_seconds(3, self.check_game)
        self.refresh(health=True)
        if not self.cfg.get("setup_done") and not (opts.store or opts.game):
            GLib.idle_add(lambda: SetupDialog(self).present() and False)

    # ---- building

    def build_sidebar(self):
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.add_css_class("sidebar")
        side.set_size_request(320, -1)
        self.art_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.append(self.art_slot)
        self.load_artwork()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, margin_top=12, margin_bottom=14, margin_start=16,
                      margin_end=16, vexpand=True)
        side.append(box)
        box.append(widgets.label("SAMURAI", "brand"))
        box.append(widgets.label("MOD MANAGER FOR CYBERPUNK 2077", "brand-sub"))
        self.game_state = widgets.label("")
        self.game_state.set_margin_top(6)
        box.append(self.game_state)
        self.summary = widgets.label("", "dim", "small", wrap=True)
        box.append(self.summary)
        self.health_summary = widgets.label("", "small", wrap=True)
        box.append(self.health_summary)
        self.launch_button = self.action(widgets.button("Launch the game", self.launch, "primary", "Start Cyberpunk 2077 through Steam"),
                                         cond=lambda: not self.game_is_running)
        self.launch_button.set_margin_top(10)
        box.append(self.launch_button)
        # One button for the whole game folder: its meaning follows the state (see update_mods_button).
        self.mods_button = self.action(widgets.button("", self.toggle_all), modifies=True, cond=self.has_store)
        box.append(self.mods_button)
        return side

    def load_artwork(self):
        widgets.clear(self.art_slot)
        own = self.cfg.get("artwork")
        for art in ([Path(own).expanduser()] if own else []) + [ARTWORK]:
            try:
                if art.is_file():
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(art), 320, -1, True)
                    if pb.get_height() > 300:
                        pb = pb.new_subpixbuf(0, (pb.get_height() - 300) // 2, 320, 300)
                    pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
                    pic.set_can_shrink(False)
                    pic.set_halign(Gtk.Align.CENTER)
                    self.art_slot.append(pic)
                    return
            except GLib.Error:
                continue      # an unreadable picture: fall back to the built-in one

    def build_output(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("outframe")
        row = Gtk.Box(spacing=8, margin_top=6, margin_bottom=6, margin_start=16, margin_end=16)
        lab = widgets.section("Output")
        lab.set_hexpand(True)
        row.append(lab)
        row.append(widgets.button("Copy", self.copy_output, "tiny"))
        row.append(widgets.button("Clear", lambda *_: self.buf.set_text(""), "tiny"))
        box.append(row)
        sc = Gtk.ScrolledWindow(vexpand=True, min_content_height=130)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, left_margin=16, right_margin=16,
                                 top_margin=6, bottom_margin=10, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.view.add_css_class("output")
        self.buf = self.view.get_buffer()
        self.buf.create_tag("cmd", foreground="#e2504c", weight=Pango.Weight.BOLD)
        self.buf.create_tag("ok", foreground="#7fc98a")
        self.buf.create_tag("err", foreground="#ff7b72")
        self.buf.create_tag("note", foreground="#8f8c87")
        self.buf.create_tag("dry", foreground="#f0b04a")
        self.end_mark = self.buf.create_mark("end", self.buf.get_end_iter(), False)
        sc.set_child(self.view)
        box.append(sc)
        return box

    # ---- services the pages use

    @property
    def busy(self):
        return self.runner.busy

    def has_store(self):
        return bool(self.status.get("has_store"))

    def action(self, widget, modifies=False, cond=None):
        """Register a button so it is switched off while a command runs, and (if it changes the game) while the game runs."""
        self.actions.append((widget, modifies, cond))
        return widget

    def forget(self, widget):
        """Drop a registered button that is being thrown away."""
        self.actions = [a for a in self.actions if a[0] is not widget]

    def out(self, text, tag=None):
        it = self.buf.get_end_iter()
        if tag:
            self.buf.insert_with_tags_by_name(it, text + "\n", tag)
        else:
            self.buf.insert(it, text + "\n")
        self.view.scroll_to_mark(self.end_mark, 0.0, False, 0.0, 1.0)

    def run(self, args, done=None, quiet=False, modifies=False, shown=None):
        def wrapped(code, lines):
            if done:
                done(code, lines)
            if modifies:
                self.refresh(health=True)
        self.runner.run(args, wrapped, quiet=quiet, shown=shown)

    def confirm(self, title, detail, ok_label, then):
        widgets.choose(self, title, detail, ["Cancel", ok_label], lambda i: then())

    def choose(self, title, detail, buttons, then):
        widgets.choose(self, title, detail, buttons, then)

    def on_busy(self, busy):
        self.spinner.set_spinning(busy)
        self.update_sensitivity()

    def update_sensitivity(self):
        for w, modifies, cond in self.actions:
            w.set_sensitive(not self.busy and not (modifies and self.game_is_running) and (cond is None or bool(cond())))
        if hasattr(self, "mods_page"):
            self.mods_page.set_switches_sensitive(not self.busy and not self.game_is_running)
        self.setup_button.set_sensitive(not self.busy)

    def check_game(self):
        running = engine.game_running()
        if running != self.game_is_running or not self.game_state.get_label():
            self.game_is_running = running
            self.game_state.set_label("Game is running" if running else "Game is closed")
            self.game_state.remove_css_class("state-bad" if not running else "state-ok")
            self.game_state.add_css_class("state-bad" if running else "state-ok")
            self.banner.set_visible(running)
            self.update_sensitivity()
        return True

    # ---- state: status, mod list, health

    def refresh(self, health=False):
        self.run(["status", "--json"], self.got_status, quiet=True)
        if health:
            self.run(["doctor", "--json"], self.got_health, quiet=True)

    def got_status(self, code, lines):
        try:
            self.status = json.loads("\n".join(lines)) if code == 0 else {}
        except ValueError:
            self.status = {}
        st = self.status
        if not st:
            self.out("\n".join(lines) or "error: could not read the status", "err")
        if st and not st.get("game"):
            self.setup_text.set_label("Cyberpunk 2077 was not found. Choose the game folder on the Settings tab.")
            self.setup_button.set_visible(False)
            self.setup_bar.set_visible(True)
        elif st and not st.get("has_store"):
            self.setup_text.set_label(f"There is no mod store yet. Set up creates an empty one at {st.get('store')} "
                                      "(change the place on the Settings tab first if you like).")
            self.setup_button.set_visible(True)
            self.setup_bar.set_visible(True)
        else:
            self.setup_bar.set_visible(False)
        self.settings_page.update()
        self.launch_button.set_visible(bool(st.get("steam")))    # other launchers start the game themselves
        if st.get("has_store"):
            self.run(["list", "--json"], self.got_list, quiet=True)
        else:
            self.got_list(0, ["[]"])

    def got_list(self, code, lines):
        try:
            self.mods = json.loads("\n".join(lines)) if code == 0 else []
        except ValueError:
            self.mods = []
        if code != 0:
            self.out("\n".join(lines), "err")
        on = [m for m in self.mods if m["state"] != "disabled"]
        in_game = sum(1 for m in on if m["state"] == "deployed")
        if not self.has_store():
            self.summary.set_label("No mod store yet.")
        else:
            off = len(self.mods) - len(on)
            text = f"{len(self.mods)} mod{'' if len(self.mods) == 1 else 's'}" + (f", {off} switched off" if off else "")
            text += f"\n{in_game} in the game" + (f", {len(on) - in_game} waiting to be put back" if in_game != len(on) else "")
            self.summary.set_label(text)
        self.update_mods_button(on, in_game)
        self.mods_page.update()
        self.install_page.update()
        self.update_sensitivity()

    def update_mods_button(self, on, in_game):
        """Everything in the game: offer vanilla. Something missing from the game: offer to put the mods back."""
        self.mods_button.set_visible(bool(on))
        self.put_back = in_game != len(on)
        for cls in ("danger", "primary"):
            self.mods_button.remove_css_class(cls)
        if self.put_back:
            self.mods_button.set_label("Put mods back")
            self.mods_button.set_tooltip_text("Place every switched-on mod's files into the game folder")
        else:
            self.mods_button.set_label("Play without mods")
            self.mods_button.set_tooltip_text("Take every mod file out of the game folder, back to vanilla. The mods stay in the store.")

    def got_health(self, code, lines):
        try:
            self.health = json.loads("\n".join(lines))
        except ValueError:
            self.health = []
        every = self.health + list(self.extra_checks.values())
        bad = sum(1 for c in every if c["status"] == "fail")
        warn = sum(1 for c in every if c["status"] == "warn")
        for cls in ("state-ok", "state-bad"):
            self.health_summary.remove_css_class(cls)
        if not every:
            self.health_summary.set_label("")
        elif bad or warn:
            self.health_summary.set_label(f"Health: {bad} problem{'' if bad == 1 else 's'}, {warn} to check (see the Health tab)")
            self.health_summary.add_css_class("state-bad")
        else:
            self.health_summary.set_label("Health: all checks pass")
            self.health_summary.add_css_class("state-ok")
        self.health_page.update()
        self.update_sensitivity()

    def full_check(self):
        """The Health button: setup checks, then every file, then the logs of the last launch."""
        self.extra_checks = {}
        self.run(["doctor"])
        if self.has_store():
            def files(code, lines):
                last = next((l for l in reversed(lines) if l.startswith("verify:")), "could not verify")
                self.extra_checks["files"] = {
                    "id": "files", "title": "Mod files in the game folder", "status": "ok" if code == 0 else "fail",
                    "detail": last.replace("verify: ", ""),
                    "fix": "" if code == 0 else "Press \"Put mods back\" (or switch the mod off and on) to restore missing or changed files."}

            def logs(code, lines):
                fails = [l.strip() for l in lines if l.strip().startswith("[FAIL]")]
                passes = sum(1 for l in lines if l.strip().startswith("[PASS]"))
                self.extra_checks["logs"] = {
                    "id": "logs", "title": "Last game launch (logs)",
                    "status": "ok" if code == 0 and passes else ("info" if code == 0 else "warn"),
                    "detail": (f"{passes} checks passed" if code == 0 and passes else "nothing to read yet") if code == 0 else
                              f"{len(fails)} of {len(fails) + passes} checks did not pass, for example: " +
                              "; ".join(f.replace("[FAIL] ", "") for f in fails[:3]),
                    "fix": "" if code == 0 else "Launch the game to the main menu after changing mods, quit, and run the check again. "
                                                "The full list is in the output pane."}
            self.run(["verify"], files)
            self.run(["logs"], logs)
        self.run(["doctor", "--json"], self.got_health, quiet=True)

    # ---- actions

    def launch(self, *_):
        self.out("\nasking Steam to start the game", "note")
        try:
            Gio.AppInfo.launch_default_for_uri(STEAM_RUN, None)
        except GLib.Error as e:
            self.out(f"error: could not reach Steam: {e.message}", "err")

    def toggle_all(self, *_):
        if self.put_back:
            self.run(["deploy"], modifies=True)
        else:
            self.confirm("Play without mods?",
                         "Every file the manager placed in the game folder is taken out, back to vanilla. "
                         "Your mods stay in the store, and \"Put mods back\" restores them.",
                         "Take mods out", lambda: self.run(["undeploy"], modifies=True))

    def save_setting(self, key, value):
        if value is None:
            self.cfg.pop(key, None)
        else:
            self.cfg[key] = value
        engine.save_config(self.cfg)
        if key == "artwork":
            self.load_artwork()
        self.refresh(health=True)

    def set_scan_dir(self, path: Path):
        self.scan_dir = Path(path)
        self.cfg["scan_dir"] = str(path)
        engine.save_config(self.cfg)
        self.install_page.watch(self.scan_dir)
        self.settings_page.update()

    def after_setup(self, scan_dir: Path, create_store):
        """Called by the welcome step once the folders are confirmed."""
        self.cfg = engine.load_config()
        self.scan_dir = Path(scan_dir)
        self.install_page.watch(self.scan_dir)
        if create_store:
            self.run(["init"], modifies=True)
        else:
            self.refresh(health=True)

    def on_drop(self, _target, value, _x, _y):
        files = value.get_files()
        if files and files[0].get_path():
            self.install_page.browsed(Path(files[0].get_path()))
            self.stack.set_visible_child_name("install")
            return True
        return False

    def copy_output(self, *_):
        s, e = self.buf.get_bounds()
        self.get_clipboard().set(self.buf.get_text(s, e, False))


class App(Gtk.Application):
    def __init__(self, opts):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE if (opts.store or opts.game)
                         else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.opts = opts
        self.win = None

    def do_activate(self):
        if self.win is None:
            settings = Gtk.Settings.get_default()
            if settings is None:
                sys.exit("error: no display to open the window on. The command line (samurai-mm) works without one.")
            if hasattr(Gtk, "InterfaceColorScheme"):
                settings.set_property("gtk-interface-color-scheme", Gtk.InterfaceColorScheme.DARK)
            else:
                settings.set_property("gtk-application-prefer-dark-theme", True)
            prov = Gtk.CssProvider()
            prov.load_from_string(CSS)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            self.win = MainWindow(self, self.opts)
        self.win.present()


def main():
    ap = argparse.ArgumentParser(prog="samurai-mm-gui", description="Window for the samurai-mm mod manager")
    ap.add_argument("--store", help="mod store to use for this run (overrides the saved setting)")
    ap.add_argument("--game", help="game folder to use for this run (overrides the saved setting)")
    opts = ap.parse_args()
    have = (Gtk.get_major_version(), Gtk.get_minor_version())
    if have < (4, 12):
        sys.exit(f"error: the window needs GTK 4.12 or newer; this system has {have[0]}.{have[1]}. "
                 "The command line (samurai-mm) works without it.")
    if os.geteuid() == 0:
        sys.exit("error: do not run this as root (or with sudo).")
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Samurai Mod Manager")
    return App(opts).run([sys.argv[0]])
