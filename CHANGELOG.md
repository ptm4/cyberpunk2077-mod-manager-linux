# Changelog

## 0.9.0 (beta)

First version meant for other people's machines.

- Renamed to Samurai Mod Manager (commands `samurai-mm` and `samurai-mm-gui`).
- The Samurai picture is the default side picture and the app icon (credit and terms in the README).
- Welcome step on first start: confirm or choose the game folder, the mod store and the downloads folder.
- Mods can be switched off and on without removing them.
- A newer download of an installed mod is recognised and can replace the old version (`add --update`).
- Health check: frameworks the installed mods need, Proton prefix runtimes, Steam launch options, game updates, stray files, plus a file check and a log check.
- Finds the game in native, Flatpak and Snap Steam, and in Heroic (GOG, Epic) and Lutris installs.
- License: all rights reserved; free to use, no redistribution without permission (see `LICENSE`).
- Hardening:
  - downloads are inspected before unpacking; paths pointing outside the mod folder, links, control characters in names and archives larger than the free disk space are refused;
  - Windows-style backslash paths inside archives are understood;
  - only one changing command works on a store at a time, so the window and the command line cannot overwrite each other's work;
  - nothing changes while the game is running;
  - refuses to run as root;
  - damaged mod lists, unwritable folders and damaged downloads give a plain message and advice instead of a Python error;
  - an interrupted deploy stays on record, so it can be finished or undone.
