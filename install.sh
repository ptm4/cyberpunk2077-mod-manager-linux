#!/bin/sh
# Per-user install: two commands in ~/.local/bin and an app-menu entry.
# It installs no packages and needs no root. Run it again after moving this folder.
# Undo with: ./install.sh --remove
set -eu

here=$(cd "$(dirname "$0")" && pwd)
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
desktop="$apps/io.github.ptm4.SamuraiModManager.desktop"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$bin/samurai-mm" "$bin/samurai-mm-gui" "$desktop"
    echo "removed the commands and the app-menu entry (your mods and settings are untouched)"
    exit 0
fi

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "needs Python 3.10 or newer"; exit 1; }
if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null; then
    echo "note: GTK4 for Python is missing, so only the command line will work."
    echo "      Arch/CachyOS: sudo pacman -S gtk4 python-gobject"
fi
command -v 7z >/dev/null 2>&1 || command -v 7zz >/dev/null 2>&1 || echo "note: 7z is missing; install it to unpack downloads (Arch/CachyOS: sudo pacman -S 7zip)"

mkdir -p "$bin" "$apps"
for name in samurai-mm samurai-mm-gui; do
    module=samurai_mm
    [ "$name" = samurai-mm-gui ] && module=samurai_mm.gui
    cat > "$bin/$name" <<WRAP
#!/bin/sh
# Starts the Cyberpunk 2077 mod manager from $here
PYTHONPATH="$here\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m $module "\$@"
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
Icon=$here/samurai_mm/data/icon.png
Terminal=false
Categories=Game;
Keywords=cyberpunk;mods;cp2077;nexus;
StartupNotify=true
StartupWMClass=io.github.ptm4.SamuraiModManager
ENTRY
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" 2>/dev/null || true

echo "installed: samurai-mm, samurai-mm-gui and the app-menu entry \"Samurai Mod Manager\""
case ":$PATH:" in *":$bin:"*) ;; *) echo "note: $bin is not on your PATH; the app-menu entry works regardless" ;; esac
