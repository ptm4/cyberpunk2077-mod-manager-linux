# Changelog

## 0.9.1 (beta)

- Open source under the GNU General Public License, version 3 or later. Contributions go through pull requests reviewed by the maintainer (see `CONTRIBUTING.md`).
- `samurai-mm --version` shows the version and license notice.
- An empty mod list or downloads folder says so, and a chosen download that was moved or deleted is dropped.
- Installer: checks for Python, GTK 4 and 7-Zip, shows the exact command for your distribution when something is missing and offers to run it, and copies the program to `~/.local/share/samurai-mm/app` so the unpacked folder can be deleted.
- New mascot: Tux as a cyber samurai (half machine, with horns, a red headband and fire rising from his head), all vector art (Tux by Larry Ewing, vector version by Garrett LeSage and IFo Hancroft), as the app icon and a larger, sharper side picture. The Cyberpunk 2077 artwork used during development is gone.
- The mod list can be sorted: by name, recently installed, biggest, or switched off first (`samurai-mm list --sort recent|size`). The choice is remembered.
- Launching the game talks to your Steam program directly. Before, it opened a `steam://` link through the desktop, which on some systems is claimed by a Windows Steam inside Wine and opened that instead.
- The Health tab now guides you: every entry that is not right lists numbered steps, with buttons that open a framework's Nexus page, install its download once it arrives, install the Windows runtimes (new `samurai-mm runtimes` command, through Protontricks), copy the launch options and open the game's properties in Steam, or run a package install in a terminal. It checks again by itself when you come back to the window.

## 0.9.0 (beta)

First version meant for other people's machines.

- Renamed to Samurai Mod Manager (commands `samurai-mm` and `samurai-mm-gui`).
- Welcome step on first start: confirm or choose the game folder, the mod store and the downloads folder.
- Mods can be switched off and on without removing them.
- A newer download of an installed mod is recognised and can replace the old version (`add --update`).
- Health check: frameworks the installed mods need, Proton prefix runtimes, Steam launch options, game updates, stray files, plus a file check and a log check.
- Finds the game in native, Flatpak and Snap Steam, and in Heroic (GOG, Epic) and Lutris installs.
- Hardening:
  - downloads are inspected before unpacking; paths pointing outside the mod folder, links, control characters in names and archives larger than the free disk space are refused;
  - Windows-style backslash paths inside archives are understood;
  - only one changing command works on a store at a time, so the window and the command line cannot overwrite each other's work;
  - nothing changes while the game is running;
  - refuses to run as root;
  - damaged mod lists, unwritable folders and damaged downloads give a plain message and advice instead of a Python error;
  - an interrupted deploy stays on record, so it can be finished or undone.
