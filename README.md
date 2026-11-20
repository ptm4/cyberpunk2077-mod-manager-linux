# Samurai Mod Manager

A mod installer and manager for **Cyberpunk 2077 on Linux** (Steam with Proton, also Heroic
and Lutris). Made and tested with game version 2.5.

Vortex has no Linux release, and copying mod files in by hand goes wrong on Linux in ways it
does not on Windows. Samurai Mod Manager does the copying for you and keeps track of every
file, so any mod, or all of them, can be taken out again cleanly.

Status: 0.9.0 beta. Built and used daily on CachyOS (Arch). It should run on any distribution
with Python 3.10+, GTK 4.12+ and PyGObject. A Windows version is planned later.

This is an unofficial fan project. It is not made, approved or supported by CD PROJEKT RED or
Nexus Mods. It never connects to the internet and collects nothing.

## What it does

- **Installs** zip, 7z and rar downloads, or an unpacked folder. It works out where
  the files go, and a dry run shows the plan first.
- **Asks instead of guessing.** Downloads with several variants, or with a FOMOD
  installer, open a chooser where you tick what you want.
- **Switches mods on and off** without deleting them.
- **Never overwrites** another mod's files or the game's own files unless you force it.
- **Removes cleanly.** Every placed file is recorded. One click takes all mods out
  (back to vanilla) and one click puts them back.
- **Handles upper/lower case.** Windows treats `R6/Scripts` and `r6/scripts` as one
  folder; Linux does not. Files are merged into whatever folders already exist.
- **Health check for the Linux side**: the frameworks your mods need (RED4ext,
  Cyber Engine Tweaks, redscript, ArchiveXL, TweakXL, Codeware), the Proton prefix
  runtimes, the Steam launch options (`WINEDLLOVERRIDES`), game updates, stray files.
- **Log check** after a launch: did the frameworks and mods actually load?
- Refuses to change anything while the game is running.
- **Updates**: a newer download of a mod you have is recognised and replaces the old version.
- One button takes every mod out for a vanilla session and puts them back afterwards.

Not there yet: load order and deliberate overwrites between mods (two mods that ship the
same file are refused, not merged), update checks and "Mod manager download" links from Nexus,
profiles, REDmod deployment, packages for the AUR or Flatpak, languages other than English.

## Install

Needs: Python 3.10+, GTK 4.12+ with PyGObject, and 7-Zip (plus `unrar` for some rar files).

| Distribution | Command |
| --- | --- |
| Arch, CachyOS, EndeavourOS | `sudo pacman -S gtk4 python-gobject 7zip unrar` |
| Fedora, Bazzite | `sudo dnf install gtk4 python3-gobject p7zip p7zip-plugins` |
| Ubuntu 24.04+, Mint 22+ | `sudo apt install gir1.2-gtk-4.0 python3-gi 7zip` |

The command line needs only Python and 7-Zip. Steam Deck: SteamOS does not let you install
these packages the normal way, so the window is untested there; the command line may work.

```bash
./install.sh            # commands in ~/.local/bin and an app-menu entry; no root, no packages
./install.sh --remove   # undo (mods and settings stay)
```

Or run it straight from this folder: `python3 -m samurai_mm.gui`.

## Use

Open **Samurai Mod Manager** from the app menu. On first start it shows the game
folder it found, where your mods will be kept (default `~/.local/share/samurai-mm/store`) and your
downloads folder, and lets you change each before anything is created.

1. On a mod's Nexus page choose **Manual download**.
2. On the **Install** tab pick it from your downloads folder, press **Dry run**, then **Install**.
3. Check the **Health** tab. It tells you if a framework, a Proton runtime or a launch
   option is missing, with the exact fix.

Everything is also available on the command line:

```bash
samurai-mm add ~/Downloads/"Some Mod-1234-1-0-1700000000.zip" --dry-run
samurai-mm add ~/Downloads/"Some Mod-1234-1-0-1700000000.zip"
samurai-mm list
samurai-mm disable "some mod"        # a unique part of the name is enough
samurai-mm enable "some mod"
samurai-mm remove "some mod"
samurai-mm add new.zip --update "some mod"   # replace an older version
samurai-mm doctor                    # the health check
samurai-mm logs                      # after a launch
samurai-mm undeploy                  # all mods out; `deploy` puts them back
samurai-mm --help
```

## How it works

- The **store** holds one folder per mod, in game-folder layout, plus `manifest.json`
  (every file with size and SHA-256) and `deployed.json` (what is in the game folder).
- **Deploying** copies files into the game folder. On btrfs and XFS the copies are
  reflinks, so they take no extra space when store and game are on the same disk.
- Removed mods are moved to `removed/` in the store, replaced settings to `backups/`.
  Nothing is deleted outright.
- The window is a thin layer: every button runs the same command-line engine and
  shows its output.

After a game update the manager stops deploying, because the frameworks are tied to
the game version. Update them (Install tab, "Install as: Update"), then accept the
new version on the Health tab.

## Layout

| Path | What it is |
| --- | --- |
| `samurai_mm/engine.py` | The mod store, deploying, and the command line (standard library only) |
| `samurai_mm/doctor.py` | The health check and the log check |
| `samurai_mm/ui/window.py` | The main window and the state the tabs share |
| `samurai_mm/ui/pages.py` | The four tabs: Mods, Install, Health, Settings |
| `samurai_mm/ui/setup.py` | The welcome step on first start |
| `samurai_mm/ui/picker.py`, `variants.py` | The chooser for downloads with variants or an installer |
| `samurai_mm/ui/runner.py`, `widgets.py`, `style.py` | Running engine commands, shared widgets, colours |
| `tests/` | `python3 -m unittest discover -s tests` runs in temp folders; `gui_drive.py` drives the real window against a sandbox |

A new feature usually means one engine command plus one small piece of a page, and the
window never does mod work itself.

## Safety

Mods are programs and data made by strangers. The manager checks what a download would write
before unpacking it, and it never runs anything from a download itself. It cannot tell you
whether a mod is trustworthy once the game loads it. Download from sources you trust, and read
the comments on a mod's page.

Your mods, the list of what is installed and every backup live in the mod store folder. Back
that folder up and you can rebuild everything.

## If something goes wrong

- The **Health** tab (or `samurai-mm doctor`) names the problem and the fix in most cases.
- **Play without mods** takes everything out; the game is vanilla again and your mods are kept.
- A removed mod is in `removed/` in the store; an earlier mod list is in `backups/manifest/`.
- When reporting a bug, include the text of the output pane (it has a Copy button).

## License

Copyright (c) 2026 ptm4. All rights reserved. Samurai Mod Manager is free to download and use.
You may read the source and change your own copy, but you may not redistribute it, re-upload
it, or publish modified versions without permission. The full terms are in `LICENSE`.
Suggestions and fixes are welcome.

## Artwork

The Samurai picture and the icon made from it come from Cyberpunk 2077 and belong to
CD PROJEKT S.A. They are included as non-commercial fan content so the manager is easy to
recognise. They are **not** covered by this project's license: if you reuse the code, do not
assume you may reuse the picture. If CD PROJEKT RED asks for it to be removed, it will be.

## Notes for whoever publishes this

See `docs/RELEASE-READINESS.md` for what was checked and what is still open.
