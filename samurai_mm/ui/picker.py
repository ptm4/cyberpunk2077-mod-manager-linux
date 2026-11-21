# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""The chooser shown when a download holds several variants or an installer with choices."""
import os
import shutil
import time
from pathlib import Path

from gi.repository import GLib, Gtk

from .. import engine
from . import variants, widgets

CACHE = Path(GLib.get_user_cache_dir()) / "samurai-mm"


class Picker(Gtk.Window):
    def __init__(self, win, src: Path, name: str, flags):
        super().__init__(title="Choose what to install", transient_for=win, modal=True,
                         default_width=640, default_height=560)
        self.add_css_class("cp")
        self.win, self.src, self.name, self.flags = win, src, name, flags
        self.work = CACHE / f"pick-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        self.fomod = None
        self.base = None
        self.group_widgets = []   # installer: (group, [(plugin, checkbutton)])
        self.layout_checks = []   # otherwise: (folder, checkbutton)
        self.loose_checks = []    # otherwise: (file, checkbutton)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                        margin_start=16, margin_end=16)
        self.set_child(outer)
        outer.append(widgets.label(name, "picker-title", wrap=True))
        self.intro = widgets.label("Unpacking the download ...", "dim", wrap=True)
        outer.append(self.intro)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sc.set_child(self.body)
        outer.append(sc)
        self.msg = widgets.label("", "state-bad", wrap=True)
        outer.append(self.msg)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.b_dry = widgets.button("Dry run", lambda *_: self.go(True))
        self.b_go = widgets.button("Install", lambda *_: self.go(False), "primary")
        for b in (widgets.button("Close", lambda *_: self.close()), self.b_dry, self.b_go):
            row.append(b)
        outer.append(row)
        self.b_dry.set_sensitive(False)
        self.b_go.set_sensitive(False)
        self.connect("close-request", self.on_close)

        CACHE.mkdir(parents=True, exist_ok=True)
        win.run(["unpack", "--", str(src), str(self.work / "src")], self.unpacked, shown=f"unpack \"{src.name}\" to choose from it")

    def on_close(self, *_):
        shutil.rmtree(self.work, ignore_errors=True)
        return False

    def has_options(self):
        return bool(self.fomod or self.layout_checks or self.loose_checks)

    def note(self, text):
        lab = widgets.label(text, "dim", "small", wrap=True)
        lab.set_margin_start(28)
        self.body.append(lab)

    def later(self):
        GLib.idle_add(lambda: self.refresh_buttons() and False)

    def unpacked(self, code, lines):
        if code != 0:
            self.intro.set_label("The download could not be unpacked. The reason is in the output pane.")
            return
        root = self.work / "src"
        self.base, cfg = variants.find_fomod(root)
        if cfg:
            try:
                self.fomod = variants.parse_fomod(cfg)
            except ValueError as e:
                self.msg.set_label(f"This download has an installer, but {e}. Pick the folders or files by hand instead.")
        if self.fomod:
            self.build_fomod()
        else:
            self.build_generic(root)
        self.later()

    def build_fomod(self):
        self.intro.set_label("This download has an installer with choices. These are its options, as its author named them.")
        last_step = None
        for g in self.fomod["groups"]:
            if g["step"] and g["step"] != last_step:
                self.body.append(widgets.section(g["step"]))
                last_step = g["step"]
            hint = {"SelectExactlyOne": "pick one", "SelectAtMostOne": "pick one or none", "SelectAtLeastOne": "pick at least one",
                    "SelectAll": "all of these are installed", "SelectAny": "pick any"}.get(g["type"], "pick any")
            head = widgets.label(f"{g['name'] or 'Options'}  ({hint})", "strong", wrap=True)
            head.set_margin_top(4)
            self.body.append(head)
            radio = g["type"] in ("SelectExactlyOne", "SelectAtMostOne")
            first, checks = None, []
            if g["type"] == "SelectAtMostOne":
                first = Gtk.CheckButton(label="None of these", active=True)
                self.body.append(first)
            for p in g["plugins"]:
                cb = Gtk.CheckButton(label=p["name"])
                if radio:
                    if first is None:
                        first = cb
                    else:
                        cb.set_group(first)
                if g["type"] == "SelectAll" or p["type"] == "Required":
                    cb.set_active(True)
                    cb.set_sensitive(False)
                elif p["type"] == "Recommended":
                    cb.set_active(True)
                cb.connect("toggled", lambda *_: self.refresh_buttons())
                self.body.append(cb)
                if p["desc"]:
                    self.note(p["desc"][:400])
                checks.append((p, cb))
            if g["type"] == "SelectExactlyOne" and not any(cb.get_active() for _, cb in checks):
                checks[0][1].set_active(True)
            self.group_widgets.append((g, checks))
        if self.fomod["required"]:
            self.note("The installer's required files are always included.")

    def build_generic(self, root: Path):
        layout, loose = variants.scan_candidates(root)
        if not layout and not loose:
            self.intro.set_label("Nothing in this download looks installable: no folders in game layout "
                                 "(archive, bin, r6, red4ext ...) and no .archive files.")
            return
        self.intro.set_label("It is not clear which files in this download to install. "
                             "Tick what you want; a dry run shows exactly where each file would go.")
        if layout:
            self.body.append(widgets.section("Folders in game layout"))
            for d in layout:
                rel = d.relative_to(root).as_posix()
                cb = Gtk.CheckButton(label=f"{'(top level)' if rel == '.' else rel}   -   {len(variants.files_under(d))} files")
                cb.connect("toggled", lambda *_: self.refresh_buttons())
                self.body.append(cb)
                self.layout_checks.append((d, cb))
        if loose:
            self.body.append(widgets.section("Loose mod files (these go into archive/pc/mod)"))
            only_one = len(loose) == 1 and not layout
            for d, files in loose:
                rel = d.relative_to(root).as_posix()
                if rel != ".":
                    lab = widgets.label(rel, "path", wrap=True)
                    lab.set_margin_top(4)
                    self.body.append(lab)
                for f in files:
                    cb = Gtk.CheckButton(label=f"{f.name}   -   {engine.human_size(f.stat().st_size)}")
                    # One folder with one mod file (plus pictures or notes) is not really a choice.
                    if only_one and len([x for x in files if x.suffix.lower() == ".archive"]) == 1:
                        cb.set_active(True)
                    cb.connect("toggled", lambda *_: self.refresh_buttons())
                    self.body.append(cb)
                    self.loose_checks.append((f, cb))

    def collect(self):
        """Return (pairs of (file, game-relative path), labels of what was chosen, problem text)."""
        if self.fomod:
            entries, flags, labels = list(self.fomod["required"]), {}, []
            for g, checks in self.group_widgets:
                chosen = [p for p, cb in checks if cb.get_active()]
                if g["type"] == "SelectExactlyOne" and len(chosen) != 1:
                    return [], [], f"Pick one option under \"{g['name']}\"."
                if g["type"] == "SelectAtLeastOne" and not chosen:
                    return [], [], f"Pick at least one option under \"{g['name']}\"."
                for p in chosen:
                    entries += p["files"]
                    flags.update(p["flags"])
                    labels.append(p["name"])
            for op, deps, files in self.fomod["patterns"]:
                hits = [flags.get(f) == v for f, v in deps]
                if hits and (all(hits) if op.lower() == "and" else any(hits)):
                    entries += files
            pairs, missing = variants.resolve_entries(self.base, entries)
            if missing:
                return [], [], "The installer points at files that are not in the download: " + ", ".join(missing[:5])
            if not pairs:
                return [], [], "The chosen options contain no files."
            return pairs, labels, ""
        pairs, labels = [], []
        for d, cb in self.layout_checks:
            if cb.get_active():
                labels.append(d.name)
                pairs += [(f, f.relative_to(d).as_posix()) for f in variants.files_under(d)]
        for f, cb in self.loose_checks:
            if cb.get_active():
                labels.append(f.name)
                pairs.append((f, "archive/pc/mod/" + f.name))
        return pairs, labels, "" if pairs else "Nothing is ticked yet."

    def refresh_buttons(self):
        pairs, _, problem = self.collect() if self.has_options() else ([], [], "")
        ok = bool(pairs) and not self.win.busy
        self.b_dry.set_sensitive(ok)
        self.b_go.set_sensitive(ok and not self.win.game_is_running)
        if self.has_options():
            self.msg.set_label("" if pairs else problem)

    def go(self, dry):
        pairs, labels, problem = self.collect()
        if problem:
            self.msg.set_label(problem)
            return
        stage = self.work / "stage" / self.name
        shutil.rmtree(stage.parent, ignore_errors=True)
        stage.mkdir(parents=True)
        for src, rel in pairs:
            dst = variants.ci_target(stage, rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst.unlink()
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        self.win.out(f"chosen from \"{self.src.name}\": {'; '.join(labels)}  ({len(pairs)} files arranged in {stage})", "note")
        args = ["add", "--name=" + self.name] + self.flags
        if self.src.is_file():
            args.append("--keep-archive=" + str(self.src))
        if dry:
            args.append("--dry-run")
        args += ["--", str(stage)]
        self.b_dry.set_sensitive(False)
        self.b_go.set_sensitive(False)

        def done(code, lines):
            if code == 0 and not dry:
                self.close()
            else:
                self.later()

        self.win.run(args, done, modifies=not dry)
