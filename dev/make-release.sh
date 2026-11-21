#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 ptm4 and Samurai Mod Manager contributors
# Builds dist/samurai-mod-manager-<version>.tar.gz after running the tests. Nothing is uploaded anywhere.
# The archive holds what a user needs: the program, the installer, README, LICENSE, CHANGELOG and screenshots.
set -eu
cd "$(dirname "$0")/.."
version=$(python3 -c 'import samurai_mm; print(samurai_mm.__version__)')
name="samurai-mod-manager-$version"
python3 -m unittest discover -s dev/tests
rm -rf "dist/$name"
mkdir -p "dist/$name"
cp -r samurai_mm docs install.sh README.md CHANGELOG.md LICENSE "dist/$name/"
chmod +x "dist/$name/install.sh"
find "dist/$name" -name __pycache__ -type d -prune -exec rm -rf {} +
tar -C dist -czf "dist/$name.tar.gz" "$name"
# The same content as a zip, for sites that only take zip, rar or 7z (Nexus Mods).
rm -f "dist/$name.zip"
python3 - "dist" "$name" <<'PY'
import os, sys, zipfile
base, name = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(os.path.join(base, name + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for folder, _, files in sorted(os.walk(os.path.join(base, name))):
        for f in sorted(files):
            full = os.path.join(folder, f)
            info = zipfile.ZipInfo.from_file(full, os.path.relpath(full, base))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if f.endswith(".sh") else 0o644          # keep install.sh runnable after unzip
            info.external_attr = (0o100000 | mode) << 16
            with open(full, "rb") as fh:
                z.writestr(info, fh.read())
PY
rm -rf "dist/$name"
( cd dist && sha256sum "$name.tar.gz" "$name.zip" > "$name.sha256" )
echo "built dist/$name.tar.gz and dist/$name.zip"
