# Release readiness: Samurai Mod Manager 0.9.0

Checked on 2026-11-19 on CachyOS (Python 3.14, GTK 4.24, 7-Zip 26.06, KDE Plasma on Wayland, NVIDIA).

## Verdict

**Ready for a public beta. Not ready to be called a finished 1.0.**

The core is sound: it does not lose track of files, it refuses hostile downloads, and it has
not damaged a store or a game folder in any test. What keeps it at "beta" is reach, not
safety: it has been run on one machine and one distribution, by one person, and it cannot yet
handle two mods that are meant to overwrite each other.

## Decisions only the owner can make

| # | Decision | Note |
| --- | --- | --- |
| 1 | **License** | Decided by the owner on 2026-11-19: all rights reserved. Free to download and use, source readable, no redistribution or published modified versions without permission (`LICENSE`). This can be loosened to an open-source license later; the reverse is not possible. The copyright line names `ptm4`; change it in `LICENSE`, `README.md` and `samurai_mm/__init__.py` if another name should appear. |
| 2 | **Where the code lives** | Decided: `github.com/ptm4/cyberpunk2077-mod-manager-linux`. The app id `io.github.ptm4.SamuraiModManager` matches that account. |
| 3 | **The name and the art** | Decided by the owner on 2026-11-19: the name stays, and the Samurai picture from the game ships with the manager as its side picture and icon, so people recognise it. The picture belongs to CD PROJEKT S.A.; the README credits it, says it is not covered by the project's license, and promises removal on request. Keep the project non-commercial (no paid downloads) for as long as it carries their art. |

## What was checked, and the result

### Hostile and broken downloads

| Check | Before | Now |
| --- | --- | --- |
| Archive entries with `../` (three spellings, including Windows backslashes) | 7-Zip defused them, but the junk file was still installed into the game | Refused before unpacking; nothing is written |
| Archive entry with an absolute path | Silently dropped | Refused before unpacking |
| Archive containing a link out of the folder | Refused after unpacking | Refused before unpacking (zip, 7z), and again after |
| Folder containing a link | Refused | Refused |
| File names with control characters (a newline) | Installed | Refused |
| Windows-made zip with `archive\pc\mod\x.archive` as one file name | Installed under a wrong, useless name | Understood and installed correctly |
| Archive claiming more data than the disk has free | Not checked | Refused before unpacking |
| Damaged archive | Raw tool output | Plain message, nothing changed |
| The manager runs code from a download | Never | Never (it only copies files) |

### Awkward but honest input

| Check | Before | Now |
| --- | --- | --- |
| Mod names starting with a dash (`-dash`, `--help`, real example `- Head Cyberware ...`) | Worked by luck | Worked on purpose: the window always separates names from options |
| 300-character mod name | Python error dump | Plain message |
| Mod name with a newline or slash | Newline accepted | Refused |
| Damaged mod list (`manifest.json`) | Python error dump | Message pointing at the automatic backups |
| Game folder not writable | Python error dump | Plain message; running the command again finishes the job |
| Game folder moved or uninstalled, then "Play without mods" | Silently did nothing useful | Plain message with what to do |
| Interrupted while placing files | Files in the game with no record | Record is kept, so it can be finished or undone |

### Two things at once

| Check | Before | Now |
| --- | --- | --- |
| Four installs started at the same moment | **One mod was lost from the list** (its files stayed behind, untracked) | All four recorded and verified; a store lock makes changing commands take turns |
| A second command while the store is busy | Raced | Waits up to a minute, then says the store is busy; reading and dry runs never wait |
| Changing mods while the game runs | Only the window refused | The engine refuses too, so the command line is covered |
| Run as root or with sudo | Allowed (would leave root-owned files Steam cannot change) | Refused |

### Other people's Linux setups

| Setup | Status |
| --- | --- |
| Steam, native package (this machine) | Tested for real |
| Steam as Flatpak or Snap | Paths are searched; **not tested on a real install** |
| Game in a second Steam library, another disk | Found through `libraryfolders.vdf`; the welcome step then suggests a store on the game's disk. Tested with simulated folders only |
| GOG or Epic through Heroic, or Lutris | Game folder is found from their config files; install, switch, verify work in tests with simulated folders. The health check cannot read their launch settings and says so. **Not tested on a real install** |
| Steam Deck (SteamOS) | **Untested.** SteamOS does not let users install GTK or Python packages the normal way; a Flatpak or AppImage would be needed for the window |
| No game installed, no mod store | Clear messages, no errors |
| Installed from a folder with spaces, into a home folder with spaces | Works |
| No display (ssh) | The window says so and exits; the command line works |

### Versions

| Check | Result |
| --- | --- |
| Python: source scanned for syntax newer than 3.10 (f-string quoting, backslashes) | None found. **Only actually run on Python 3.14** |
| GTK: needs 4.12 (file and alert dialogs, CSS loading) | Checked at start with a clear message. This rules out Ubuntu 22.04 and Debian 12 for the window; the command line still works there. **Only run on GTK 4.24** |
| Desktop: KDE Plasma on Wayland | Looks right. **GNOME, X11 and light themes are untested**; the window sets its own dark colours, which usually keeps it readable |
| Game version 2.5 | The manager itself is not tied to a game version. After a game update it stops deploying until the frameworks are updated and the new version is accepted |

### Code and packaging

| Check | Result |
| --- | --- |
| Automated tests | 45 pass: engine flows, hostile inputs, other launchers, display-free window helpers. One of them, a compatibility check against the script this project grew from, only runs when pointed at that script |
| Scripted run of the real window | 31 checks of every flow plus 7 of the welcome step pass, on a throwaway display against sandbox folders |
| Network use | None anywhere in the code (no sockets, no HTTP). Only two links are ever opened, in the user's browser or Steam: a mod's Nexus page and `steam://rungameid` |
| Shell injection | None possible: every external tool is started with an argument list, never through a shell, and file names are passed after `--` |
| Personal data in the source | None (no user names or home paths) |
| Unused imports | None |
| Speed on a real store (65 mods, 1032 files, 594 MB) | status, list, health check under 0.1 s each; full file check 0.5 s |
| Installer | Tested into a fake home, from and into paths with spaces, and its removal |
| Linters (ruff, shellcheck, bandit) | **Not run: not installed on this machine.** Worth running once before 1.0 |

## Known limits to state openly on the download page

1. **No overwrites or load order.** If two mods ship the same file, the second is refused. Patches that are meant to replace another mod's file need `--force` on the command line. This is the biggest gap compared with Vortex.
2. **FOMOD installers:** the common kind works (options, option groups, flags). Installers with file-existence conditions or nested conditions fall back to ticking folders by hand.
3. **REDmod** (`mods/` folder) mods are installed but not compiled or deployed through REDmod.
4. **No update checks and no "Mod manager download" button.** Downloads are manual; a button opens the mod's Nexus page.
5. **English only.**
6. **One store, no profiles.**
7. Mods copied into the game by hand or by another tool are reported by the health check, not taken over.

## Before 1.0

- Someone other than the author installs it from scratch on another distribution (Fedora or Ubuntu 24.04 would cover most users) and on Flatpak Steam.
- One real Heroic (GOG) install.
- Overwrite rules and load order.
- A package: AUR first, Flatpak for the Steam Deck.
- Run ruff, shellcheck and bandit.

## About the Windows version

The engine is plain Python and most of it carries over. What is Linux-only today: finding
the game (Steam paths, Heroic, Lutris), the running-game check (`/proc`), the store lock
(`fcntl`), copy-on-write copies (`cp --reflink`), and the whole health check (Proton, launch
options). On Windows the health check would shrink to frameworks and file checks, and
hard links would replace reflinks. The window toolkit (GTK4) runs on Windows but is awkward to
ship there; that choice should be revisited before starting.
