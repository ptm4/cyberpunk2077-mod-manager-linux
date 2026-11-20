"""Engine tests. Everything runs in a temporary folder with a fake game; nothing real is touched.

Run from the project folder:  python3 -m unittest discover -s dev/tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from samurai_mm import doctor, engine  # noqa: E402

HAVE_UNPACKER = any(shutil.which(t) for t in ("7z", "7zz", "7za", "bsdtar"))


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="samurai-mm-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.steam = self.home / ".local/share/Steam"
        self.game = self.steam / "steamapps/common/Cyberpunk 2077"
        (self.game / "bin/x64").mkdir(parents=True)
        (self.game / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ fake")
        self.set_build("1000")
        self.store = self.tmp / "store"
        self.dl = self.tmp / "dl"
        self.dl.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                        PYTHONPATH=str(ROOT), SAMURAI_MM_ASSUME_GAME_CLOSED="1")

    def set_build(self, build):
        (self.steam / "steamapps/appmanifest_1091500.acf").write_text('"AppState"\n{\n\t"buildid"\t\t"%s"\n}\n' % build)

    def run_cli(self, *args, ok=True):
        r = subprocess.run([sys.executable, "-m", "samurai_mm", "--store", str(self.store), *args],
                           capture_output=True, text=True, env=self.env)
        if ok is not None:
            self.assertEqual(r.returncode == 0, ok, f"{args}: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r.stdout + r.stderr

    def make_zip(self, name, files):
        p = self.dl / name
        with zipfile.ZipFile(p, "w") as z:
            for rel, data in files.items():
                z.writestr(rel, data)
        return p

    def game_files(self):
        return sorted(p.relative_to(self.game).as_posix() for p in self.game.rglob("*") if p.is_file())

    def mods(self):
        return {m["name"]: m for m in json.loads(self.run_cli("list", "--json"))}


@unittest.skipUnless(HAVE_UNPACKER, "needs 7z or bsdtar")
class EngineFlow(Sandbox):
    def setUp(self):
        super().setUp()
        self.run_cli("init")
        self.a = self.make_zip("Mod A-11-1-0-1700000000.zip", {"archive/pc/mod/a.archive": "aaa", "r6/scripts/a.reds": "x", "readme.txt": "hi"})
        self.b = self.make_zip("Mod B-22-2-1-1700000001.zip", {"archive/pc/mod/b.archive": "bbb"})

    def test_init_twice_refused(self):
        self.assertIn("already a mod store", self.run_cli("init", ok=False))

    def test_add_dry_run_changes_nothing(self):
        out = self.run_cli("add", str(self.a), "--dry-run")
        self.assertIn("would add 2 files", out)
        self.assertEqual(self.game_files(), ["bin/x64/Cyberpunk2077.exe"])
        self.assertEqual(self.mods(), {})

    def test_add_deploys_and_keeps_archive(self):
        out = self.run_cli("add", str(self.a))
        self.assertIn("verify: 2/2 identical", out)
        self.assertIn("archive/pc/mod/a.archive", self.game_files())
        self.assertNotIn("readme.txt", self.game_files())
        self.assertTrue((self.store / "archives" / self.a.name).is_file())
        m = self.mods()["Mod A-11-1-0-1700000000"]
        self.assertEqual((m["state"], m["files"], m["nexus_id"], m["version"]), ("deployed", 2, 11, "1.0"))

    def test_disable_enable_roundtrip(self):
        self.run_cli("add", str(self.a))
        self.run_cli("add", str(self.b))
        self.assertIn("disabled 'Mod A", self.run_cli("disable", "mod a"))
        self.assertEqual(self.game_files(), ["archive/pc/mod/b.archive", "bin/x64/Cyberpunk2077.exe"])
        self.assertEqual(self.mods()["Mod A-11-1-0-1700000000"]["state"], "disabled")
        self.assertTrue((self.store / "mods/Mod A-11-1-0-1700000000/archive/pc/mod/a.archive").is_file())
        self.run_cli("verify")            # disabled mods are not expected in the game
        self.run_cli("deploy")            # and deploy does not bring them back
        self.assertNotIn("archive/pc/mod/a.archive", self.game_files())
        self.assertIn("enabled 'Mod A", self.run_cli("enable", "mod a"))
        self.assertIn("r6/scripts/a.reds", self.game_files())
        self.assertEqual(self.mods()["Mod A-11-1-0-1700000000"]["state"], "deployed")
        self.run_cli("verify")

    def test_clash_refused_and_enable_checks_too(self):
        self.run_cli("add", str(self.a))
        clash = self.make_zip("Clash-33-1-1700000002.zip", {"archive/pc/mod/A.archive": "other"})
        self.assertIn("already installed by: Mod A", self.run_cli("add", str(clash), ok=False))
        self.run_cli("disable", "Mod A")
        self.run_cli("add", str(clash))
        self.assertIn("not enabling", self.run_cli("enable", "Mod A", ok=False))
        self.assertEqual(self.mods()["Mod A-11-1-0-1700000000"]["state"], "disabled")

    def test_foreign_file_not_overwritten(self):
        (self.game / "archive/pc/mod").mkdir(parents=True)
        (self.game / "archive/pc/mod/a.archive").write_text("by hand")
        self.assertIn("something else put there", self.run_cli("add", str(self.a), ok=False))
        self.assertEqual((self.game / "archive/pc/mod/a.archive").read_text(), "by hand")

    def test_case_insensitive_merge(self):
        (self.game / "Archive/PC/Mod").mkdir(parents=True)
        self.run_cli("add", str(self.a))
        self.assertIn("Archive/PC/Mod/a.archive", self.game_files())
        self.assertFalse((self.game / "archive").exists())

    def test_replace_and_remove(self):
        self.run_cli("add", str(self.a))
        new = self.make_zip("Mod A-11-1-1-1700000009.zip", {"archive/pc/mod/a.archive": "v2", "archive/pc/mod/a2.archive": "more"})
        self.assertIn("already in the store", self.run_cli("add", str(new), "--name", "Mod A-11-1-0-1700000000", ok=False))
        self.run_cli("add", str(new), "--replace", "--name", "Mod A-11-1-0-1700000000")
        self.assertEqual((self.game / "archive/pc/mod/a.archive").read_text(), "v2")
        self.assertNotIn("r6/scripts/a.reds", self.game_files())
        self.assertIn("dry run", self.run_cli("remove", "Mod A", "--dry-run"))
        self.run_cli("remove", "Mod A")
        self.assertEqual(self.game_files(), ["bin/x64/Cyberpunk2077.exe"])
        self.assertEqual(self.mods(), {})
        self.assertEqual(len(list((self.store / "removed").iterdir())), 2)

    def test_update_replaces_the_old_version(self):
        self.run_cli("add", str(self.a))
        new = self.make_zip("Mod A-11-1-1-1700000009.zip", {"archive/pc/mod/a.archive": "v2", "archive/pc/mod/a2.archive": "more"})
        self.assertIn("already installed by: Mod A-11-1-0", self.run_cli("add", str(new), ok=False))
        out = self.run_cli("add", str(new), "--update", "Mod A-11-1-0-1700000000", "--dry-run")
        self.assertIn("replacing 'Mod A-11-1-0-1700000000'", out)
        self.assertEqual(list(self.mods()), ["Mod A-11-1-0-1700000000"])
        self.run_cli("add", str(new), "--update", "Mod A-11-1-0-1700000000")
        self.assertEqual(list(self.mods()), ["Mod A-11-1-1-1700000009"])
        self.assertEqual(self.mods()["Mod A-11-1-1-1700000009"]["version"], "1.1")
        self.assertEqual((self.game / "archive/pc/mod/a.archive").read_text(), "v2")
        self.assertNotIn("r6/scripts/a.reds", self.game_files())
        self.run_cli("verify")

    def test_remove_disabled_mod(self):
        self.run_cli("add", str(self.a))
        self.run_cli("disable", "Mod A")
        self.run_cli("remove", "Mod A")
        self.assertEqual(self.mods(), {})

    def test_undeploy_and_deploy(self):
        self.run_cli("add", str(self.a))
        self.assertIn("would remove 2 files", self.run_cli("undeploy", "--dry-run"))
        self.run_cli("undeploy")
        self.assertEqual(self.game_files(), ["bin/x64/Cyberpunk2077.exe"])
        self.assertIn("2 missing", self.run_cli("verify", ok=False))
        self.assertIn("would place 2 files", self.run_cli("deploy", "--dry-run"))
        self.run_cli("deploy")
        self.run_cli("verify")

    def test_game_update_blocks_until_accepted(self):
        self.run_cli("add", str(self.a))
        self.set_build("2000")
        self.assertIn("game was updated", self.run_cli("deploy", ok=False))
        self.assertIn("fail", [c["status"] for c in json.loads(self.run_cli("doctor", "--json")) if c["id"] == "build"])
        self.assertIn("recorded game build 2000", self.run_cli("accept-build"))
        self.run_cli("deploy")

    def test_variant_archive_refused(self):
        v = self.make_zip("Variants.zip", {"Pack/Red/red.archive": "r", "Pack/Blue/blue.archive": "b"})
        self.assertIn("cannot tell where", self.run_cli("add", str(v), ok=False))
        f = self.make_zip("Fomod.zip", {"fomod/ModuleConfig.xml": "<config/>", "A/a.archive": "a"})
        self.assertIn("installer with choices", self.run_cli("add", str(f), ok=False))

    def test_doctor_requirements_and_launch_options(self):
        self.run_cli("add", str(self.a))
        checks = {c["id"]: c for c in json.loads(self.run_cli("doctor", "--json"))}
        self.assertEqual(checks["fw:redscript"]["status"], "fail")      # a.reds needs redscript
        self.assertEqual(checks["fw:ArchiveXL"]["status"], "info")
        self.assertEqual(checks["unmanaged"]["status"], "ok")
        # install fake RED4ext + CET by hand: frameworks present, launch options and runtimes missing
        for rel in ("red4ext/RED4ext.dll", "bin/x64/winmm.dll", "bin/x64/version.dll", "bin/x64/plugins/cyber_engine_tweaks.asi"):
            (self.game / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.game / rel).write_text("x")
        pfx = self.steam / "steamapps/compatdata/1091500/pfx"
        pfx.mkdir(parents=True)
        checks = {c["id"]: c for c in json.loads(self.run_cli("doctor", "--json"))}
        self.assertEqual(checks["launch"]["status"], "warn")
        self.assertEqual(checks["runtimes"]["status"], "warn")
        self.assertIn("protontricks 1091500 vcrun2022 d3dcompiler_47", checks["runtimes"]["fix"])
        (pfx / "winetricks.log").write_text("vcrun2022\nd3dcompiler_47\n")
        cfg = self.steam / "userdata/1/config/localconfig.vdf"
        cfg.parent.mkdir(parents=True)
        cfg.write_text('"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"apps"\n\t\t{\n\t\t\t"1091500"\n\t\t\t{\n'
                       '\t\t\t\t"LaunchOptions"\t\t"WINEDLLOVERRIDES=\\"winmm,version=n,b\\" %command% --launcher-skip"\n\t\t\t}\n\t\t}\n\t}\n}\n')
        checks = {c["id"]: c for c in json.loads(self.run_cli("doctor", "--json"))}
        self.assertEqual(checks["launch"]["status"], "ok")
        self.assertEqual(checks["runtimes"]["status"], "ok")
        self.assertEqual(checks["fw:RED4ext"]["status"], "ok")

    def test_doctor_reports_unmanaged_files(self):
        (self.game / "archive/pc/mod").mkdir(parents=True)
        (self.game / "archive/pc/mod/handmade.archive").write_text("x")
        checks = {c["id"]: c for c in json.loads(self.run_cli("doctor", "--json"))}
        self.assertEqual(checks["unmanaged"]["status"], "warn")

    def test_older_tool_still_reads_the_store(self):
        old = Path(os.environ.get("SAMURAI_MM_OLD_TOOL", "/nonexistent"))     # the script this engine grew out of
        if not old.is_file():
            self.skipTest("set SAMURAI_MM_OLD_TOOL to the original cp2077-mods.py to run this")
        self.run_cli("add", str(self.a))
        self.run_cli("add", str(self.b))
        self.run_cli("disable", "Mod B")
        r = subprocess.run([sys.executable, str(old), "--store", str(self.store), "--game", str(self.game), "list"],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Mod A", r.stdout)
        self.assertNotIn("Mod B", r.stdout)
        r = subprocess.run([sys.executable, str(old), "--store", str(self.store), "--game", str(self.game), "verify"],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.mods()["Mod B-22-2-1-1700000001"]["state"], "disabled")   # the old tool kept our data


@unittest.skipUnless(HAVE_UNPACKER, "needs 7z or bsdtar")
class RunningGame(Sandbox):
    def test_changes_refused_while_game_runs(self):
        self.run_cli("init")
        mod = self.make_zip("Mod A-11-1-0-1700000000.zip", {"archive/pc/mod/a.archive": "aaa"})
        self.run_cli("add", str(mod))
        fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "Z:\\fake\\bin\\x64\\Cyberpunk2077.exe"])
        self.addCleanup(fake.wait)
        self.addCleanup(fake.kill)
        self.env.pop("SAMURAI_MM_ASSUME_GAME_CLOSED")
        for args in (["disable", "Mod A"], ["remove", "Mod A"], ["undeploy"], ["deploy"]):
            self.assertIn("the game is running", self.run_cli(*args, ok=False))
        self.assertIn("would place 1 files", self.run_cli("deploy", "--dry-run"))
        self.assertIn("archive/pc/mod/a.archive", self.game_files())
        self.run_cli("list")
        self.run_cli("doctor", ok=None)


class NoStore(Sandbox):
    def test_status_and_doctor_without_store(self):
        st = json.loads(self.run_cli("status", "--json"))
        self.assertFalse(st["has_store"])
        self.assertEqual(st["game"], str(self.game))
        self.assertIn("Run `init`", self.run_cli("list", ok=False))
        checks = {c["id"]: c for c in json.loads(self.run_cli("doctor", "--json"))}
        self.assertEqual(checks["store"]["status"], "warn")

    def test_game_not_found(self):
        shutil.rmtree(self.game)
        checks = json.loads(self.run_cli("doctor", "--json"))
        self.assertEqual((checks[0]["id"], checks[0]["status"]), ("game", "fail"))
        self.assertIn("game folder not found", self.run_cli("init", ok=False))


class Parsing(unittest.TestCase):
    def test_mod_names(self):
        cases = {
            "ArchiveXL 4198 1.28.1 2026-10-27T17-59Z 4rpqrKKT3": ("ArchiveXL", 4198, "1.28.1"),
            "Mod Settings v0.2.27 for 2.50 4885 0.2.27 2026-10-26T22-14Z cB3xB00IB": ("Mod Settings v0.2.27 for 2.50", 4885, "0.2.27"),
            "HUD Fixes-4011-1-15-0-1775904244": ("HUD Fixes", 4011, "1.15.0"),
            "judy-romancable-with-v-male-24961-0-1-0-1760303888": ("judy-romancable-with-v-male", 24961, "0.1.0"),
            "vehiclehandling_v1.3-210-v1-3-1726943022": ("vehiclehandling_v1.3", 210, "v1.3"),
            "Outrun Waves 93.7 - Radio Mod-5808-1-1-3-1715903376": ("Outrun Waves 93.7 - Radio Mod", 5808, "1.1.3"),
            "My own folder": ("My own folder", None, None),
        }
        for name, want in cases.items():
            got = engine.parse_mod_name(name)
            self.assertEqual((got["title"], got["nexus_id"], got["version"]), want, name)

    def test_dll_overrides(self):
        f = doctor.native_overrides
        self.assertEqual(f('A=1 WINEDLLOVERRIDES="winmm,version=n,b" %command%'), {"winmm", "version"})
        self.assertEqual(f("WINEDLLOVERRIDES=winmm=n,b;version=b %command%"), {"winmm"})
        self.assertEqual(f("PROTON_LOG=1 %command%"), set())
        self.assertEqual(f(None), set())

    def test_vdf_blocks(self):
        text = '"apps"\n{\n"1091500"\n{\n"x" "a{b"\n"LaunchOptions" "foo"\n"n"\n{\n}\n}\n"2"\n{\n}\n}'
        blocks = list(doctor.vdf_app_blocks(text, "1091500"))
        self.assertEqual(len(blocks), 1)
        self.assertIn('"LaunchOptions" "foo"', blocks[0])
        self.assertNotIn('"2"', blocks[0])


if __name__ == "__main__":
    unittest.main()
