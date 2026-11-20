#!/bin/sh
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
rm -rf "dist/$name"
( cd dist && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256" )
echo "built dist/$name.tar.gz"
