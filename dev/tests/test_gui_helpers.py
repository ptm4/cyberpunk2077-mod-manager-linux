"""Tests for the parts that do not need a display: game detection and reading what a download offers."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from samurai_mm import engine  # noqa: E402
from samurai_mm.ui import variants  # noqa: E402

FOMOD = """<?xml version="1.0" encoding="UTF-8"?>
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <requiredInstallFiles><folder source="core" destination=""/></requiredInstallFiles>
 <installSteps><installStep name="Main"><optionalFileGroups>
  <group name="Texture" type="SelectExactlyOne"><plugins>
   <plugin name="A"><files><file source="Opt A\\a.archive" destination="archive\\pc\\mod\\a.archive"/></files></plugin>
   <plugin name="B"><conditionFlags><flag name="b">On</flag></conditionFlags><typeDescriptor><type name="Recommended"/></typeDescriptor></plugin>
  </plugins></group></optionalFileGroups></installStep></installSteps>
 <conditionalFileInstalls><patterns><pattern><dependencies operator="And"><flagDependency flag="b" value="On"/></dependencies>
  <files><folder source="Opt B" destination="archive/pc/mod"/></files></pattern></patterns></conditionalFileInstalls>
</config>"""


class Helpers(unittest.TestCase):
    def test_game_process_is_detected(self):
        fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)", "Z:\\\\fake\\\\bin\\\\x64\\\\Cyberpunk2077.exe"])
        try:
            self.assertTrue(engine.game_running())
        finally:
            fake.kill()
            fake.wait()

    def test_fomod_reader(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("fomod/ModuleConfig.xml", "Core/archive/pc/mod/core.archive", "Opt A/a.archive", "Opt B/b.archive"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(FOMOD if rel.endswith(".xml") else "x")
            base, cfg = variants.find_fomod(root)
            info = variants.parse_fomod(cfg)
            self.assertEqual([p["name"] for p in info["groups"][0]["plugins"]], ["A", "B"])
            pairs, missing = variants.resolve_entries(base, info["required"] + info["groups"][0]["plugins"][0]["files"] + info["patterns"][0][2])
            self.assertEqual(missing, [])
            self.assertEqual(sorted(rel for _, rel in pairs),
                             ["archive/pc/mod/a.archive", "archive/pc/mod/b.archive", "archive/pc/mod/core.archive"])

    def test_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("Pack/Red/red.archive", "Pack/Blue/blue.archive", "Pack/Full/archive/pc/mod/x.archive", "Pack/readme.txt"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x")
            layout, loose = variants.scan_candidates(root)
            self.assertEqual([p.name for p in layout], ["Full"])
            self.assertEqual(sorted(f.name for _, files in loose for f in files), ["blue.archive", "red.archive"])


if __name__ == "__main__":
    unittest.main()
