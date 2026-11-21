# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""Hostile and awkward inputs: archives built to write where they should not, odd names, damaged files,
two commands at once, installs that are not on Steam. Everything runs in a temporary folder."""
import fcntl
import json
import os
import stat
import subprocess
import sys
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_engine import HAVE_UNPACKER, Sandbox  # noqa: E402

from samurai_mm import engine  # noqa: E402


@unittest.skipUnless(HAVE_UNPACKER, "needs 7z or bsdtar")
class Hostile(Sandbox):
    def setUp(self):
        super().setUp()
        self.run_cli("init")

    def nothing_changed(self):
        self.assertEqual(self.mods(), {})
        self.assertEqual(self.game_files(), ["bin/x64/Cyberpunk2077.exe"])
        self.assertEqual([p.name for p in self.tmp.rglob("escaped*")], [])
        self.assertEqual(list((self.store / "incoming").glob("*")) if (self.store / "incoming").is_dir() else [], [])

    def test_parent_folder_entries_refused(self):
        for bad in ("../../escaped.txt", "archive/../../escaped.txt", "archive\\..\\..\\escaped.txt"):
            z = self.make_zip("traversal.zip", {"archive/pc/mod/ok.archive": "ok", bad: "evil"})
            self.assertIn("points outside the mod folder", self.run_cli("add", str(z), ok=False), bad)
            self.nothing_changed()

    def test_absolute_path_refused(self):
        target = self.tmp / "escaped-abs.txt"
        z = self.make_zip("absolute.zip", {"archive/pc/mod/ok.archive": "ok", str(target): "evil"})
        self.assertIn("points outside the mod folder", self.run_cli("add", str(z), ok=False))
        self.nothing_changed()

    def test_link_refused(self):
        z = self.dl / "link.zip"
        with zipfile.ZipFile(z, "w") as f:
            zi = zipfile.ZipInfo("archive/pc/mod/link")
            zi.create_system = 3
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            f.writestr(zi, str(self.home))
            f.writestr("archive/pc/mod/ok.archive", "ok")
        self.assertIn("contains a link", self.run_cli("add", str(z), ok=False))
        self.nothing_changed()

    def test_folder_with_link_refused(self):
        d = self.dl / "folder mod"
        (d / "archive/pc/mod").mkdir(parents=True)
        (d / "archive/pc/mod/a.archive").write_text("a")
        os.symlink(self.home, d / "archive/pc/mod/home")
        self.assertIn("contains a link", self.run_cli("add", str(d), ok=False))
        self.nothing_changed()

    def test_control_characters_refused(self):
        z = self.make_zip("control.zip", {"archive/pc/mod/new\nline.archive": "x"})
        self.assertIn("control characters", self.run_cli("add", str(z), ok=False))
        self.nothing_changed()

    def test_windows_backslash_paths_are_understood(self):
        z = self.make_zip("Backslash Mod.zip", {"archive\\pc\\mod\\bs.archive": "x", "r6\\scripts\\bs.reds": "y"})
        self.run_cli("add", str(z))
        self.assertEqual(self.game_files(), ["archive/pc/mod/bs.archive", "bin/x64/Cyberpunk2077.exe", "r6/scripts/bs.reds"])

    def test_archive_bigger_than_the_disk_refused(self):
        with self.assertRaises(SystemExit) as e:
            engine.vet_listing("bomb.zip", [("archive/pc/mod/a.archive", 10 ** 15, False)], free_bytes=10 ** 9)
        self.assertIn("only", str(e.exception))
        with self.assertRaises(SystemExit):
            engine.vet_listing("many.zip", [("a", 0, False)] * (engine.MAX_ARCHIVE_ENTRIES + 1), free_bytes=None)

    def test_seven_zip_archive_is_vetted_too(self):
        tool = engine.seven_zip()
        if not tool:
            self.skipTest("needs 7z")
        src = self.tmp / "src"
        (src / "archive/pc/mod").mkdir(parents=True)
        (src / "archive/pc/mod/z.archive").write_text("z")
        subprocess.run([tool, "a", "-bso0", "-bsp0", str(self.dl / "Seven-5-1-0-1700000000.7z"), "."], cwd=src, check=True)
        listing = engine.list_archive(self.dl / "Seven-5-1-0-1700000000.7z")
        self.assertIn(("archive/pc/mod/z.archive", 1, False), listing)
        self.run_cli("add", str(self.dl / "Seven-5-1-0-1700000000.7z"))
        self.assertIn("archive/pc/mod/z.archive", self.game_files())

    def test_damaged_archive(self):
        (self.dl / "damaged.zip").write_bytes(b"PK\x03\x04 this is not a zip" * 10)
        out = self.run_cli("add", str(self.dl / "damaged.zip"), ok=False)
        self.assertIn("error: could not", out)
        self.assertNotIn("Traceback", out)
        self.nothing_changed()

    def test_bad_names(self):
        z = self.make_zip("ok.zip", {"archive/pc/mod/ok.archive": "ok"})
        self.assertIn("too long", self.run_cli("add", str(z), "--name", "x" * 300, ok=False))
        self.assertIn("cannot be used", self.run_cli("add", str(z), "--name", "bad\nname", ok=False))
        self.assertIn("cannot be used", self.run_cli("add", str(z), "--name", "a/b", ok=False))
        self.nothing_changed()

    def test_names_starting_with_a_dash(self):
        for name in ("-dash", "--help", "- Head Thing-1-2-1700000000"):
            z = self.make_zip(name + ".zip", {f"archive/pc/mod/{abs(hash(name))}.archive": "x"})
            self.run_cli("add", "--", str(z))
            self.run_cli("disable", "--", name)
            self.assertEqual(self.mods()[name]["state"], "disabled")
            self.run_cli("enable", "--", name)
            self.run_cli("info", "--", name)
            newer = self.make_zip(name + " v2.zip", {f"archive/pc/mod/{abs(hash(name))}.archive": "y"})
            self.run_cli("add", "--update=" + name, "--", str(newer))
            self.run_cli("remove", "--", name + " v2")
        self.assertEqual(self.mods(), {})

    def test_damaged_mod_list_gives_advice(self):
        self.run_cli("add", str(self.make_zip("ok.zip", {"archive/pc/mod/ok.archive": "ok"})))
        (self.store / "manifest.json").write_text("{ not json")
        out = self.run_cli("list", ok=False)
        self.assertIn("is damaged", out)
        self.assertIn("backups", out)
        self.assertNotIn("Traceback", out)
        self.assertTrue(list((self.store / "backups" / "manifest").glob("manifest-*.json")))

    def test_game_folder_not_writable(self):
        z = self.make_zip("ro.zip", {"r6/scripts/ro.reds": "x"})
        os.chmod(self.game, 0o555)
        try:
            out = self.run_cli("add", str(z), ok=False)
        finally:
            os.chmod(self.game, 0o755)
        self.assertIn("no permission to write", out)
        self.assertNotIn("Traceback", out)
        self.assertIn("deployed", self.run_cli("deploy"))       # once fixed, running again finishes the job
        self.run_cli("verify")

    def test_two_commands_at_once_both_land(self):
        zips = [self.make_zip(f"Par{i}.zip", {f"archive/pc/mod/par{i}.archive": "x" * 1000}) for i in range(4)]
        outs = {}
        threads = [threading.Thread(target=lambda z=z: outs.__setitem__(z.name, self.run_cli("add", str(z), ok=None))) for z in zips]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(self.mods()), ["Par0", "Par1", "Par2", "Par3"], outs)
        self.run_cli("verify")

    def test_busy_store_is_reported(self):
        self.env["SAMURAI_MM_LOCK_WAIT"] = "0.5"
        with open(self.store / ".lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            out = self.run_cli("add", str(self.make_zip("ok.zip", {"archive/pc/mod/ok.archive": "ok"})), ok=False)
            self.assertIn("still working on this mod store", out)
            self.run_cli("list")                                  # reading never waits
            self.assertIn("would add", self.run_cli("add", str(self.dl / "ok.zip"), "--dry-run"))
        self.run_cli("add", str(self.dl / "ok.zip"))

    def test_undeploy_when_the_game_folder_is_gone(self):
        self.run_cli("add", str(self.make_zip("ok.zip", {"archive/pc/mod/ok.archive": "ok"})))
        os.rename(self.game, self.game.with_name("moved away"))
        out = self.run_cli("--game", str(self.game.with_name("moved away")), "undeploy", ok=False)
        self.assertIn("is gone", out)
        self.assertNotIn("Traceback", out)


class OtherLaunchers(Sandbox):
    def move_game_out_of_steam(self):
        gog = self.tmp / "Games/Heroic/Cyberpunk 2077"
        gog.parent.mkdir(parents=True)
        os.rename(self.game, gog)
        return gog

    def test_heroic_gog_install_is_found(self):
        gog = self.move_game_out_of_steam()
        f = self.home / ".config/heroic/gog_store/installed.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"installed": [{"appName": "1", "install_path": "/nowhere"}, {"appName": "1423049311", "install_path": str(gog)}]}))
        st = json.loads(self.run_cli("status", "--json"))
        self.assertEqual((st["game"], st["steam"]), (str(gog), False))

    def test_lutris_install_is_found(self):
        gog = self.move_game_out_of_steam()
        f = self.home / ".config/lutris/games/cyberpunk-2077-123.yml"
        f.parent.mkdir(parents=True)
        f.write_text(f"game:\n  exe: {gog}/bin/x64/Cyberpunk2077.exe\n  prefix: /somewhere\n")
        self.assertEqual(json.loads(self.run_cli("status", "--json"))["game"], str(gog))

    @unittest.skipUnless(HAVE_UNPACKER, "needs 7z or bsdtar")
    def test_non_steam_install_works_and_gets_fitting_advice(self):
        gog = self.move_game_out_of_steam()
        self.run_cli("--game", str(gog), "init")
        z = self.make_zip("Mod.zip", {"archive/pc/mod/m.archive": "m"})
        self.assertIn("verify: 1/1 identical", self.run_cli("--game", str(gog), "add", str(z)))
        for rel in ("red4ext/RED4ext.dll", "bin/x64/winmm.dll"):
            (gog / rel).parent.mkdir(parents=True, exist_ok=True)
            (gog / rel).write_text("x")
        checks = {c["id"]: c for c in json.loads(self.run_cli("--game", str(gog), "doctor", "--json"))}
        self.assertEqual(checks["launch"]["status"], "info")
        self.assertIn("Heroic", checks["launch"]["fix"])
        self.assertEqual(checks["prefix"]["status"], "info")
        self.assertEqual(checks["build"]["status"], "ok")
        (gog / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ a patched exe")       # a game update without Steam
        checks = {c["id"]: c for c in json.loads(self.run_cli("--game", str(gog), "doctor", "--json"))}
        self.assertEqual(checks["build"]["status"], "fail")

    def test_store_suggested_next_to_a_game_on_another_disk(self):
        self.assertEqual(engine.suggest_store(None), engine.DEFAULT_STORE)
        if os.stat("/dev/shm").st_dev != os.stat(self.tmp).st_dev and os.access("/dev/shm", os.W_OK):
            import tempfile
            other = Path(tempfile.mkdtemp(dir="/dev/shm"))
            self.addCleanup(__import__("shutil").rmtree, other, ignore_errors=True)
            game = other / "SteamLibrary/steamapps/common/Cyberpunk 2077"
            game.mkdir(parents=True)
            if os.stat(engine.DATA_HOME if engine.DATA_HOME.exists() else Path.home()).st_dev != os.stat(game).st_dev:
                self.assertEqual(engine.suggest_store(game), other / "SteamLibrary/samurai-mm-store")


if __name__ == "__main__":
    unittest.main()
