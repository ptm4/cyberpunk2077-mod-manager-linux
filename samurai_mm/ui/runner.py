# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Runs engine commands one after another as separate processes and hands their output back line by line."""
import os
import re
import shlex
import sys
from pathlib import Path

from gi.repository import Gio, GLib

PKG_PARENT = Path(__file__).resolve().parent.parent.parent


def tag_for(line):
    """Which colour a line of engine output gets in the output pane."""
    s = line.strip()
    if s.startswith("[PASS]") or re.match(
            r"(verify: (\d+)/\2 identical, 0 missing, 0 differ, 0 case)|deployed |added |enabled |created |recorded |doctor: 0 problems, 0 warn", s):
        return "ok"
    if s.startswith(("error:", "[FAIL]", "BAD", "MISSING", "DIFFERS", "CASE-DUPLICATE", "refusing", "not adding",
                     "not enabling", "Traceback", "verify:")):
        return "err"
    if s.startswith(("dry run:", "would remove", "[WARN]", "doctor:")):
        return "dry"
    if s.startswith(("note:", "[INFO]", "fix:")):
        return "note"
    return None


class Runner:
    def __init__(self, show, on_busy, global_args=()):
        self.show = show            # show(text, tag)
        self.on_busy = on_busy      # on_busy(bool)
        self.global_args = list(global_args)
        self.queue = []
        self.busy = False

    def run(self, args, done=None, quiet=False, shown=None):
        """Queue `samurai-mm <args>`. done(exit_code, lines) is called when it ends. quiet hides it from the output pane."""
        label = None if quiet else (shown or "samurai-mm " + shlex.join(args))
        self.queue.append(([sys.executable, "-m", "samurai_mm"] + self.global_args + list(args), label, done or (lambda c, l: None)))
        if not self.busy:
            self._next()

    def _set_busy(self, busy):
        self.busy = busy
        self.on_busy(busy)

    def _next(self):
        if not self.queue:
            self._set_busy(False)
            return
        argv, shown, done = self.queue.pop(0)
        self._set_busy(True)
        if shown:
            self.show("\n> " + shown, "cmd")
        lines = []
        try:
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
            launcher.setenv("PYTHONUNBUFFERED", "1", True)
            launcher.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(PKG_PARENT), os.environ.get("PYTHONPATH")])), True)
            proc = launcher.spawnv(argv)
        except GLib.Error as e:
            self.show(f"error: could not start the command: {e.message}", "err")
            done(127, lines)
            self._next()
            return
        pipe = proc.get_stdout_pipe()
        pending = [b""]

        def finished(p, res):
            try:
                p.wait_finish(res)
                code = p.get_exit_status() if p.get_if_exited() else 1
            except GLib.Error:
                code = 1
            if shown:
                self.show("finished" if code == 0 else f"stopped with exit code {code}", "note" if code == 0 else "err")
            done(code, lines)
            self._next()

        def emit(raw):
            line = raw.decode("utf-8", "replace").rstrip("\r")
            lines.append(line)
            if shown:
                self.show(line, tag_for(line))

        def got_data(s, res):
            # Raw reads split into lines here: DataInputStream.read_line cannot tell end-of-stream from an empty line in PyGObject.
            try:
                data = s.read_bytes_finish(res).get_data() or b""
            except GLib.Error:
                data = b""
            if not data:
                if pending[0]:
                    emit(pending[0])
                proc.wait_async(None, finished)
                return
            *whole, pending[0] = (pending[0] + data).split(b"\n")
            for raw in whole:
                emit(raw)
            s.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, None, got_data)

        pipe.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, None, got_data)
