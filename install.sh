#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
# Installs Samurai Mod Manager for the current user. No root is needed for the manager itself.
#
#   sh install.sh             install (or update) it
#   sh install.sh --remove    remove it again; your mods and settings stay
#   sh install.sh --in-place  run it from this folder instead of copying it (for people changing the code)
#
# What it does: checks that Python, GTK 4 and 7-Zip are there (and offers to install what is missing, after
# asking), copies the program to ~/.local/share/samurai-mm/app, and adds two commands plus an app-menu entry.
# After that this folder is no longer needed.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
data="${XDG_DATA_HOME:-$HOME/.local/share}"
app="$data/samurai-mm/app"
bin="$HOME/.local/bin"
apps="$data/applications"
desktop="$apps/io.github.ptm4.SamuraiModManager.desktop"
mode="${1:-}"

say() { printf '%s\n' "$*"; }

if [ "$(id -u)" = 0 ]; then
    say "Do not run this as root or with sudo. Run it as yourself: sh install.sh"
    exit 1
fi

case "$mode" in
    ""|--in-place) ;;
    --remove)
        rm -f "$bin/samurai-mm" "$bin/samurai-mm-gui" "$desktop"
        case "$app" in */samurai-mm/app) rm -rf "$app" ;; esac
        say "Samurai Mod Manager is removed. Your mods and settings were not touched."
        exit 0 ;;
    *)
        say "Unknown option: $mode"
        say "Use: sh install.sh            (install or update)"
        say "     sh install.sh --remove   (remove)"
        exit 1 ;;
esac

if [ ! -f "$here/samurai_mm/engine.py" ]; then
    say "This does not look like the Samurai Mod Manager folder (samurai_mm is missing next to install.sh)."
    say "Unpack the whole download and run install.sh from inside it."
    exit 1
fi

# ---- what is missing?

need_python=no; need_gtk=no; need_7z=no; old_gtk=""
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    need_python=yes
elif ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null; then
    need_gtk=yes
elif ! python3 -c 'import gi, sys; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk; sys.exit(0 if (Gtk.get_major_version(), Gtk.get_minor_version()) >= (4, 12) else 1)' 2>/dev/null; then
    old_gtk=$(python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk; print("%d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version()))' 2>/dev/null || true)
fi
if ! command -v 7z >/dev/null 2>&1 && ! command -v 7zz >/dev/null 2>&1 && ! command -v 7za >/dev/null 2>&1; then
    need_7z=yes
fi

# ---- which distribution, and so which command installs the missing parts?

id=""; like=""
if [ -r /etc/os-release ]; then
    id=$(. /etc/os-release && printf '%s' "${ID:-}")
    like=$(. /etc/os-release && printf '%s' "${ID_LIKE:-}")
fi
pkg_cmd=""; pkg_note=""
case " $id $like " in
    *" arch "*|*" cachyos "*|*" endeavouros "*|*" manjaro "*)
        pkg_cmd="sudo pacman -S --needed python gtk4 python-gobject 7zip unrar" ;;
    *" fedora "*|*" rhel "*|*" nobara "*|*" bazzite "*)
        pkg_cmd="sudo dnf install python3 gtk4 python3-gobject p7zip p7zip-plugins"
        pkg_note="On an image-based Fedora (Bazzite, Silverblue) use rpm-ostree install instead of dnf install, then restart. If dnf cannot find p7zip, use 7zip in its place." ;;
    *" debian "*|*" ubuntu "*|*" linuxmint "*|*" pop "*)
        pkg_cmd="sudo apt install python3 python3-gi gir1.2-gtk-4.0 7zip" ;;
    *" opensuse "*|*" suse "*)
        pkg_cmd="sudo zypper install python3 python3-gobject typelib-1_0-Gtk-4_0 7zip" ;;
esac

if [ "$need_python$need_gtk$need_7z" != "nonono" ]; then
    say "Some things Samurai Mod Manager needs are missing on this computer:"
    [ "$need_python" = yes ] && say "  - Python 3.10 or newer"
    [ "$need_gtk" = yes ] && say "  - GTK 4 for Python (the window)"
    [ "$need_7z" = yes ] && say "  - 7-Zip (to unpack mod downloads)"
    say ""
    if [ -n "$pkg_cmd" ]; then
        say "This command installs them:"
        say "    $pkg_cmd"
        [ -n "$pkg_note" ] && say "  ($pkg_note)"
        if [ -t 0 ]; then
            printf 'Run it now? It will ask for your password. [y/N] '
            read -r answer || answer=""
            case "$answer" in
                y|Y|yes|Yes|YES) $pkg_cmd || say "That did not finish. You can run the command yourself and then run install.sh again." ;;
                *) say "Not installing them now." ;;
            esac
        fi
    else
        say "I do not know this distribution's package names. Install these with your package manager:"
        say "  Python 3.10+, GTK 4.12+ with its Python bindings (PyGObject), and 7-Zip."
    fi
    say ""
    if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        say "Python 3.10 or newer is still missing, and nothing works without it. Install it, then run install.sh again."
        exit 1
    fi
fi
if [ -n "$old_gtk" ]; then
    say "Note: this system has GTK $old_gtk, and the window needs 4.12 or newer."
    say "      The command line (samurai-mm) will still work. A newer release of your distribution brings a newer GTK."
fi

# ---- put the program in place

if [ "$mode" = "--in-place" ]; then
    app="$here"
else
    mkdir -p "$app"
    rm -rf "$app/samurai_mm"
    cp -r "$here/samurai_mm" "$app/"
    find "$app" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
    for f in install.sh LICENSE README.md CHANGELOG.md; do
        [ -f "$here/$f" ] && cp "$here/$f" "$app/"
    done
    chmod +x "$app/install.sh" 2>/dev/null || true
fi

mkdir -p "$bin" "$apps"
for name in samurai-mm samurai-mm-gui; do
    module=samurai_mm
    [ "$name" = samurai-mm-gui ] && module=samurai_mm.gui
    cat > "$bin/$name" <<WRAP
#!/bin/sh
# Starts Samurai Mod Manager from $app
PYTHONPATH="$app\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m $module "\$@"
WRAP
    chmod +x "$bin/$name"
done

cat > "$desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=Samurai Mod Manager
GenericName=Mod manager for Cyberpunk 2077
Comment=Install, switch and check Cyberpunk 2077 mods on Linux
Exec="$bin/samurai-mm-gui"
Icon=$app/samurai_mm/data/icon.png
Terminal=false
Categories=Game;
Keywords=cyberpunk;mods;cp2077;nexus;
StartupNotify=true
StartupWMClass=io.github.ptm4.SamuraiModManager
ENTRY
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" 2>/dev/null || true

say "Samurai Mod Manager is installed."
say "  Open it from your app menu, or run: samurai-mm-gui"
if [ "$mode" != "--in-place" ]; then
    say "  You can delete this folder now. To remove the manager later: sh \"$app/install.sh\" --remove"
fi
if [ "$need_gtk" = yes ] && ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null; then
    say "  The window will not open until GTK 4 for Python is installed (see above). The command line works already."
fi
if [ "$need_7z" = yes ] && ! command -v 7z >/dev/null 2>&1 && ! command -v 7zz >/dev/null 2>&1 && ! command -v 7za >/dev/null 2>&1; then
    say "  Mods cannot be unpacked until 7-Zip is installed (see above)."
fi
case ":$PATH:" in
    *":$bin:"*) ;;
    *) say "  Note: $bin is not on your PATH, so the samurai-mm commands need their full path. The app-menu entry works regardless." ;;
esac
