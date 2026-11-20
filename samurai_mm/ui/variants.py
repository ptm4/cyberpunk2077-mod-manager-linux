"""What can be installed from a download the engine will not decide about: FOMOD installer options,
folders in game layout, loose .archive files. No window code here, so it can be tested without a display."""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..engine import GAME_TOP_DIRS

def ci_find(base: Path, rel: str):
    """Find rel under base, ignoring upper/lower case (installer files are written on Windows)."""
    cur = base
    for part in [p for p in re.split(r"[\\/]+", rel) if p and p != "."]:
        if part == "..":
            return None
        nxt = cur / part
        if not nxt.exists():
            if not cur.is_dir():
                return None
            hits = [e for e in os.listdir(cur) if e.lower() == part.lower()]
            if not hits:
                return None
            nxt = cur / hits[0]
        cur = nxt
    return cur


def ci_target(base: Path, rel: str) -> Path:
    """Path for rel under base, reusing existing folders whose names differ only in case."""
    cur = base
    for part in [p for p in re.split(r"[\\/]+", rel) if p and p not in (".", "..")]:
        nxt = cur / part
        if not nxt.exists() and cur.is_dir():
            hits = [e for e in os.listdir(cur) if e.lower() == part.lower()]
            if hits:
                nxt = cur / hits[0]
        cur = nxt
    return cur


def files_under(folder: Path):
    out = []
    for d, _, files in os.walk(folder):
        for n in files:
            out.append(Path(d) / n)
    return sorted(out)


def fomod_entries(node):
    out = []
    if node is not None:
        for e in node:
            if e.tag in ("file", "folder"):
                out.append((e.tag, e.get("source", ""), e.get("destination")))
    return out


def parse_fomod(cfg: Path):
    """Read the options out of a fomod/ModuleConfig.xml. Raises ValueError when it needs more than we can do."""
    try:
        root = ET.parse(cfg).getroot()
    except (ET.ParseError, OSError, UnicodeError) as e:
        raise ValueError(f"could not read the installer file ({e})")
    for el in root.iter():
        if isinstance(el.tag, str):
            el.tag = el.tag.split("}")[-1]
    info = {"name": (root.findtext("moduleName") or "").strip(),
            "required": fomod_entries(root.find("requiredInstallFiles")), "groups": [], "patterns": []}
    for step in root.findall("installSteps/installStep"):
        for g in step.findall("optionalFileGroups/group"):
            plugins = []
            for p in g.findall("plugins/plugin"):
                t = p.find("typeDescriptor/type")
                plugins.append({
                    "name": p.get("name", "(unnamed)"),
                    "desc": " ".join((p.findtext("description") or "").split()),
                    "files": fomod_entries(p.find("files")),
                    "flags": {f.get("name"): (f.text or "").strip() for f in p.findall("conditionFlags/flag")},
                    "type": t.get("name", "Optional") if t is not None else "Optional"})
            if plugins:
                info["groups"].append({"step": step.get("name", ""), "name": g.get("name", ""),
                                       "type": g.get("type", "SelectAny"), "plugins": plugins})
    for pat in root.findall("conditionalFileInstalls/patterns/pattern"):
        dep = pat.find("dependencies")
        if dep is None or any(c.tag != "flagDependency" for c in dep):
            raise ValueError("the installer uses conditions this window cannot evaluate")
        info["patterns"].append((dep.get("operator", "And"),
                                 [(c.get("flag"), c.get("value", "")) for c in dep],
                                 fomod_entries(pat.find("files"))))
    if not info["groups"] and not info["required"]:
        raise ValueError("the installer file lists no options")
    return info


def find_fomod(root: Path):
    """Return (base folder, ModuleConfig.xml) if a fomod installer sits within two wrapper folders."""
    cur = root
    for _ in range(3):
        f = ci_find(cur, "fomod/ModuleConfig.xml")
        if f and f.is_file():
            return cur, f
        dirs = [e for e in cur.iterdir() if e.is_dir()]
        if len(dirs) != 1:
            break
        cur = dirs[0]
    return None, None


def scan_candidates(root: Path):
    """Things in an unpacked download the engine could install: folders in game layout, and loose .archive files."""
    layout, loose = [], []

    def walk(d: Path, depth):
        entries = sorted(d.iterdir(), key=lambda p: p.name.lower())
        subdirs = [e for e in entries if e.is_dir()]
        if any(e.name.lower() in GAME_TOP_DIRS for e in subdirs):
            layout.append(d)
            return
        files = [e for e in entries if e.is_file() and e.suffix.lower() in (".archive", ".xl")]
        if files:
            loose.append((d, files))
        if depth < 6:
            for s in subdirs:
                if s.name.lower() != "fomod":
                    walk(s, depth + 1)

    walk(root, 0)
    return layout, loose


def resolve_entries(base: Path, entries):
    """Turn installer (kind, source, destination) entries into (file, game-relative path) pairs."""
    pairs, missing = [], []
    for kind, source, dest in entries:
        src = ci_find(base, source) if source else base
        if src is None or not src.exists():
            missing.append(source)
            continue
        if src.is_dir():
            prefix = source if dest is None else dest
            for f in files_under(src):
                if "fomod" in [p.lower() for p in f.relative_to(base).parts[:-1]]:
                    continue
                rel = f.relative_to(src).as_posix()
                pairs.append((f, (prefix.replace("\\", "/").strip("/") + "/" + rel).lstrip("/")))
        else:
            if dest is None:
                rel = source
            elif dest == "" or dest.endswith(("/", "\\")):
                rel = dest + src.name
            else:
                rel = dest
            pairs.append((src, rel.replace("\\", "/").lstrip("/")))
    return pairs, missing
