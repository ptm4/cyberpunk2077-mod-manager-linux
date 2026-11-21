# For whoever works on the code

Nothing in this folder is needed to use Samurai Mod Manager.

While working on the code, install with `sh install.sh --in-place` so the commands and the menu entry run
straight from this checkout. A plain `sh install.sh` copies the program to `~/.local/share/samurai-mm/app`.

| Path | What it is |
| --- | --- |
| `tests/` | Automated tests. `python3 -m unittest discover -s dev/tests` from the project folder; everything runs in temporary folders with a fake game |
| `tests/gui_drive.py` | Drives the real window through every flow against a sandbox, on a throwaway display (see the top of the file) |
| `make-release.sh` | Runs the tests and builds `dist/samurai-mod-manager-<version>.tar.gz` |
| `RELEASE-READINESS.md` | What was checked before the first public version, and what is still open |
| `REPO-SETTINGS.md` | The GitHub settings that keep `main` behind maintainer review (for the repository owner) |

## How the program is laid out

| Path | What it is |
| --- | --- |
| `samurai_mm/engine.py` | The mod store, deploying, and the command line (standard library only) |
| `samurai_mm/doctor.py` | The health check and the log check |
| `samurai_mm/ui/window.py` | The main window and the state the tabs share |
| `samurai_mm/ui/pages.py` | The four tabs: Mods, Install, Health, Settings |
| `samurai_mm/ui/setup.py` | The welcome step on first start |
| `samurai_mm/ui/picker.py`, `variants.py` | The chooser for downloads with variants or an installer |
| `samurai_mm/ui/runner.py`, `widgets.py`, `style.py` | Running engine commands, shared widgets, colours |

The window holds no mod logic: every button runs the same command-line engine as a separate
process and shows its output. A new feature usually means one engine command plus one small
piece of a tab.

The store keeps one folder per mod in game-folder layout, `manifest.json` (every file with
size and SHA-256) and `deployed.json` (what is in the game folder). Deploying copies files
into the game folder, as reflinks where the filesystem supports them.

## Before sending a change

Read `CONTRIBUTING.md` in the project folder. In short: run the tests, start new files with the
two-line SPDX license header, and sign off every commit with `git commit -s`.

## Images

`samurai_mm/data/icon.svg` and `banner.svg` are the sources. After changing them, render the PNGs:

```bash
rsvg-convert -w 256 -h 256 samurai_mm/data/icon.svg -o samurai_mm/data/icon.png
rsvg-convert -w 640 -h 600 samurai_mm/data/banner.svg -o samurai_mm/data/banner.png
```
