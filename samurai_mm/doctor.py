# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
"""samurai_mm.doctor - checks on the Linux side, and reading the game's logs after a launch.

`doctor` answers "is everything in place for my mods to load?": the frameworks the
installed mods need, the Proton prefix runtimes, the Steam launch options, game
updates, stray files. `logs` answers "did they actually load?" after a launch.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from .engine import (APPID, NEXUS_GAME, case_duplicates, find_game, find_prefix, game_build, is_steam_install, load_manifest,
                     load_state, resolve_ci, steam_roots)

# Frameworks other mods depend on: (name, files that mark it as installed, Nexus mod id)
FRAMEWORKS = [
    ("RED4ext", ["red4ext/RED4ext.dll", "bin/x64/winmm.dll"], 2380),
    ("Cyber Engine Tweaks", ["bin/x64/plugins/cyber_engine_tweaks.asi", "bin/x64/version.dll"], 107),
    ("redscript", ["engine/tools/scc.exe"], 1511),
    ("ArchiveXL", ["red4ext/plugins/ArchiveXL/ArchiveXL.dll"], 4198),
    ("TweakXL", ["red4ext/plugins/TweakXL/TweakXL.dll"], 4197),
    ("Codeware", ["red4ext/plugins/Codeware/Codeware.dll"], 7780),
]
# What a mod's files say about the framework it needs: (framework, test on a lower-case game-relative path)
REQUIREMENT_RULES = [
    ("RED4ext", lambda p: p.startswith("red4ext/plugins/")),
    ("Cyber Engine Tweaks", lambda p: p.startswith("bin/x64/plugins/cyber_engine_tweaks/mods/")),
    ("redscript", lambda p: p.startswith("r6/scripts/") and p.endswith(".reds")),
    ("ArchiveXL", lambda p: p.startswith("archive/pc/mod/") and p.endswith(".xl")),
    ("TweakXL", lambda p: p.startswith("r6/tweaks/")),
]
FRAMEWORK_OWN_PREFIX = {  # a framework's own files do not count as "a mod needing it"
    "RED4ext": ("red4ext/plugins/archivexl/", "red4ext/plugins/tweakxl/", "red4ext/plugins/codeware/"),
}


def vdf_app_blocks(text: str, appid: str):
    """Yield the text of every `"<appid>" { ... }` block in a Steam .vdf file."""
    for m in re.finditer(r'"%s"\s*\{' % re.escape(appid), text):
        depth, i, in_str = 1, m.end(), False
        while i < len(text) and depth:
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 1
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        yield text[m.end():i - 1]


def steam_launch_options():
    """The game's launch options from the most recently used Steam account that has any, or None."""
    best = None
    for root in steam_roots():
        for cfg in root.glob("userdata/*/config/localconfig.vdf"):
            try:
                text = cfg.read_text(errors="replace")
            except OSError:
                continue
            for block in vdf_app_blocks(text, APPID):
                m = re.search(r'"LaunchOptions"\s+"((?:[^"\\]|\\.)*)"', block)
                if m and (best is None or cfg.stat().st_mtime > best[0]):
                    best = (cfg.stat().st_mtime, m.group(1).replace('\\"', '"').replace("\\\\", "\\"))
    return best[1] if best else None


def native_overrides(launch_options: str):
    """DLL names set to load native-first by WINEDLLOVERRIDES in the launch options."""
    m = re.search(r'WINEDLLOVERRIDES=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', launch_options or "")
    if not m:
        return set()
    out = set()
    for group in (m.group(1) or m.group(2) or m.group(3) or "").split(";"):
        names, _, mode = group.partition("=")
        if mode.strip().lower().startswith("n"):
            out |= {n.strip().lower() for n in names.split(",") if n.strip()}
    return out


def installed_frameworks(game: Path):
    return {name: all(resolve_ci(game, rel).is_file() for rel in files) for name, files, _ in FRAMEWORKS}


def needed_frameworks(man):
    """framework -> names of enabled mods whose files need it."""
    need = {}
    for f in man["files"]:
        low = f["path"].lower()
        for fw, test in REQUIREMENT_RULES:
            if test(low) and not low.startswith(FRAMEWORK_OWN_PREFIX.get(fw, ("\0",))):
                need.setdefault(fw, set()).add(f["mod"])
    return need


def unmanaged_files(game: Path, state):
    """Mod files in the game folder that this tool did not place."""
    known = {k.lower() for k in state["files"]} | {k.lower() for k in state.get("settings", {})}
    found = []
    for top, exts in (("archive/pc/mod", {".archive", ".xl"}), ("r6/scripts", {".reds"}), ("r6/tweaks", {".yaml", ".yml", ".tweak"}),
                      ("red4ext/plugins", {".dll"}), ("bin/x64/plugins/cyber_engine_tweaks/mods", {".lua"})):
        base = resolve_ci(game, top)
        if not base.is_dir():
            continue
        for d, _, files in os.walk(base):
            for n in files:
                p = Path(d) / n
                if p.suffix.lower() in exts and str(p.relative_to(game)).lower() not in known:
                    found.append(str(p.relative_to(game)))
    return sorted(found)


def run_doctor(store: Path, game_arg):
    checks = []

    def add(key, title, status, detail="", fix=""):
        checks.append({"id": key, "title": title, "status": status, "detail": detail, "fix": fix})

    game = find_game(game_arg, required=False)
    if not game:
        add("game", "Game folder", "fail", "Cyberpunk 2077 was not found in any Steam library.",
            "Install the game, or set the game folder in the settings (--game).")
        return checks
    add("game", "Game folder", "ok", str(game))

    has_store = (store / "manifest.json").is_file()
    man = load_manifest(store) if has_store else None
    state = load_state(store) if has_store else {"files": {}, "settings": {}}
    if not has_store:
        add("store", "Mod store", "warn", f"No store at {store} yet.", "Run `init` (the Set up button).")
    else:
        add("store", "Mod store", "ok", f"{store}: {len(man['mods'])} enabled, {len(man['disabled']['mods'])} disabled")
        have, want = game_build(game), str(man["game"].get("buildid") or "")
        if want and have != want:
            add("build", "Game version", "fail", f"The game is now build {have}; the mods were set up for {want}.",
                "Update the frameworks for the new game version (Install as: Update), then accept the new build.")
        else:
            add("build", "Game version", "ok", f"build {have}")
        try:
            same_fs = os.stat(store).st_dev == os.stat(game).st_dev
        except OSError:
            same_fs = False
        add("disk", "Store and game on the same disk", "ok" if same_fs else "info",
            "Mod files can be shared with the game folder without using extra space." if same_fs else
            "They are on different filesystems, so every mod file is stored twice. That works, it just uses more space.")

    tools = [t for t in ("7z", "7zz", "7za", "unrar", "bsdtar") if shutil.which(t)]
    has_7z = any(t.startswith("7z") for t in tools)
    add("unpack", "Unpacking tools", "ok" if has_7z else ("warn" if tools else "fail"),
        "found: " + (", ".join(tools) or "none"),
        "" if has_7z else "Install 7zip (Arch/CachyOS: sudo pacman -S 7zip) so zip, 7z and rar downloads all unpack.")

    fw = installed_frameworks(game)
    need = needed_frameworks(man) if man else {}
    for name, _, nexus in FRAMEWORKS:
        users = sorted(need.get(name, ()))
        if fw[name]:
            add("fw:" + name, name, "ok", "installed" + (f", used by {len(users)} mod{'s' if len(users) != 1 else ''}" if users else ""))
        elif users:
            add("fw:" + name, name, "fail",
                f"Not installed, but {len(users)} enabled mod{'s need' if len(users) != 1 else ' needs'} it: " + "; ".join(users[:4]) + (" ..." if len(users) > 4 else ""),
                f"Download it from https://www.nexusmods.com/{NEXUS_GAME}/mods/{nexus} and install it like any mod.")
        else:
            add("fw:" + name, name, "info", "not installed (no enabled mod needs it)")

    uses_dll_loaders = fw["RED4ext"] or fw["Cyber Engine Tweaks"]
    pfx = find_prefix(game)
    if pfx is None:
        on_steam = is_steam_install(game)
        add("prefix", "Proton prefix", "warn" if on_steam else "info",
            "No Steam Proton prefix found for the game." if on_steam else
            "Not a Steam install, so the prefix and launch options cannot be checked from here.",
            "Launch the game once from Steam so Proton creates it." if on_steam else "")
    else:
        add("prefix", "Proton prefix", "ok", str(pfx))
        if uses_dll_loaders:
            log = pfx / "winetricks.log"
            verbs = set(log.read_text(errors="replace").split()) if log.is_file() else set()
            missing = [v for v in ("vcrun2022", "d3dcompiler_47") if v not in verbs]
            add("runtimes", "Windows runtimes in the prefix", "warn" if missing else "ok",
                ("not recorded as installed: " + ", ".join(missing)) if missing else "vcrun2022 and d3dcompiler_47 are installed",
                f"protontricks {APPID} " + " ".join(missing) if missing else "")
    if uses_dll_loaders and not is_steam_install(game):
        add("launch", "DLL overrides", "info",
            "This is not a Steam install, so the launcher settings cannot be read from here. RED4ext needs the winmm override "
            "and Cyber Engine Tweaks the version override.",
            'In Heroic or Lutris, add this environment variable for the game: WINEDLLOVERRIDES="winmm,version=n,b". '
            "Also install vcrun2022 and d3dcompiler_47 into its prefix with winetricks.")
    elif uses_dll_loaders:
        wanted = ([("winmm", "RED4ext")] if fw["RED4ext"] else []) + ([("version", "Cyber Engine Tweaks")] if fw["Cyber Engine Tweaks"] else [])
        opts = steam_launch_options()
        native = native_overrides(opts)
        lacking = [f"{dll} (for {who})" for dll, who in wanted if dll not in native]
        want_str = 'WINEDLLOVERRIDES="' + ",".join(d for d, _ in wanted) + '=n,b" %command%'
        if opts is None:
            add("launch", "Steam launch options", "warn", "No launch options are set for the game.",
                "In Steam: right-click the game, Properties, Launch Options: " + want_str)
        elif lacking:
            add("launch", "Steam launch options", "warn", f"Current: {opts}\nMissing DLL overrides: " + ", ".join(lacking),
                "Add to the launch options (before %command%): " + want_str.replace(" %command%", ""))
        else:
            add("launch", "Steam launch options", "ok", opts)
        if man and any(f["path"].lower().startswith("mods/") for f in man["files"]) and "-modded" not in (opts or ""):
            add("redmod", "REDmod mods", "warn", "REDmod-style mods (mods/ folder) are installed, but the game is not started with -modded.",
                "Add -modded after %command% in the launch options, and install the REDmod DLC.")

    dupes = case_duplicates(game)
    add("case", "Upper/lower-case duplicates", "fail" if dupes else "ok",
        "; ".join(f"{w}: {' vs '.join(n)}" for w, n in dupes[:5]) if dupes else "none",
        "Merge the duplicate folders by hand; Windows games treat them as one folder, Linux does not." if dupes else "")
    stray = unmanaged_files(game, state)
    add("unmanaged", "Mod files this manager did not place", "warn" if stray else "ok",
        (f"{len(stray)} files, for example: " + "; ".join(stray[:5])) if stray else "none",
        "They were copied in by hand or by another tool. Remove them and add the mod through this manager so it can track it." if stray else "")
    return checks


def cmd_doctor(a):
    checks = run_doctor(a.store, a.game)
    if a.json:
        print(json.dumps(checks))
        return
    label = {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    for c in checks:
        print(f"[{label[c['status']]}] {c['title']}: {c['detail']}")
        if c["fix"]:
            print(f"       fix: {c['fix']}")
    bad = sum(1 for c in checks if c["status"] == "fail")
    warn = sum(1 for c in checks if c["status"] == "warn")
    print(f"doctor: {bad} problems, {warn} warnings")
    sys.exit(1 if bad else 0)


def newest(game: Path, rel_dir: str, pattern: str):
    d = resolve_ci(game, rel_dir)
    if not d.is_dir():
        return None
    c = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime)
    return c[-1] if c else None


def cmd_logs(a):
    game = find_game(a.game)
    man = load_manifest(a.store)
    state = load_state(a.store)
    ok = True
    # A store may list exactly which plugins should load ("expected"); otherwise go by what is deployed.
    exp = man.get("expected", {})
    plugins_expected = exp.get("plugins")
    deployed = [k.lower() for k in state["files"]]
    plugin_dirs = {p.split("/")[2] for p in deployed if p.startswith("red4ext/plugins/") and p.endswith(".dll") and p.count("/") >= 3}
    cet_expected = exp.get("cet_mods")
    if cet_expected is None:
        real = {k.split("/")[5] for k in state["files"] if k.lower().startswith("bin/x64/plugins/cyber_engine_tweaks/mods/")
                and k.lower().endswith("/init.lua") and k.count("/") == 6}
        cet_expected = sorted(real)

    def report(name, good, detail=""):
        nonlocal ok
        ok = ok and good
        print(f"[{'PASS' if good else 'FAIL'}] {name} {detail}")

    fw = installed_frameworks(game)
    if fw["RED4ext"]:
        r = newest(game, "red4ext/logs", "red4ext-*.log")
        dep = a.store / "deployed.json"
        if r and dep.is_file() and r.stat().st_mtime < dep.stat().st_mtime:
            report("logs are from a launch after the last change", False, f"- {r.name} is older than the last deploy; launch the game first")
        if not r:
            report("RED4ext log", False, "- none found: is the winmm DLL override set and vcrun2022 installed? (see doctor)")
        else:
            t = r.read_text(errors="replace")
            report("RED4ext initialized", "successfully initialized" in t, f"({r.name})")
            m = re.search(r"(\d+) plugin\(s\) loaded", t)
            if plugins_expected is not None:
                for p in plugins_expected:
                    report(f"  plugin {p}", re.search(re.escape(p) + r" \(version: .*\) has been loaded", t) is not None)
                want = len(plugins_expected)
            else:
                want = len(plugin_dirs)
            if plugins_expected is None and m and int(m.group(1)) != want:
                # counted from folders, which is only an estimate: say so instead of failing
                print(f"[INFO]   plugin count ({m.group(1)} loaded, about {want} installed)")
            else:
                report("  plugin count", bool(m) and int(m.group(1)) == want, f"({m.group(1) if m else '?'} loaded, {want} installed)")
            if fw["redscript"]:
                report("  redscript compile (scc)", "scc invoked successfully" in t)
            errs = [l for l in t.splitlines() if "[error" in l or "[critical" in l]
            report("  no RED4ext errors", not errs, f"({len(errs)} error lines)")
            for l in errs[:10]:
                print("     ", l)
    else:
        print("[INFO] RED4ext is not installed; skipping its log")
    if fw["Cyber Engine Tweaks"]:
        c = resolve_ci(game, "bin/x64/plugins/cyber_engine_tweaks/cyber_engine_tweaks.log")
        if not c.is_file():
            report("CET log", False, "- none found: is the version DLL override set and d3dcompiler_47 installed? (see doctor)")
        else:
            t = c.read_text(errors="replace")
            # CET appends to its logs across launches: judge only the newest session,
            # so lines from an earlier good run cannot hide a failure in the latest one.
            lines = t.splitlines()
            starts = [i for i, l in enumerate(lines) if "Cyber Engine Tweaks is starting" in l]
            since = lines[starts[-1]][1:20] if starts else ""
            if starts:
                t = "\n".join(lines[starts[-1]:])
            report("CET started", bool(starts), f"({c.name}, session {since or 'none'})")
            sl = c.with_name("scripting.log")
            st = sl.read_text(errors="replace") if sl.is_file() else ""
            if since:
                st = "\n".join(l for l in st.splitlines() if l[:1] != "[" or l[1:20] >= since)
            for m_ in cet_expected:
                report(f"  CET mod {m_}", f"Mod {m_} loaded!" in st)
            errs = [l for l in t.splitlines() if "[error" in l.lower()]
            report("  no CET errors", not errs, f"({len(errs)} error lines)")
            for l in errs[:10]:
                print("     ", l)
    else:
        print("[INFO] Cyber Engine Tweaks is not installed; skipping its log")
    if fw["redscript"]:
        s = resolve_ci(game, "r6/logs/redscript_rCURRENT.log")
        if s.is_file():
            t = s.read_text(errors="replace")
            report("redscript log has no errors", "[ERROR" not in t and "compilation failed" not in t.lower(), f"({s.name})")
        else:
            report("redscript log", False, "- none found")
    for name, rel, pat in (("ArchiveXL", "red4ext/plugins/ArchiveXL", "ArchiveXL-*.log"), ("TweakXL", "red4ext/plugins/TweakXL", "TweakXL-*.log")):
        if not fw[name]:
            continue
        f = newest(game, rel, pat)
        if f:
            errs = [l for l in f.read_text(errors="replace").splitlines() if "[error" in l.lower()]
            report(f"{name} log has no errors", not errs, f"({len(errs)} error lines, {f.name})")
            for l in errs[:5]:
                print("     ", l)
        else:
            report(f"{name} log", False, "- none found")
    if not any(fw.values()):
        print("no frameworks are installed, so there are no logs to check")
    sys.exit(0 if ok else 1)
