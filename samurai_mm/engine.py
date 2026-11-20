"""samurai_mm.engine - mod store and deployment for Cyberpunk 2077 on Linux (Steam / Proton).

Standard library only. The idea: every mod lives in its own folder in a "store",
in game-folder layout. The game folder only ever receives copies of those files,
and everything placed there is recorded, so any mod (or all of them) can be taken
out again without leaving anything behind.

Commands:

  init          create an empty store for the installed game
  add           add a downloaded mod archive (zip/7z/rar) or folder, then deploy it
  remove        take one mod out of the game and out of the store (kept under removed/)
  enable        put a disabled mod back into the game
  disable       take a mod out of the game but keep it in the store
  list          list the mods in the store
  info          show one mod's files
  status        show what is deployed
  deploy        place every enabled mod file into the game folder (case-insensitive merge)
  undeploy      remove exactly the files deploy placed
  verify        re-hash the deployed files against the manifest
  doctor        check the Linux side: game, Proton prefix, launch options, frameworks
  logs          check RED4ext / CET / redscript logs after a game launch
  accept-build  record the installed game build as the one the mods are for
  settings      copy saved settings from the store into the game (backs up what it replaces)

The engine never overwrites a file it did not place itself (unless --force).
"""
import argparse
import contextlib
import fcntl
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

APPID = "1091500"
GAME_DIRNAME = "Cyberpunk 2077"
NEXUS_GAME = "cyberpunk2077"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
DEFAULT_STORE = DATA_HOME / "samurai-mm" / "store"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "samurai-mm" / "config.json"
GAME_TOP_DIRS = {"archive", "bin", "engine", "r6", "red4ext", "mods", "tools"}
LOOSE_ARCHIVE_EXT = {".archive", ".xl"}
MANIFEST_BACKUPS_KEPT = 20
MAX_NAME_BYTES = 150          # a mod's name becomes a folder name
MAX_ARCHIVE_ENTRIES = 200000
LOCK_WAIT_SECONDS = float(os.environ.get("SAMURAI_MM_LOCK_WAIT", "60"))   # the variable is for tests


# ---------------------------------------------------------------- small helpers

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


GAME_EXES = {b"cyberpunk2077.exe", b"redprelauncher.exe"}


def game_running():
    """True if a process whose command line names the game's exe exists."""
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        for arg in raw.split(b"\0"):
            if re.split(rb"[\\/]", arg)[-1].lower() in GAME_EXES:
                return True
    return False


def require_game_closed(a):
    """Commands that change the game folder stop here while the game runs. Dry runs may pass."""
    if getattr(a, "dry_run", False) or os.environ.get("SAMURAI_MM_ASSUME_GAME_CLOSED") == "1":   # the variable is for tests
        return
    if game_running():
        sys.exit("error: the game is running. Close it first; changing mod files under a running game can break it.")


def steam_roots():
    home = Path.home()
    roots = [home / ".local/share/Steam", home / ".steam/steam",
             home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
             home / "snap/steam/common/.local/share/Steam"]
    seen, out = set(), []
    for r in roots:
        if (r / "steamapps").is_dir() and r.resolve() not in seen:
            seen.add(r.resolve())
            out.append(r)
    return out


def steam_libraries():
    libs = []
    for root in steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                libs.append(Path(m.group(1)))
    seen, out = set(), []
    for lib in libs:
        r = lib.resolve()
        if r not in seen:
            seen.add(r)
            out.append(lib)
    return out


def is_game_dir(p: Path) -> bool:
    return (p / "bin" / "x64" / "Cyberpunk2077.exe").is_file()


def other_launcher_games():
    """Game folders known to Heroic (GOG, Epic) and Lutris, native or Flatpak."""
    home, found = Path.home(), []
    for cfg in (home / ".config", home / ".var/app/com.heroicgameslauncher.hgl/config"):
        for rel in ("heroic/gog_store/installed.json", "heroic/legendaryConfig/legendary/installed.json", "legendary/installed.json"):
            f = cfg / rel
            try:
                data = json.loads(f.read_text(errors="replace")) if f.is_file() else None
            except (OSError, ValueError):
                continue
            todo = [data]
            while todo:
                x = todo.pop()
                if isinstance(x, dict):
                    todo += list(x.values())
                elif isinstance(x, list):
                    todo += x
                elif isinstance(x, str) and x.startswith("/") and len(x) < 4096 and is_game_dir(Path(x)):
                    found.append(Path(x))
    for cfg in (home / ".config/lutris/games", home / ".local/share/lutris/games", home / ".var/app/net.lutris.Lutris/config/lutris/games"):
        if cfg.is_dir():
            for f in cfg.glob("*.yml"):
                try:
                    m = re.search(r"exe:\s*['\"]?(/.+?)[\\/]bin[\\/]x64[\\/]Cyberpunk2077\.exe", f.read_text(errors="replace"))
                except OSError:
                    continue
                if m and is_game_dir(Path(m.group(1))):
                    found.append(Path(m.group(1)))
    return found


def is_steam_install(game: Path) -> bool:
    return (game.parent.parent / f"appmanifest_{APPID}.acf").is_file()


def suggest_store(game):
    """Where a new store should go: the default place, or next to the game when that is on another disk."""
    if game is None:
        return DEFAULT_STORE
    probe = DEFAULT_STORE
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        if os.stat(probe).st_dev == os.stat(game).st_dev:
            return DEFAULT_STORE
        library = game.parent.parent.parent if game.parent.name == "common" else game.parent
        if os.access(library, os.W_OK):
            return library / "samurai-mm-store"
    except OSError:
        pass
    return DEFAULT_STORE


def find_game(explicit=None, required=True):
    """The game folder: --game, then the saved setting, then the Steam libraries, then Heroic and Lutris."""
    choice = explicit or load_config().get("game")
    if choice:
        p = Path(choice).expanduser()
        if is_game_dir(p):
            return p
        if explicit or required:
            sys.exit(f"error: no bin/x64/Cyberpunk2077.exe under {p}")
        return None
    for lib in steam_libraries():
        p = lib / "steamapps" / "common" / GAME_DIRNAME
        if is_game_dir(p):
            return p
    for p in other_launcher_games():
        return p
    if required:
        sys.exit("error: game folder not found. Pass --game /path/to/'Cyberpunk 2077' or set it in the settings.")
    return None


def find_prefix(game: Path):
    """The Proton prefix, for a Steam install."""
    p = game.parent.parent / "compatdata" / APPID / "pfx"
    return p if p.is_dir() else None


def game_build(game: Path) -> str:
    """Steam's build id, or a fingerprint of the exe for installs Steam does not know about."""
    acf = game.parent.parent / f"appmanifest_{APPID}.acf"
    if acf.is_file():
        m = re.search(r'"buildid"\s+"(\d+)"', acf.read_text(errors="replace"))
        if m:
            return m.group(1)
    return "exe-" + sha256(game / "bin" / "x64" / "Cyberpunk2077.exe")[:12]


def resolve_ci(root: Path, rel: str) -> Path:
    """Map a game-relative path onto root, reusing existing entries whose names differ only in case."""
    cur = root
    for part in rel.replace("\\", "/").split("/"):
        nxt = cur / part
        if not nxt.exists() and cur.is_dir():
            low = part.lower()
            matches = [e for e in os.listdir(cur) if e.lower() == low]
            if len(matches) > 1:
                sys.exit(f"error: case-duplicate entries in {cur}: {matches}")
            if matches:
                nxt = cur / matches[0]
        cur = nxt
    return cur


def place(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    r = subprocess.run(["cp", "--reflink=auto", "--preserve=timestamps", str(src), str(dst)])
    if r.returncode != 0:
        shutil.copy2(src, dst)


def parse_mod_name(name: str):
    """Pull the Nexus mod id and version out of a download's name, when it follows Nexus naming."""
    m = re.match(r"^(?P<title>.+) (?P<id>\d+) (?P<ver>\S+) \d{4}-\d\d-\d\dT\d\d-\d\dZ \w+$", name)  # via Vortex
    if m:
        return {"title": m.group("title"), "nexus_id": int(m.group("id")), "version": m.group("ver")}
    m = re.match(r"^(?P<title>.+?)-(?P<id>\d+)-(?P<ver>[A-Za-z0-9-]+?)-(?P<ts>\d{10})$", name)       # manual download
    if m:
        return {"title": m.group("title"), "nexus_id": int(m.group("id")), "version": m.group("ver").replace("-", ".")}
    return {"title": name, "nexus_id": None, "version": None}


# ---------------------------------------------------------------- store files

_lock_depth = 0


@contextlib.contextmanager
def store_lock(store: Path):
    """One changing command at a time per store; a second one waits a while, then gives up."""
    global _lock_depth
    if _lock_depth:
        _lock_depth += 1
        try:
            yield
        finally:
            _lock_depth -= 1
        return
    store.mkdir(parents=True, exist_ok=True)
    with open(store / ".lock", "w") as fh:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    sys.exit("error: another Samurai Mod Manager command is still working on this mod store. Try again when it has finished.")
                time.sleep(0.2)
        _lock_depth = 1
        try:
            yield
        finally:
            _lock_depth = 0


def changes_store(fn):
    """For commands that change the store or the game folder: game closed, and one at a time. Dry runs pass freely."""
    @functools.wraps(fn)
    def wrapper(a):
        if getattr(a, "dry_run", False):
            return fn(a)
        require_game_closed(a)
        with store_lock(a.store):
            return fn(a)
    return wrapper


def has_control_chars(text: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in text)


def check_mod_name(name: str):
    if not name.strip() or name in (".", "..") or any(c in name for c in "/\\") or has_control_chars(name):
        sys.exit("error: that mod name cannot be used (empty, or it contains a slash or a control character)")
    if len(name.encode("utf-8", "replace")) > MAX_NAME_BYTES:
        sys.exit(f"error: the mod name is too long ({len(name.encode('utf-8', 'replace'))} bytes, at most {MAX_NAME_BYTES}). "
                 "Rename the download or pass --name with a shorter one.")

def load_manifest(store: Path):
    f = store / "manifest.json"
    if not f.is_file():
        sys.exit(f"error: no mod store at {store} yet. Run `init` first (or pass --store).")
    try:
        man = json.loads(f.read_text(encoding="utf-8-sig"))
        if not isinstance(man, dict):
            raise ValueError("not a mod list")
    except ValueError as e:
        sys.exit(f"error: the mod list {f} is damaged ({e}). Copies from before each change are in "
                 f"{store / 'backups' / 'manifest'}; copy the newest good one over manifest.json.")
    man.setdefault("mods", [])
    man.setdefault("files", [])
    man.setdefault("settings", [])
    man.setdefault("game", {})
    dis = man.setdefault("disabled", {})
    dis.setdefault("mods", [])
    dis.setdefault("files", [])
    return man


def save_manifest(store: Path, man):
    f = store / "manifest.json"
    if f.is_file():
        bdir = store / "backups" / "manifest"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, bdir / f"manifest-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.json")
        old = sorted(bdir.glob("manifest-*.json"))
        for extra in old[:-MANIFEST_BACKUPS_KEPT]:
            extra.unlink()
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def load_state(store: Path):
    f = store / "deployed.json"
    try:
        state = json.loads(f.read_text()) if f.is_file() else {}
        if not isinstance(state, dict):
            raise ValueError("not a record")
    except ValueError as e:
        sys.exit(f"error: the record of placed files {f} is damaged ({e}). Move it away and run `deploy`: "
                 "files already in the game that match your mods are taken over again.")
    state.setdefault("files", {})
    state.setdefault("settings", {})
    return state


def save_state(store: Path, state):
    f = store / "deployed.json"
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    os.replace(tmp, f)


def shelve(store: Path, mod_dir: Path):
    """Move a mod folder to removed/ under a name that is not taken yet."""
    base = store / "removed"
    base.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target, n = base / f"{mod_dir.name}.{stamp}", 1
    while target.exists():
        n += 1
        target = base / f"{mod_dir.name}.{stamp}-{n}"
    shutil.move(str(mod_dir), str(target))
    return target


def all_mod_names(man):
    return list(man["mods"]) + list(man["disabled"]["mods"])


def match_mod(man, name, pool=None):
    names = pool if pool is not None else all_mod_names(man)
    if name in names:
        return name
    hits = [m for m in names if name.lower() in m.lower()]
    if len(hits) != 1:
        sys.exit(f"error: '{name}' matches {len(hits)} mods" + (": " + "; ".join(hits) if hits else "") +
                 ". Use `list` and give a longer part of the name.")
    return hits[0]


def mod_rows(man, state):
    """One summary per mod: enabled ones with their deploy state, then the disabled ones."""
    count, size, dep = {}, {}, {}
    for f in man["files"] + man["disabled"]["files"]:
        count[f["mod"]] = count.get(f["mod"], 0) + 1
        size[f["mod"]] = size.get(f["mod"], 0) + f.get("size", 0)
    for v in state["files"].values():
        dep[v["mod"]] = dep.get(v["mod"], 0) + 1
    rows = []
    for m in man["mods"]:
        c, d = count.get(m, 0), dep.get(m, 0)
        rows.append({"name": m, "files": c, "size": size.get(m, 0),
                     "state": "deployed" if d == c and c else ("partial" if d else "not in game"), **parse_mod_name(m)})
    for m in man["disabled"]["mods"]:
        rows.append({"name": m, "files": count.get(m, 0), "size": size.get(m, 0), "state": "disabled", **parse_mod_name(m)})
    return sorted(rows, key=lambda r: r["name"].lower())


# ---------------------------------------------------------------- init, deploy, undeploy, verify

@changes_store
def cmd_init(a):
    f = a.store / "manifest.json"
    if f.is_file():
        sys.exit(f"error: there is already a mod store at {a.store}")
    game = find_game(a.game)
    (a.store / "mods").mkdir(parents=True, exist_ok=True)
    man = {"schema": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "game": {"steam_appid": int(APPID), "buildid": game_build(game)},
           "mods": [], "files": [], "settings": [], "disabled": {"mods": [], "files": []}}
    save_manifest(a.store, man)
    print(f"created an empty mod store at {a.store}\ngame: {game} (build {man['game']['buildid']})")


def check_build(game: Path, man, force):
    have, want = game_build(game), str(man["game"].get("buildid") or "")
    if not want:
        print(f"game build: installed {have} (none recorded in the store)")
        return
    print(f"game build: installed {have}, mods set up for {want}")
    if have != want and not force:
        sys.exit("error: the game was updated since the mods were set up. Frameworks (RED4ext, CET, redscript, "
                 "ArchiveXL, TweakXL, Codeware) are tied to the game version: update them first (add --replace), "
                 "then run `accept-build`. Or re-run with --force.")


@changes_store
def cmd_accept_build(a):
    man = load_manifest(a.store)
    game = find_game(a.game)
    old, new = man["game"].get("buildid"), game_build(game)
    if str(old) == new:
        print(f"the store is already set up for build {new}")
        return
    man["game"]["buildid"] = new
    save_manifest(a.store, man)
    print(f"recorded game build {new} (was {old})")


def find_clashes(man, state, game: Path, name: str, rels, also_ignore=None):
    """Which of the game-relative paths in rels would replace another enabled mod's file or a foreign file."""
    owner = {f["path"].lower(): f["mod"] for f in man["files"] if f["mod"] not in (name, also_ignore)}
    seen, clashes = set(), []
    for rel in rels:
        low = rel.lower()
        if low in seen:
            clashes.append(f"{rel}  (twice in this mod, differing only in upper/lower case)")
        seen.add(low)
        if low in owner:
            clashes.append(f"{rel}  (already installed by: {owner[low]})")
        else:
            dst = resolve_ci(game, rel)
            if dst.exists() and str(dst.relative_to(game)) not in state["files"]:
                clashes.append(f"{rel}  (a file the game or something else put there)")
    return clashes


def plan_deploy(store: Path, game: Path, state, entries, force):
    plan, conflicts = [], []
    for f in entries:
        src = store / "mods" / f["mod"] / f["path"]
        if not src.is_file():
            sys.exit(f"error: missing in the store: {src}")
        dst = resolve_ci(game, f["path"])
        rel = str(dst.relative_to(game))
        if dst.exists() and rel not in state["files"]:
            if sha256(dst) != f["sha256"] and not force:
                conflicts.append(rel)
        plan.append((src, dst, rel, f))
    if conflicts:
        print("refusing to overwrite files this tool did not place:")
        for c in conflicts:
            print("  ", c)
        sys.exit(1)
    return plan


def run_plan(store: Path, game: Path, state, plan):
    state["game"] = str(game)
    try:
        for src, dst, rel, f in plan:
            if not (dst.is_file() and dst.stat().st_size == f["size"] and sha256(dst) == f["sha256"]):
                place(src, dst)
            state["files"][rel] = {"mod": f["mod"], "sha256": f["sha256"]}
    finally:
        # also when interrupted or out of space: what was placed so far stays on record, so it can be removed again
        state["deployed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_state(store, state)


@changes_store
def cmd_deploy(a):
    man = load_manifest(a.store)
    game = find_game(a.game)
    check_build(game, man, a.force)
    state = load_state(a.store)
    plan = plan_deploy(a.store, game, state, man["files"], a.force)
    if a.dry_run:
        print(f"dry run: would place {len(plan)} files into {game}")
        return
    run_plan(a.store, game, state, plan)
    print(f"deployed {len(plan)} files from {len(man['mods'])} mods into {game}")


def remove_from_game(store: Path, state, mod):
    game = Path(state["game"]) if state.get("game") else None
    n, dirs = 0, set()
    for rel in [r for r, v in state["files"].items() if v["mod"] == mod]:
        p = game / rel
        if p.is_file():
            p.unlink()
            n += 1
            dirs.add(p.parent)
        del state["files"][rel]
    prune_empty(game, dirs)
    save_state(store, state)
    return n


def prune_empty(game: Path, dirs):
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        while d != game and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent


@changes_store
def cmd_undeploy(a):
    state = load_state(a.store)
    if not state.get("game"):
        print("nothing deployed")
        return
    game = Path(state["game"])
    if not game.is_dir():
        sys.exit(f"error: the game folder the mods were placed in is gone ({game}). If the game was moved, set the new folder "
                 "in the settings and run `deploy`; if it was uninstalled there is nothing left to remove.")
    removed, dirs = 0, set()
    for rel in list(state["files"]) + list(state.get("settings", {})):
        p = game / rel
        if p.is_file():
            if a.dry_run:
                print("would remove", rel)
            else:
                p.unlink()
            removed += 1
            dirs.add(p.parent)
    if a.dry_run:
        print(f"dry run: would remove {removed} files")
        return
    prune_empty(game, dirs)
    save_state(a.store, {"files": {}, "settings": {}})
    print(f"removed {removed} files; logs and caches the game wrote itself are left in place")


def case_duplicates(game: Path):
    """Folders or files in the mod locations whose names differ only in case (Wine would pick one arbitrarily)."""
    found = []
    for top in ("bin/x64/plugins", "red4ext", "r6", "archive/pc/mod", "engine"):
        base = resolve_ci(game, top)
        for d, dirs, files in os.walk(base):
            names = {}
            for n in dirs + files:
                names.setdefault(n.lower(), []).append(n)
            for v in names.values():
                if len(v) > 1:
                    found.append((str(Path(d).relative_to(game)), v))
    return found


def cmd_verify(a):
    man = load_manifest(a.store)
    game = find_game(a.game)
    missing = bad = 0
    for f in man["files"]:
        dst = resolve_ci(game, f["path"])
        if not dst.is_file():
            missing += 1
            print("MISSING", f["path"])
        elif sha256(dst) != f["sha256"]:
            bad += 1
            print("DIFFERS", f["path"])
    dupes = case_duplicates(game)
    for where, names in dupes:
        print("CASE-DUPLICATE", where, names)
    total = len(man["files"])
    print(f"verify: {total - missing - bad}/{total} identical, {missing} missing, {bad} differ, {len(dupes)} case duplicates")
    sys.exit(0 if not (missing or bad or dupes) else 1)


@changes_store
def cmd_settings(a):
    man = load_manifest(a.store)
    if not man["settings"] and not (a.store / "settings" / "UserSettings.json").is_file():
        print("this store has no saved settings")
        return
    game = find_game(a.game)
    state = load_state(a.store)
    backup = a.store / "backups" / time.strftime("%Y%m%d-%H%M%S")
    n = 0
    for f in man["settings"]:
        src = a.store / "settings" / "game-folder" / f["path"]
        dst = resolve_ci(game, f["path"])
        if dst.exists():
            b = backup / "game-folder" / f["path"]
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, b)
        place(src, dst)
        state["settings"][str(dst.relative_to(game))] = f["sha256"]
        n += 1
    print(f"copied {n} mod settings files into {game}")
    pfx = find_prefix(game)
    us_src = a.store / "settings" / "UserSettings.json"
    if pfx and us_src.is_file():
        us_dst = pfx / "drive_c/users/steamuser/AppData/Local/CD Projekt Red/Cyberpunk 2077/UserSettings.json"
        if us_dst.exists():
            b = backup / "UserSettings.json"
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(us_dst, b)
        us_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(us_src, us_dst)
        print(f"copied UserSettings.json into the prefix ({us_dst})")
    elif us_src.is_file():
        print("note: Proton prefix not found; launch the game once, then re-run settings for UserSettings.json")
    save_state(a.store, state)
    if backup.exists():
        print(f"backups of replaced files: {backup}")


# ---------------------------------------------------------------- add, remove, enable, disable

def seven_zip():
    return shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")


def list_archive(src: Path):
    """What an archive says it contains, before anything is unpacked: [(path, size, is a link)]. None if it cannot be listed."""
    entries = []
    if src.suffix.lower() == ".zip":
        import zipfile
        try:
            with zipfile.ZipFile(src) as z:
                for i in z.infolist():
                    entries.append((i.filename, i.file_size, (i.external_attr >> 16) & 0o170000 == 0o120000))
        except (zipfile.BadZipFile, OSError, ValueError):
            entries = []
    tool = seven_zip()
    if tool:
        r = subprocess.run([tool, "l", "-slt", "-ba", "-sccUTF-8", "--", str(src)], capture_output=True, text=True, errors="replace")
        if r.returncode == 0:
            for block in r.stdout.split("\n\n"):
                fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
                if "Path" in fields:
                    size = int(fields["Size"]) if fields.get("Size", "").isdigit() else 0
                    link = bool(fields.get("Symbolic Link") or fields.get("Hard Link")) or fields.get("Attributes", "").startswith("l")
                    entries.append((fields["Path"], size, link))
            return entries
    if entries:
        return entries
    if shutil.which("bsdtar"):
        r = subprocess.run(["bsdtar", "-tvf", str(src)], capture_output=True, text=True, errors="replace")
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split(None, 8)
                if len(parts) == 9:
                    entries.append((parts[8].split(" -> ")[0], int(parts[4]) if parts[4].isdigit() else 0, line.startswith(("l", "h"))))
            return entries
    return None


def vet_listing(name: str, entries, free_bytes):
    """Refuse an archive whose listing shows it is built to write outside its folder, or to fill the disk."""
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        sys.exit(f"error: {name} holds {len(entries)} entries, far more than any mod. Not unpacking it.")
    total = 0
    for path, size, link in entries:
        parts = [p for p in re.split(r"[\\/]+", path) if p]
        shown = "".join(c if not has_control_chars(c) else "?" for c in path)[:120]
        if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or ".." in parts:
            sys.exit(f"error: {name} contains a path that points outside the mod folder ({shown}). "
                     "Real mods never need that; not unpacking it.")
        if has_control_chars(path):
            sys.exit(f"error: {name} contains a file name with control characters ({shown}); not unpacking it.")
        if link:
            sys.exit(f"error: {name} contains a link ({shown}). Real mods never need that; not unpacking it.")
        total += size
    if free_bytes is not None and total > free_bytes:
        sys.exit(f"error: {name} unpacks to {human_size(total)} but only {human_size(free_bytes)} is free on the disk holding the mod store.")
    return total


def untangle_backslashes(dest: Path):
    """Some Windows tools store 'archive\\pc\\mod\\x.archive' as one file name; turn such names back into folders."""
    for d, dirs, files in os.walk(dest, topdown=False):
        for n in files + dirs:
            if "\\" in n:
                parts = [p for p in n.split("\\") if p not in ("", ".")]
                if not parts or ".." in parts:
                    sys.exit(f"error: the download contains a file name that points outside the mod folder ({n[:120]}); not adding it")
                target = Path(d).joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    sys.exit(f"error: the download contains the same file twice under different spellings ({n[:120]}); not adding it")
                os.rename(Path(d) / n, target)


def extract(src: Path, dest: Path):
    """Unpack an archive (or copy a folder) into the new folder dest, after checking what it claims to contain.
    Refuses links, control characters in names, and anything that would land outside dest."""
    src = src.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if src.is_dir():
        total = 0
        for d, dirs, files in os.walk(src):
            for n in dirs + files:
                q = Path(d) / n
                if q.is_symlink():
                    sys.exit(f"error: {src.name} contains a link ({n[:120]}); not adding it")
                total += q.stat().st_size if q.is_file() else 0
        if total > free:
            sys.exit(f"error: {src.name} is {human_size(total)} but only {human_size(free)} is free on the disk holding the mod store.")
        dest.mkdir()
        shutil.copytree(src, dest, dirs_exist_ok=True, symlinks=True)
    else:
        entries = list_archive(src)
        if entries is None:
            sys.exit(f"error: could not read {src.name}. It is damaged, or not a zip, 7z or rar archive "
                     "(unpacking needs 7z; unrar helps with some rar files).")
        vet_listing(src.name, entries, free)
        dest.mkdir()
        tool = seven_zip()
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        r = subprocess.run([tool, "x", "-y", "-bso0", "-bsp0", f"-o{dest}", "--", str(src)], **quiet) if tool else None
        if (r is None or r.returncode != 0) and src.suffix.lower() == ".rar" and shutil.which("unrar"):
            r = subprocess.run(["unrar", "x", "-y", "-idq", "--", str(src), f"{dest}/"], **quiet)
        if (r is None or r.returncode != 0) and shutil.which("bsdtar"):
            r = subprocess.run(["bsdtar", "-xf", str(src), "-C", str(dest)], **quiet)
        if r is None or r.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            sys.exit(f"error: could not unpack {src.name}. It is damaged, or needs a tool that is not installed (7z, unrar).")
    untangle_backslashes(dest)
    root = dest.resolve()
    for d, dirs, files in os.walk(dest):
        for n in dirs + files:
            q = Path(d) / n
            if q.is_symlink() or root not in q.resolve().parents:
                sys.exit(f"error: {src.name} contains a link or a path outside the mod folder ({n[:120]}); not adding it")
            if has_control_chars(n):
                sys.exit(f"error: {src.name} contains a file name with control characters; not adding it")


def cmd_unpack(a):
    """Used by the window: unpack with the same checks `add` applies."""
    dest = Path(a.dest).expanduser()
    try:
        extract(Path(a.source).expanduser(), dest)
    except SystemExit:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    print("unpacked")


def find_layout_root(tmp: Path):
    """Return (folder holding game-relative content, prefix to put in front of each path)."""
    cur = tmp
    for _ in range(3):  # allow up to two wrapper folders
        entries = [e for e in cur.iterdir()]
        names = {e.name.lower() for e in entries}
        if "fomod" in names:
            sys.exit("error: this mod ships an installer with choices (a 'fomod' folder). Unpack it by hand, keep only the "
                     "option you want in game-folder layout (archive/, bin/, r6/, red4ext/ ...), then `add` that folder.")
        if names & GAME_TOP_DIRS:
            return cur, ""
        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]
        if files and all(f.suffix.lower() in LOOSE_ARCHIVE_EXT or f.suffix.lower() in {".txt", ".md"} for f in files) \
                and any(f.suffix.lower() == ".archive" for f in files) and not dirs:
            return cur, "archive/pc/mod/"
        if len(dirs) == 1 and not [f for f in files if f.suffix.lower() not in {".txt", ".md", ".url"}]:
            cur = dirs[0]
            continue
        break
    listing = ", ".join(sorted(e.name for e in cur.iterdir())[:12])
    sys.exit(f"error: cannot tell where this mod's files go. Top level holds: {listing}\n"
             "Arrange it in game-folder layout (archive/, bin/, r6/, red4ext/ ...) in a folder and `add` that folder.")


@changes_store
def cmd_add(a):
    src = Path(a.source).expanduser()
    if not src.exists():
        sys.exit(f"error: {src} not found")
    man = load_manifest(a.store)
    game = find_game(a.game)
    state = load_state(a.store)
    name = a.name or (src.name if src.is_dir() else src.stem)
    check_mod_name(name)
    if name in man["disabled"]["mods"]:
        sys.exit(f"error: a mod named '{name}' is in the store but disabled. Enable it first to update it, "
                 "or remove it, or use --name to add this one under another name.")
    old = None
    if a.update:
        old = match_mod(man, a.update, pool=man["mods"])
        if old == name:
            old, a.replace = None, True      # same name: a plain replace
    replacing = name in man["mods"]
    if replacing and not a.replace:
        sys.exit(f"error: a mod named '{name}' is already in the store. Use --replace to update it, or --name to add it under another name.")
    tmp = a.store / "incoming" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    try:
        extract(src, tmp)
        root, prefix = find_layout_root(tmp)
        new = []
        for d, _, files in os.walk(root):
            for n in files:
                q = Path(d) / n
                rel = prefix + q.relative_to(root).as_posix()
                if rel.split("/")[0].lower() not in GAME_TOP_DIRS:
                    continue  # readme, screenshots and the like next to the game folders
                new.append((q, rel))
        if not new:
            sys.exit("error: nothing to install found in it")
        if any(rel.split("/")[0].lower() == "mods" for _, rel in new):
            print("note: this is a REDmod-style mod (mods/ folder). It only loads if the REDmod DLC is installed and the game is started with -modded.")
        clashes = find_clashes(man, state, game, name, [rel for _, rel in new], also_ignore=old)
        if clashes and not a.force:
            print(f"not adding '{name}': {len(clashes)} of its {len(new)} files would replace existing ones:")
            for c in clashes[:25]:
                print("  ", c)
            print("Nothing was changed. If the overlap is intended (a patch for another mod), remove or disable the other mod first or use --force.")
            sys.exit(1)
        if a.dry_run:
            print(f"dry run: '{name}' would add {len(new)} files" + (f", replacing '{old}'" if old else "") + ":")
            for _, rel in sorted(new, key=lambda x: x[1])[:40]:
                print("  ", rel)
            if len(new) > 40:
                print(f"   ... and {len(new) - 40} more")
            return
        if replacing:
            remove_from_game(a.store, state, name)
            old = a.store / "mods" / name
            if old.exists():
                shelve(a.store, old)
            man["files"] = [f for f in man["files"] if f["mod"] != name]
        if old:
            remove_from_game(a.store, state, old)
            if (a.store / "mods" / old).exists():
                shelve(a.store, a.store / "mods" / old)
            man["files"] = [f for f in man["files"] if f["mod"] != old]
            man["mods"] = [m for m in man["mods"] if m != old]
            print(f"replaced '{old}' (its folder is kept under {a.store / 'removed'})")
        mod_dir = a.store / "mods" / name
        for q, rel in new:
            t = mod_dir / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(q), str(t))
            man["files"].append({"mod": name, "path": rel, "size": t.stat().st_size, "sha256": sha256(t)})
        if name not in man["mods"]:
            man["mods"].append(name)
        save_manifest(a.store, man)
        keep = Path(a.keep_archive).expanduser() if a.keep_archive else (src if src.is_file() else None)
        if keep and keep.is_file():
            arch = a.store / "archives"
            arch.mkdir(exist_ok=True)
            shutil.copy2(keep, arch / keep.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"added '{name}': {len(new)} files")
    if a.no_deploy:
        print("not deployed yet (--no-deploy); run `deploy` then `verify`")
        return
    a.force, a.dry_run = False, False
    cmd_deploy(a)
    cmd_verify(a)


@changes_store
def cmd_remove(a):
    man, state = load_manifest(a.store), load_state(a.store)
    name = match_mod(man, a.mod)
    files = [f for f in man["files"] + man["disabled"]["files"] if f["mod"] == name]
    if a.dry_run:
        print(f"dry run: would remove '{name}' ({len(files)} files) from the game and move it to {a.store / 'removed'}")
        return
    n = remove_from_game(a.store, state, name) if state.get("game") else 0
    for part in (man, man["disabled"]):
        part["files"] = [f for f in part["files"] if f["mod"] != name]
        part["mods"] = [m for m in part["mods"] if m != name]
    save_manifest(a.store, man)
    d = a.store / "mods" / name
    if d.exists():
        shelve(a.store, d)
    print(f"removed '{name}': {n} files taken out of the game; its folder is kept under {a.store / 'removed'}")


@changes_store
def cmd_disable(a):
    man, state = load_manifest(a.store), load_state(a.store)
    name = match_mod(man, a.mod)
    if name in man["disabled"]["mods"]:
        print(f"'{name}' is already disabled")
        return
    files = [f for f in man["files"] if f["mod"] == name]
    if a.dry_run:
        print(f"dry run: would take the {len(files)} files of '{name}' out of the game and keep the mod in the store")
        return
    n = remove_from_game(a.store, state, name) if state.get("game") else 0
    man["files"] = [f for f in man["files"] if f["mod"] != name]
    man["mods"] = [m for m in man["mods"] if m != name]
    man["disabled"]["files"] += files
    man["disabled"]["mods"].append(name)
    save_manifest(a.store, man)
    print(f"disabled '{name}': {n} files taken out of the game; the mod stays in the store")


@changes_store
def cmd_enable(a):
    man, state = load_manifest(a.store), load_state(a.store)
    name = match_mod(man, a.mod)
    if name in man["mods"]:
        print(f"'{name}' is already enabled")
        return
    game = find_game(a.game)
    check_build(game, man, a.force)
    files = [f for f in man["disabled"]["files"] if f["mod"] == name]
    clashes = find_clashes(man, state, game, name, [f["path"] for f in files])
    if clashes and not a.force:
        print(f"not enabling '{name}': {len(clashes)} of its {len(files)} files would replace existing ones:")
        for c in clashes[:25]:
            print("  ", c)
        print("Nothing was changed. Disable or remove the other mod first, or use --force.")
        sys.exit(1)
    plan = plan_deploy(a.store, game, state, files, a.force)
    if a.dry_run:
        print(f"dry run: would put the {len(files)} files of '{name}' back into the game")
        return
    man["disabled"]["files"] = [f for f in man["disabled"]["files"] if f["mod"] != name]
    man["disabled"]["mods"] = [m for m in man["disabled"]["mods"] if m != name]
    man["files"] += files
    man["mods"].append(name)
    save_manifest(a.store, man)
    run_plan(a.store, game, state, plan)
    print(f"enabled '{name}': {len(files)} files placed in the game")


# ---------------------------------------------------------------- list, info, status

def cmd_list(a):
    man, state = load_manifest(a.store), load_state(a.store)
    rows = mod_rows(man, state)
    if a.json:
        print(json.dumps(rows))
        return
    for r in rows:
        print(f"  {r['state']:<11}  {r['files']:4d} files  {r['name']}")
    off = len(man["disabled"]["mods"])
    print(f"{len(rows)} mods ({off} disabled), {len(man['files']) + len(man['disabled']['files'])} files in {a.store}")


def cmd_info(a):
    man, state = load_manifest(a.store), load_state(a.store)
    name = match_mod(man, a.mod)
    row = [r for r in mod_rows(man, state) if r["name"] == name][0]
    files = sorted(f["path"] for f in man["files"] + man["disabled"]["files"] if f["mod"] == name)
    if a.json:
        print(json.dumps({**row, "paths": files, "folder": str(a.store / "mods" / name)}))
        return
    print(f"{name}\n  state: {row['state']}, {row['files']} files, {human_size(row['size'])}")
    if row["nexus_id"]:
        print(f"  Nexus: https://www.nexusmods.com/{NEXUS_GAME}/mods/{row['nexus_id']}  (version {row['version']})")
    print(f"  folder: {a.store / 'mods' / name}")
    for p in files:
        print("   ", p)


def cmd_status(a):
    has_store = (a.store / "manifest.json").is_file()
    game = find_game(a.game, required=False)
    if a.json:
        out = {"store": str(a.store), "has_store": has_store, "game": str(game) if game else None,
               "steam": bool(game and is_steam_install(game)), "config": str(CONFIG)}
        if has_store:
            man, state = load_manifest(a.store), load_state(a.store)
            out.update({"mods": len(man["mods"]), "disabled": len(man["disabled"]["mods"]),
                        "files_deployed": len(state["files"]), "settings_saved": len(man["settings"]),
                        "build_recorded": str(man["game"].get("buildid") or ""),
                        "build_installed": game_build(game) if game else None,
                        "deployed_at": state.get("deployed_at")})
        print(json.dumps(out))
        return
    if not has_store:
        print(f"store: {a.store} (not set up yet; run `init`)\ngame:  {game or '(not found)'}")
        return
    state = load_state(a.store)
    mods = sorted({v["mod"] for v in state["files"].values()})
    print(f"store: {a.store}\ngame:  {state.get('game', '(not deployed)')}\n"
          f"files: {len(state['files'])} from {len(mods)} mods, settings: {len(state.get('settings', {}))}")
    for m in mods:
        print("  ", m)


# ---------------------------------------------------------------- command line

def build_parser():
    from . import doctor   # imported here because doctor itself builds on this module
    ap = argparse.ArgumentParser(prog="samurai-mm", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, help=f"mod store (default: the saved setting, else {DEFAULT_STORE})")
    ap.add_argument("--game", help="path to the 'Cyberpunk 2077' folder (default: the saved setting, else found through Steam)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, fn, *flags):
        s = sub.add_parser(name)
        for f in flags:
            s.add_argument(f, action="store_true")
        s.set_defaults(fn=fn)
        return s

    cmd("init", cmd_init)
    cmd("deploy", cmd_deploy, "--dry-run", "--force")
    cmd("undeploy", cmd_undeploy, "--dry-run")
    cmd("verify", cmd_verify)
    cmd("settings", cmd_settings)
    cmd("logs", doctor.cmd_logs)
    cmd("accept-build", cmd_accept_build)
    cmd("status", cmd_status, "--json")
    cmd("list", cmd_list, "--json")
    cmd("doctor", doctor.cmd_doctor, "--json")
    s = cmd("info", cmd_info, "--json")
    s.add_argument("mod", help="mod name or a unique part of it")
    s = cmd("add", cmd_add, "--replace", "--dry-run", "--no-deploy", "--force")
    s.add_argument("source", help="downloaded archive (zip/7z/rar) or an unpacked folder")
    s.add_argument("--name", help="mod name in the store (default: the archive's file name)")
    s.add_argument("--keep-archive", help="when adding from a folder: the original download to keep under archives/")
    s.add_argument("--update", metavar="OLD", help="the installed mod this download is a newer version of; it is replaced")
    for name, fn, flags in (("remove", cmd_remove, ("--dry-run",)), ("disable", cmd_disable, ("--dry-run",)),
                            ("enable", cmd_enable, ("--dry-run", "--force"))):
        s = cmd(name, fn, *flags)
        s.add_argument("mod", help="mod name or a unique part of it")
    s = cmd("unpack", cmd_unpack)
    s.add_argument("source")
    s.add_argument("dest")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if os.geteuid() == 0 and os.environ.get("SAMURAI_MM_ALLOW_ROOT") != "1":
        sys.exit("error: do not run this as root (or with sudo). Files it creates would belong to root, "
                 "and Steam and the game could no longer change them.")
    a.store = (a.store or Path(load_config().get("store") or DEFAULT_STORE)).expanduser()
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit("\ninterrupted. What was already placed in the game is on record; run the command again to finish.")
    except PermissionError as e:
        sys.exit(f"error: no permission to write {e.filename}. Check who owns that folder (running a tool with sudo "
                 "earlier can cause this). Run the command again once that is fixed.")
    except OSError as e:
        sys.exit(f"error: {e.strerror or e}" + (f": {e.filename}" if e.filename else "") +
                 ". Run the command again once that is fixed; `verify` shows whether anything is missing.")


if __name__ == "__main__":
    main()
