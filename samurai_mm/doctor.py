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
import subprocess
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
FRAMEWORK_NEEDS = {"ArchiveXL": "RED4ext", "TweakXL": "RED4ext", "Codeware": "RED4ext"}    # these are RED4ext plugins
RUNTIMES = ("vcrun2022", "d3dcompiler_47")      # what RED4ext and Cyber Engine Tweaks need inside the Proton prefix

# System packages by distribution family: the install command, then each tool's package name there.
PACKAGE_INSTALL = {"arch": "sudo pacman -S --needed", "fedora": "sudo dnf install", "debian": "sudo apt install",
                   "suse": "sudo zypper install"}
PACKAGE_NAMES = {
    "7zip": {"arch": "7zip", "fedora": "p7zip p7zip-plugins", "debian": "7zip", "suse": "7zip"},
    "unrar": {"arch": "unrar", "fedora": "unrar", "debian": "unrar", "suse": "unrar"},
    "protontricks": {"arch": "protontricks", "fedora": "protontricks", "debian": "protontricks", "suse": "protontricks"},
}
FAMILIES = (("arch", ("arch", "cachyos", "endeavouros", "manjaro", "garuda")), ("fedora", ("fedora", "rhel", "nobara", "bazzite")),
            ("debian", ("debian", "ubuntu", "linuxmint", "pop")), ("suse", ("opensuse", "suse")))
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


def distro_family():
    """arch, fedora, debian or suse, from /etc/os-release; None if it is something else."""
    try:
        text = Path(os.environ.get("SAMURAI_MM_OS_RELEASE") or "/etc/os-release").read_text(errors="replace")   # the variable is for tests
    except OSError:
        return None
    ids = []
    for key in ("ID", "ID_LIKE"):
        m = re.search(rf'^{key}=("?)(.*)\1\s*$', text, re.M)
        if m:
            ids += m.group(2).lower().split()
    for family, names in FAMILIES:
        if any(i in names for i in ids):
            return family
    return None


def package_command(tool):
    """The command that installs a system tool on this distribution, or None if the distribution is not known."""
    family = distro_family()
    if family is None:
        return None
    return f"{PACKAGE_INSTALL[family]} {PACKAGE_NAMES[tool][family]}"


def package_step(text, tool):
    """A step that installs a system package: run in a terminal where the command is known, plain words otherwise."""
    command = package_command(tool)
    if command:
        return step(text, {"type": "terminal", "label": "Install it in a terminal", "command": command})
    return step(f"{text} Use your distribution's package manager; the package is usually called {tool}.")


def step(text, action=None):
    return {"text": text, "action": action}


def protontricks_command():
    """How to run Protontricks here (as a normal program or as a Flatpak), or None if it is not installed."""
    exe = shutil.which("protontricks")
    if exe:
        return [exe]
    app = "com.github.Matoking.protontricks"
    if shutil.which("flatpak") and any((base / "app" / app).is_dir() for base in
                                        (Path.home() / ".local/share/flatpak", Path("/var/lib/flatpak"))):
        return ["flatpak", "run", app]
    return None


def missing_runtimes(pfx: Path):
    log = pfx / "winetricks.log"
    done = set(log.read_text(errors="replace").split()) if log.is_file() else set()
    return [v for v in RUNTIMES if v not in done]


def launch_options_wanted(opts, dlls):
    """The whole launch-options line the user should end up with, keeping what they already have."""
    override = 'WINEDLLOVERRIDES="' + ",".join(dlls) + '=n,b"'
    opts = (opts or "").strip()
    if not opts:
        return f"{override} %command%"
    if "WINEDLLOVERRIDES" in opts:
        return re.sub(r'WINEDLLOVERRIDES=(?:"[^"]*"|\'[^\']*\'|\S+)', lambda m: override, opts, count=1)
    if "%command%" in opts:
        return f"{override} {opts}"
    return f"{override} %command% {opts}"


def run_doctor(store: Path, game_arg):
    """Every check as {id, title, status, detail, fix, steps}. `steps` is what to do about it, in order: each step
    has a text and, where the manager can help, an action the window turns into a button."""
    checks = []

    def add(key, title, status, detail="", fix="", steps=None):
        checks.append({"id": key, "title": title, "status": status, "detail": detail, "fix": fix, "steps": steps or []})

    game = find_game(game_arg, required=False)
    if not game:
        add("game", "Game folder", "fail", "Cyberpunk 2077 was not found in any Steam library.",
            "Install the game, or set the game folder in the settings (--game).",
            [step("Install Cyberpunk 2077 through Steam (or Heroic or Lutris) if it is not installed yet."),
             step("If it is installed in an unusual place, choose its folder on the Settings tab.",
                  {"type": "tab", "label": "Open Settings", "tab": "settings"})])
        return checks
    add("game", "Game folder", "ok", str(game))
    on_steam = is_steam_install(game)

    has_store = (store / "manifest.json").is_file()
    man = load_manifest(store) if has_store else None
    state = load_state(store) if has_store else {"files": {}, "settings": {}}
    if not has_store:
        add("store", "Mod store", "warn", f"No store at {store} yet.", "Run `init` (the Set up button).",
            [step("Create the folder the manager keeps your mods in.", {"type": "run", "label": "Set up", "args": ["init"]})])
    else:
        add("store", "Mod store", "ok", f"{store}: {len(man['mods'])} enabled, {len(man['disabled']['mods'])} disabled")
        have, want = game_build(game), str(man["game"].get("buildid") or "")
        if want and have != want:
            add("build", "Game version", "fail", f"The game is now build {have}; the mods were set up for {want}.",
                "Update the frameworks for the new game version (add --update), then run accept-build.",
                [step("The game was updated. Mods are not put into the game until you confirm the frameworks match it."),
                 step("For each framework you use (they are listed below), open its Nexus page and download the version "
                      "made for the new game version."),
                 step("Install each download from the Install tab. The manager offers to update the old one."),
                 step("Then tell the manager the new game version is fine.", {"type": "accept-build", "label": "Accept version"})])
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
        "" if has_7z else "Install 7-Zip so zip, 7z and rar downloads all unpack" + (f": {package_command('7zip')}" if package_command("7zip") else "."),
        [] if has_7z else [package_step("Install 7-Zip. The manager uses it to unpack the mods you download.", "7zip")])
    if has_7z and "unrar" not in tools:
        add("unrar", "unrar (optional)", "info", "Not installed. 7-Zip opens most rar downloads; a few newer ones need unrar.",
            (package_command("unrar") or "") if package_command("unrar") else "",
            [package_step("Only if a rar download fails to unpack: install unrar.", "unrar")])

    fw = installed_frameworks(game)
    need = needed_frameworks(man) if man else {}
    for name, _, nexus in FRAMEWORKS:
        users = sorted(need.get(name, ()))
        if fw[name]:
            add("fw:" + name, name, "ok", "installed" + (f", used by {len(users)} mod{'s' if len(users) != 1 else ''}" if users else ""))
            continue
        page = f"https://www.nexusmods.com/{NEXUS_GAME}/mods/{nexus}"
        steps = []
        base = FRAMEWORK_NEEDS.get(name)
        if base and not fw[base]:
            steps.append(step(f"Install {base} first (see its own entry here). {name} is a plugin for it."))
        steps += [step("Open its Nexus page, go to the Files tab and choose Manual download on the main file.",
                       {"type": "url", "label": "Open its Nexus page", "url": page + "?tab=files"}),
                  step("When the download has finished, install it.", {"type": "install", "label": "Install this download", "nexus_id": nexus})]
        if name in ("RED4ext", "Cyber Engine Tweaks"):
            steps.append(step("After that, two more entries appear here: the Windows runtimes it needs and the Steam launch options. "
                              "It only loads once both are done."))
        if users:
            add("fw:" + name, name, "fail",
                f"Not installed, but {len(users)} enabled mod{'s need' if len(users) != 1 else ' needs'} it: " + "; ".join(users[:4]) + (" ..." if len(users) > 4 else ""),
                f"Download it from {page} and install it like any mod.", steps)
        else:
            add("fw:" + name, name, "info", "Not installed. None of your mods needs it yet; many popular mods do.",
                f"Download it from {page} and install it like any mod.", steps)

    uses_dll_loaders = fw["RED4ext"] or fw["Cyber Engine Tweaks"]
    dlls = (["winmm"] if fw["RED4ext"] else []) + (["version"] if fw["Cyber Engine Tweaks"] else [])
    override = 'WINEDLLOVERRIDES="' + ",".join(dlls) + '=n,b"'
    pfx = find_prefix(game)
    if pfx is None:
        add("prefix", "Proton prefix", "warn" if on_steam else "info",
            "No Steam Proton prefix found for the game." if on_steam else
            "Not a Steam install, so the prefix and launch options cannot be checked from here.",
            "Launch the game once from Steam so Proton creates it." if on_steam else "",
            [step("Start the game once through Steam and quit at the main menu. Proton sets up its Windows folder on first launch.",
                  {"type": "launch", "label": "Launch the game"})] if on_steam else [])
    else:
        add("prefix", "Proton prefix", "ok", str(pfx))
        if uses_dll_loaders:
            missing = missing_runtimes(pfx)
            if not missing:
                add("runtimes", "Windows runtimes in the prefix", "ok", " and ".join(RUNTIMES) + " are installed")
            else:
                steps = []
                if protontricks_command() is None:
                    steps.append(package_step("Install Protontricks, the tool that adds Windows runtimes to a Steam game.", "protontricks"))
                steps += [step("Close the game if it is running."),
                          step("Install the runtimes into the game's Proton prefix. They are downloaded from Microsoft, and it "
                               "takes a few minutes; progress shows in the output pane.",
                               {"type": "run", "label": "Install the runtimes", "args": ["runtimes"]})]
                add("runtimes", "Windows runtimes in the prefix", "warn", "Not installed yet: " + ", ".join(missing) +
                    ". RED4ext and Cyber Engine Tweaks do not load without them.",
                    f"samurai-mm runtimes   (it runs: protontricks {APPID} -q " + " ".join(missing) + ")", steps)
    if uses_dll_loaders and not on_steam:
        add("launch", "DLL overrides", "info",
            "This is not a Steam install, so the launcher settings cannot be read from here. RED4ext needs the winmm override "
            "and Cyber Engine Tweaks the version override.",
            f'In Heroic or Lutris, add this environment variable for the game: {override}. '
            "Also install vcrun2022 and d3dcompiler_47 into its prefix with winetricks.",
            [step("Copy this setting: " + override, {"type": "copy", "label": "Copy it", "text": override}),
             step("In Heroic or Lutris, open the game's settings and add it as an environment variable "
                  "(name WINEDLLOVERRIDES, value " + ",".join(dlls) + "=n,b)."),
             step("In the same settings, use Winetricks to install vcrun2022 and d3dcompiler_47 into the game's prefix.")])
    elif uses_dll_loaders:
        opts = steam_launch_options()
        native = native_overrides(opts)
        lacking = [d for d in dlls if d not in native]
        if not lacking:
            add("launch", "Steam launch options", "ok", opts)
        else:
            wanted = launch_options_wanted(opts, dlls)
            who = {"winmm": "RED4ext", "version": "Cyber Engine Tweaks"}
            detail = ("No launch options are set for the game." if opts is None else f"Current: {opts}") + \
                "\nMissing: " + ", ".join(f"{d} (for {who[d]})" for d in lacking) + ". Without it Proton ignores the mod loader."
            add("launch", "Steam launch options", "warn", detail, "In Steam: right-click the game, Properties, Launch Options: " + wanted,
                [step("Copy this line: " + wanted, {"type": "copy", "label": "Copy the line", "text": wanted}),
                 step("Open the game's properties in Steam.",
                      {"type": "steam", "label": "Open Steam properties", "url": f"steam://gameproperties/{APPID}"}),
                 step("On the General page, find Launch Options. Replace what is in the box with the line you copied "
                      "(it already contains what you had)."),
                 step("Steam only saves this to disk now and then, at the latest when it closes. If this entry stays yellow, "
                      "restart Steam and run the check again.")])
        if man and any(f["path"].lower().startswith("mods/") for f in man["files"]) and "-modded" not in (opts or ""):
            add("redmod", "REDmod mods", "warn", "REDmod-style mods (mods/ folder) are installed, but the game is not started with -modded.",
                "Add -modded after %command% in the launch options, and install the REDmod DLC.",
                [step("Install the free REDmod DLC for Cyberpunk 2077 from its Steam store page."),
                 step("Add -modded to the very end of the game's launch options in Steam.",
                      {"type": "steam", "label": "Open Steam properties", "url": f"steam://gameproperties/{APPID}"})])

    dupes = case_duplicates(game)
    add("case", "Upper/lower-case duplicates", "fail" if dupes else "ok",
        "; ".join(f"{w}: {' vs '.join(n)}" for w, n in dupes[:5]) if dupes else "none",
        "Merge the duplicate folders by hand; Windows games treat them as one folder, Linux does not." if dupes else "",
        [step("Two folders or files differ only in upper and lower case. Windows treats them as one, Linux does not, so the "
              "game sees only one of them."),
         step("Open the game folder and move the contents of one into the other, then delete the empty one.",
              {"type": "open", "label": "Open the game folder", "path": str(game)})] if dupes else [])
    stray = unmanaged_files(game, state)
    add("unmanaged", "Mod files this manager did not place", "warn" if stray else "ok",
        (f"{len(stray)} files, for example: " + "; ".join(stray[:5])) if stray else "none",
        "They were copied in by hand or by another tool. Remove them and add the mod through this manager so it can track it." if stray else "",
        [step("These were copied in by hand or by another tool, so the manager cannot switch or remove them."),
         step("Take them out of the game folder, then install the mod they came from on the Install tab.",
              {"type": "open", "label": "Open the game folder", "path": str(game)})] if stray else [])
    return checks


def cmd_doctor(a):
    checks = run_doctor(a.store, a.game)
    if a.json:
        print(json.dumps(checks))
        return
    label = {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "info": "INFO"}
    for c in checks:
        print(f"[{label[c['status']]}] {c['title']}: {c['detail']}")
        for n, st in enumerate(c["steps"], 1):
            print(f"       {n}. {st['text']}")
            act = st["action"] or {}
            extra = act.get("command") or act.get("url") or (("samurai-mm " + " ".join(act["args"])) if act.get("args") else "")
            if extra:
                print(f"          {extra}")
        if c["fix"] and not c["steps"]:
            print(f"       fix: {c['fix']}")
    bad = sum(1 for c in checks if c["status"] == "fail")
    warn = sum(1 for c in checks if c["status"] == "warn")
    print(f"doctor: {bad} problems, {warn} warnings")
    sys.exit(1 if bad else 0)


def cmd_runtimes(a):
    """Install the Windows runtimes RED4ext and Cyber Engine Tweaks need into the game's Proton prefix."""
    from .engine import clean_env, require_game_closed
    game = find_game(a.game)
    if not is_steam_install(game):
        sys.exit("error: this is not a Steam install, so Protontricks cannot reach it. In Heroic or Lutris, open the game's "
                 "settings and use Winetricks to install: " + " ".join(RUNTIMES))
    pfx = find_prefix(game)
    if pfx is None:
        sys.exit("error: the game has no Proton prefix yet. Start it once through Steam, quit at the main menu, then try again.")
    missing = missing_runtimes(pfx)
    if not missing:
        print("the runtimes are already installed: " + ", ".join(RUNTIMES))
        return
    tool = protontricks_command()
    if tool is None:
        sys.exit("error: Protontricks is not installed. Install it" +
                 (f" ({package_command('protontricks')})" if package_command("protontricks") else " with your package manager") +
                 ", then run this again.")
    cmd = tool + [APPID, "-q"] + missing
    if a.dry_run:
        print("dry run: would run: " + " ".join(cmd))
        return
    require_game_closed(a)
    print("running: " + " ".join(cmd))
    print("This downloads the runtimes from Microsoft and installs them. It can take a few minutes.", flush=True)
    try:
        code = subprocess.run(cmd, env=clean_env(), stdin=subprocess.DEVNULL).returncode
    except OSError as e:
        sys.exit(f"error: could not start Protontricks: {e}")
    still = missing_runtimes(pfx)
    if still:
        sys.exit(f"error: Protontricks ended (exit code {code}) but these are still not installed: " + ", ".join(still) +
                 ". Its messages above say why. Steam must have been started at least once, and the game must be closed.")
    print("installed the runtimes: " + ", ".join(missing))


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
