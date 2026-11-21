# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Drives the real window through every flow against a sandbox, without a person clicking.

Usage:
  gui_drive.py flows SANDBOX SHOTS_DIR [PICTURE]     everything after setup, with --store/--game pointing into SANDBOX
  gui_drive.py firstrun SANDBOX SHOTS_DIR            the welcome step; run it with HOME=SANDBOX/home

SANDBOX is a new, empty folder. The fake game, the Steam files and the sample downloads are created in it. Run on a throwaway display, for example `kwin_wayland --virtual --socket test`
with WAYLAND_DISPLAY=test, with XDG_CONFIG_HOME / XDG_CACHE_HOME pointing into the sandbox so no real settings
are touched, and with GSK_RENDERER=cairo: saving the pictures through the GPU driver can crash while something
else (the game) is using the GPU. Each run needs a fresh SANDBOX.
"""
import json
import os
import sys
import types
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
MODE, SB, SHOTS = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
ART = sys.argv[4] if len(sys.argv) > 4 else None
os.environ["SAMURAI_MM_ASSUME_GAME_CLOSED"] = "1"     # the real game may be running while this test runs

from samurai_mm import engine  # noqa: E402
from samurai_mm.ui import pages, window  # noqa: E402
from samurai_mm.ui.picker import Picker  # noqa: E402
from samurai_mm.ui.setup import SetupDialog  # noqa: E402
from gi.repository import Gio, GLib, Gtk  # noqa: E402

pretend = {"running": False}
engine.game_running = lambda: pretend["running"]

if MODE == "firstrun":
    STEAM = Path.home() / ".local/share/Steam"
    GAME, STORE = STEAM / "steamapps/common/Cyberpunk 2077", engine.DEFAULT_STORE
    opts = types.SimpleNamespace(store=None, game=None)
else:
    STEAM = SB
    GAME, STORE = SB / "steamapps/common/Cyberpunk 2077", SB / "store"
    opts = types.SimpleNamespace(store=str(STORE), game=str(GAME))
(GAME / "bin/x64").mkdir(parents=True, exist_ok=True)
(GAME / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ fake")
FOMOD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <moduleName>Fomod Test</moduleName>
 <requiredInstallFiles><folder source="core" destination=""/></requiredInstallFiles>
 <installSteps order="Explicit">
  <installStep name="Main choices">
   <optionalFileGroups>
    <group name="Texture" type="SelectExactlyOne"><plugins order="Explicit">
     <plugin name="Option A"><description>The A look.</description><files><file source="Opt A\\opt_a.archive" destination="archive\\pc\\mod\\opt_a.archive"/></files><typeDescriptor><type name="Optional"/></typeDescriptor></plugin>
     <plugin name="Option B"><description>The B look.</description><files><folder source="Opt B" destination="archive/pc/mod"/></files><typeDescriptor><type name="Recommended"/></typeDescriptor></plugin>
    </plugins></group>
    <group name="Extras" type="SelectAny"><plugins>
     <plugin name="Script patch"><description>Adds a patch.</description><conditionFlags><flag name="patch">On</flag></conditionFlags><typeDescriptor><type name="Optional"/></typeDescriptor></plugin>
    </plugins></group>
   </optionalFileGroups>
  </installStep>
 </installSteps>
 <conditionalFileInstalls><patterns><pattern><dependencies operator="And"><flagDependency flag="patch" value="On"/></dependencies><files><file source="extra/patch.reds" destination="r6/scripts/patch.reds"/></files></pattern></patterns></conditionalFileInstalls>
</config>
"""


def make_downloads(dl: Path):
    """The sample downloads the flows use: a plain mod, one with two variants, one with a FOMOD installer."""
    dl.mkdir(parents=True, exist_ok=True)
    samples = {
        "Plain Mod-111-1-0-1700000000.zip": {"archive/pc/mod/plain.archive": "a", "r6/scripts/plain.reds": "b"},
        "Colour Mod-222-1-0-1700000001.7z": {"Colour Mod/Red/colour_red.archive": "r", "Colour Mod/Blue/colour_blue.archive": "b",
                                             "Colour Mod/preview.png": "x"},
        "Fomod Test-333-1-0-1700000002.zip": {"fomod/ModuleConfig.xml": FOMOD_XML, "Core/archive/pc/mod/core.archive": "c",
                                              "Opt A/opt_a.archive": "a", "Opt B/opt_b.archive": "b", "extra/patch.reds": "e"},
    }
    for name, files in samples.items():
        if (dl / name).exists():
            continue
        if name.endswith(".7z"):
            import shutil
            import subprocess
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                for rel, data in files.items():
                    (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp) / rel).write_text(data)
                subprocess.run([shutil.which("7z") or "7z", "a", "-bso0", "-bsp0", str(dl / name), "."], cwd=tmp, check=True)
        else:
            with zipfile.ZipFile(dl / name, "w") as z:
                for rel, data in files.items():
                    z.writestr(rel, data)


make_downloads(SB / "dl")
ACF = STEAM / "steamapps/appmanifest_1091500.acf"
ACF.write_text('"AppState"\n{\n\t"buildid"\t\t"1000"\n}\n')
with zipfile.ZipFile(SB / "dl" / "Plain Mod-111-1-1-1700000009.zip", "w") as z:
    z.writestr("archive/pc/mod/plain.archive", "version two")
    z.writestr("archive/pc/mod/plain_extra.archive", "new file")

app = window.App(opts)
# its own instance: without this the welcome-step run would just wake a manager that is already open on this desktop
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what, flush=True)
    if not cond:
        fails.append(what)


def text(win):
    s, e = win.buf.get_bounds()
    return win.buf.get_text(s, e, False)


def shot(w, name):
    p = Gtk.WidgetPaintable.new(w)
    snap = Gtk.Snapshot()
    p.snapshot(snap, w.get_width(), w.get_height())
    node = snap.to_node()
    if node is None:
        print("     (no picture taken for %s: the window is not drawn yet)" % name, flush=True)
        return
    w.get_renderer().render_texture(node, None).save_to_png(str(SHOTS / name))


def select(win, part):
    i = 0
    while (row := win.install_page.list.get_row_at_index(i)) is not None:
        if part in row.path.name:
            win.install_page.list.select_row(row)
            return row
        i += 1
    raise SystemExit("no download named " + part)


def mod_row(win, part):
    i = 0
    while (row := win.mods_page.list.get_row_at_index(i)) is not None:
        if part in row.mod["name"]:
            return row, win.mods_page.switches[i]
        i += 1
    raise SystemExit("no mod named " + part)


def toplevel(kind):
    for t in Gtk.Window.list_toplevels():
        if isinstance(t, kind) and t.get_visible():
            return t


def game_files():
    return sorted(str(p.relative_to(GAME)) for p in GAME.rglob("*") if p.is_file())


def state_of(win, part):
    return [m["state"] for m in win.mods if part in m["name"]][0]


def buttons(win):
    return {w.get_label(): w.get_sensitive() for w, m, c in win.actions}


def firstrun(win):
    yield
    yield
    yield
    dlg = toplevel(SetupDialog)
    check(dlg is not None, "welcome step opens on first start")
    check(dlg.rows["game"][0].get_label() == str(GAME) and "Steam" in dlg.rows["game"][1].get_label(), "it shows the game folder it found")
    check(dlg.rows["store"][0].get_label() == str(STORE) and "will be created" in dlg.rows["store"][1].get_label(), "it shows where mods will be kept")
    dlg.set_game(SB / "dl")
    check("not the game folder" in dlg.rows["game"][1].get_label() and dlg.game == GAME, "a wrong game folder is refused with a reason")
    dlg.show_values()
    dlg.set_scan(SB / "dl")
    yield
    shot(dlg, "0-welcome.png")
    dlg.on_continue()
    yield
    cfg = json.loads(engine.CONFIG.read_text())
    check(cfg.get("setup_done") and cfg.get("scan_dir") == str(SB / "dl") and "game" not in cfg, "choices saved; a game found through Steam is not pinned")
    check((STORE / "manifest.json").is_file() and not win.setup_bar.get_visible() and toplevel(SetupDialog) is None, "the empty store is created")
    check(win.install_page.list.get_row_at_index(0) is not None, "the Install tab lists the chosen downloads folder")


def flows(win):
    win.confirm = lambda t, d, o, then: then()
    answers = []
    win.choose = lambda t, d, btns, then: (answers.append(btns), then(len(btns) - 1))    # always the last button
    yield
    yield
    yield
    check(toplevel(SetupDialog) is None, "no welcome step when folders are given on the command line")
    check(win.setup_bar.get_visible() and not win.mods_button.get_visible(), "no store yet: set-up bar shown")
    first = win.mods_page.list.get_row_at_index(0)
    check(first is not None and first.mod is None and "No mods yet" in first.get_child().get_label() and win.mods_page.selected() is None,
          "an empty mod list says so")
    win.setup_button.emit("clicked")
    yield
    check((STORE / "manifest.json").is_file() and not win.setup_bar.get_visible(), "set up created the store")
    win.stack.set_visible_child_name("install")
    win.set_scan_dir(SB / "dl")
    yield
    select(win, "Plain Mod-111-1-0")
    win.install_page.add(True)
    yield
    check("would add 2 files" in text(win) and game_files() == ["bin/x64/Cyberpunk2077.exe"], "dry run shows the plan and changes nothing")
    win.install_page.add(False)
    yield
    check(state_of(win, "Plain Mod") == "deployed" and "archive/pc/mod/plain.archive" in game_files(), "install")
    check(win.mods_button.get_visible() and win.mods_button.get_label() == "Play without mods", "side button offers vanilla once mods are in")
    shot(win, "1-install.png")
    select(win, "Colour Mod")
    win.install_page.add(True)
    yield
    pk = toplevel(Picker)
    check(pk is not None and len(pk.loose_checks) == 2 and not pk.b_go.get_sensitive(), "chooser opens, nothing ticked, install off")
    [cb for f, cb in pk.loose_checks if "red" in f.name][0].set_active(True)
    yield
    pk.go(True)
    yield
    check("would add 1 files" in text(win) and toplevel(Picker) is pk, "chooser dry run, stays open")
    pk.go(False)
    yield
    gf = game_files()
    check("archive/pc/mod/colour_red.archive" in gf and not any("blue" in g for g in gf), "only the ticked variant is installed")
    check((STORE / "archives/Colour Mod-222-1-0-1700000001.7z").is_file() and toplevel(Picker) is None and not pk.work.exists(),
          "original download kept, chooser closed and cleaned up")
    select(win, "Fomod Test")
    win.install_page.add(False)
    yield
    pk = toplevel(Picker)
    check(pk is not None and pk.fomod is not None and [cb.get_active() for p, cb in pk.group_widgets[0][1]] == [False, True],
          "installer chooser opens with the recommended option preselected")
    pk.group_widgets[1][1][0][1].set_active(True)
    yield
    shot(pk, "2-chooser.png")
    pk.go(False)
    yield
    gf = game_files()
    check(all(x in gf for x in ["archive/pc/mod/core.archive", "archive/pc/mod/opt_b.archive", "r6/scripts/patch.reds"])
          and not any("opt_a" in g for g in gf), "installer: required files, option B and the flagged patch")
    # a newer download of an installed mod
    select(win, "Plain Mod-111-1-1")
    win.install_page.add(False)
    yield
    check(answers and answers[-1][0:2] == ["Cancel", "Add as a separate mod"] and answers[-1][-1].startswith("Update Plain Mod"),
          "a newer download of an installed mod asks: update or add")
    names = [m["name"] for m in win.mods]
    check("Plain Mod-111-1-1-1700000009" in names and "Plain Mod-111-1-0-1700000000" not in names
          and "r6/scripts/plain.reds" not in game_files() and "archive/pc/mod/plain_extra.archive" in game_files(), "update replaces the old version")
    win.install_page.add(False)
    yield
    check(answers[-1] == ["Cancel", "Reinstall"] and "--replace" in text(win) and len(win.mods) == 3, "the same download again offers a reinstall")
    # switches
    win.stack.set_visible_child_name("mods")
    yield
    row, sw = mod_row(win, "Plain Mod")
    check(sw.get_active(), "switch is on for an enabled mod")
    sw.set_active(False)
    yield
    check(state_of(win, "Plain Mod") == "disabled" and "archive/pc/mod/plain.archive" not in game_files()
          and (STORE / "mods/Plain Mod-111-1-1-1700000009/archive/pc/mod/plain.archive").is_file(), "switch off: out of the game, kept in the store")
    check("1 switched off" in win.summary.get_label(), "side panel counts the switched-off mod")
    row, sw = mod_row(win, "Colour Mod")
    win.mods_page.list.select_row(row)
    yield
    shot(win, "3-mods.png")
    row, sw = mod_row(win, "Plain Mod")
    check(not sw.get_active(), "switch shows off after the list is rebuilt")
    sw.set_active(True)
    yield
    check(state_of(win, "Plain Mod") == "deployed" and "archive/pc/mod/plain.archive" in game_files(), "switch on: back in the game")
    row, sw = mod_row(win, "Colour Mod")
    win.mods_page.list.select_row(row)
    win.mods_page.show_files()
    yield
    check("archive/pc/mod/colour_red.archive" in text(win).split("> samurai-mm info")[-1], "double-click lists a mod's files")
    win.mods_page.remove()
    yield
    check(len(win.mods) == 2 and not any("colour" in g for g in game_files()), "remove")
    # sorting: three mods of different sizes, one made the oldest
    big = SB / "dl" / "Zeta Big-444-1-0-1700000010.zip"
    with zipfile.ZipFile(big, "w") as z:
        z.writestr("archive/pc/mod/zeta.archive", "z" * 50000)
    win.stack.set_visible_child_name("install")
    win.install_page.update()
    select(win, "Zeta Big")
    win.install_page.add(False)
    yield
    win.stack.set_visible_child_name("mods")

    def order():
        out, i = [], 0
        while (r := win.mods_page.list.get_row_at_index(i)) is not None:
            out.append(r.mod["title"])
            i += 1
        return out
    keys = [k for k, _ in pages.SORT_CHOICES]
    check(order() == ["Fomod Test", "Plain Mod", "Zeta Big"], "mods are listed A to Z by default")
    win.mods_page.sort.set_selected(keys.index("size"))
    yield
    check(order()[0] == "Zeta Big", "sort: biggest first")
    win.mods_page.sort.set_selected(keys.index("recent"))
    yield
    row0 = win.mods_page.list.get_row_at_index(0)
    check(order()[0] == "Zeta Big" and "installed 20" in row0.get_child().get_first_child().get_next_sibling().get_last_child().get_label(),
          "sort: recently installed first, with the date shown")
    shot(win, "3b-sorted.png")
    row, sw = mod_row(win, "Fomod Test")
    sw.set_active(False)
    yield
    win.mods_page.sort.set_selected(keys.index("off"))
    yield
    check(order()[0] == "Fomod Test" and json.loads(engine.CONFIG.read_text()).get("sort") == "off", "sort: switched off first, and the choice is remembered")
    row, sw = mod_row(win, "Fomod Test")
    sw.set_active(True)
    yield
    win.mods_page.sort.set_selected(keys.index("name"))
    yield
    row, sw = mod_row(win, "Zeta Big")
    win.mods_page.list.select_row(row)
    win.mods_page.remove()
    yield
    check(order() == ["Fomod Test", "Plain Mod"], "back to A to Z; the extra mod removed")
    # the launch button talks to the Steam program directly
    asked = []
    real_launch, engine.launch_game = engine.launch_game, lambda game=None: asked.append(game) or ["/usr/bin/steam", "steam://rungameid/1091500"]
    win.status["steam"] = True
    win.launch()
    engine.launch_game = real_launch
    check(asked == [str(GAME)] and "asked Steam to start the game" in text(win), "launch goes to the Steam program, with the game's folder")
    # one button for the whole game folder
    win.toggle_all()
    yield
    check(game_files() == ["bin/x64/Cyberpunk2077.exe"] and win.mods_button.get_label() == "Put mods back"
          and "waiting to be put back" in win.summary.get_label(), "play without mods: everything out, button flips")
    win.toggle_all()
    yield
    check(all(m["state"] == "deployed" for m in win.mods) and win.mods_button.get_label() == "Play without mods", "put mods back")
    # health
    win.stack.set_visible_child_name("health")
    win.full_check()
    yield
    ids = {c["id"]: c["status"] for c in win.health + list(win.extra_checks.values())}
    check(ids.get("fw:redscript") == "fail" and ids.get("files") == "ok" and "logs" in ids and "problem" in win.health_summary.get_label(),
          "full check: finds the missing framework, verifies the files, reads the logs")
    shot(win, "4-health.png")
    (GAME / "archive/pc/mod/core.archive").write_text("damaged")
    win.full_check()
    yield
    check(win.extra_checks["files"]["status"] == "fail" and "1 differ" in win.extra_checks["files"]["detail"], "full check notices a damaged file")
    win.run(["deploy"], modifies=True)
    yield
    ACF.write_text('"AppState"\n{\n\t"buildid"\t\t"99999999"\n}\n')
    win.refresh(health=True)
    yield
    check({c["id"]: c["status"] for c in win.health}.get("build") == "fail" and ("build", 4) in win.health_page.buttons, "health reports a game update, with an Accept step")
    win.health_page.accept_build()
    yield
    check({c["id"]: c["status"] for c in win.health}.get("build") == "ok" and ("build", 4) not in win.health_page.buttons, "accept version clears it")
    # guided setup: a missing framework is walked through, from its Nexus page to installed
    hp = win.health_page
    card = {c["id"]: c for c in win.health}["fw:redscript"]
    check(card["status"] == "fail" and hp.buttons[("fw:redscript", 1)].get_label() == "Open its Nexus page"
          and hp.buttons[("fw:redscript", 2)].get_label() == "Waiting for the download"
          and not hp.buttons[("fw:redscript", 2)].get_sensitive(), "missing framework: page button, and install waits for the download")
    check("to sort out" in hp.hint.get_label(), "the Health tab says how many things are left to do")
    shot(win, "4b-guided.png")
    with zipfile.ZipFile(SB / "dl" / "redscript-1511-0-5-32-1700000020.zip", "w") as z:
        z.writestr("engine/tools/scc.exe", "MZ fake scc")
        z.writestr("engine/config/base/scripts.ini", "x")
    win.install_page.on_dir_changed()
    yield
    yield
    yield
    b = hp.buttons.get(("fw:redscript", 2))
    check(b is not None and b.get_label() == "Install this download" and b.get_sensitive(), "the install step lights up when the download arrives")
    b.emit("clicked")
    yield
    check({c["id"]: c["status"] for c in win.health}.get("fw:redscript") == "ok" and "engine/tools/scc.exe" in game_files(),
          "one click installs it and the entry turns OK")
    copied = []
    hp.copy = lambda text: copied.append(text)
    b = hp.action_button({"type": "copy", "label": "Copy the line", "text": "WINEDLLOVERRIDES=x"})
    b.emit("clicked")
    opened = []
    real_open, engine.steam_open = engine.steam_open, lambda url, game=None: opened.append(url) or ["steam", url]
    hp.action_button({"type": "steam", "label": "Open Steam properties", "url": "steam://gameproperties/1091500"}).emit("clicked")
    engine.steam_open = real_open
    spawned = []
    real_spawn, real_term = engine.spawn_detached, engine.terminal_command
    engine.spawn_detached, engine.terminal_command = (lambda cmd: spawned.append(cmd)), (lambda c: ["konsole", "-e", "sh", "-c", c])
    tb = hp.action_button({"type": "terminal", "label": "Install it in a terminal", "command": "sudo pacman -S --needed 7zip"})
    tb.emit("clicked")
    engine.terminal_command = lambda c: None
    nb = hp.action_button({"type": "terminal", "label": "Install it in a terminal", "command": "sudo pacman -S --needed 7zip"})
    engine.spawn_detached, engine.terminal_command = real_spawn, real_term
    check(copied == ["WINEDLLOVERRIDES=x"] and opened == ["steam://gameproperties/1091500"]
          and spawned == [["konsole", "-e", "sh", "-c", "sudo pacman -S --needed 7zip"]] and nb.get_label() == "Copy the command",
          "step buttons: copy, open Steam, run in a terminal (or copy the command when there is no terminal)")
    del hp.copy
    # settings
    win.stack.set_visible_child_name("settings")
    if ART:
        win.save_setting("artwork", ART)
        yield
        check(win.settings_page.values["artwork"].get_label() == ART, "side panel picture can be set")
    yield
    check(not win.settings_page.saved.get_visible(), "saved-settings card hidden when the store has none")
    shot(win, "5-settings.png")
    # game running
    pretend["running"] = True
    win.check_game()
    win.stack.set_visible_child_name("mods")
    yield
    b = buttons(win)
    check(win.banner.get_visible() and not b["Install"] and not b["Launch the game"] and not b["Play without mods"] and b["Dry run"]
          and b["Run full check"] and not any(s.get_sensitive() for s in win.mods_page.switches),
          "game running: everything that changes the game is off, checks stay on")
    shot(win, "6-game-running.png")
    pretend["running"] = False
    win.check_game()
    yield
    check(not win.banner.get_visible() and all(s.get_sensitive() for s in win.mods_page.switches), "game closed: back on")
    # the chosen download disappears, then the folder empties
    win.stack.set_visible_child_name("install")
    select(win, "Fomod Test")
    yield
    check(win.install_page.source is not None and buttons(win)["Install"], "a download is chosen")
    for f in (SB / "dl").iterdir():
        f.unlink()
    win.install_page.update()
    yield
    first = win.install_page.list.get_row_at_index(0)
    check(win.install_page.source is None and not buttons(win)["Install"], "a download that vanished is no longer the chosen one")
    check(first is not None and first.path is None and "No zip" in first.get_child().get_label(), "an empty downloads folder says so")
    shot(win, "7-empty-downloads.png")
    print("buttons in the window:", sorted(buttons(win)), flush=True)


def pump(win, gen):
    def tick():
        if win.busy or win.runner.queue:
            return True
        try:
            next(gen)
        except StopIteration:
            print("FAILED: %d" % len(fails) if fails else "ALL PASSED", flush=True)
            app.quit()
            return False
        except BaseException:
            import traceback
            traceback.print_exc()
            fails.append("crashed")
            app.quit()
            return False
        return True
    GLib.timeout_add(350, tick)


app.connect_after("activate", lambda *_: pump(app.win, (firstrun if MODE == "firstrun" else flows)(app.win)))
app.run([])
sys.exit(1 if fails else 0)
