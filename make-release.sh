#!/bin/sh
# Builds dist/samurai-mod-manager-<version>.tar.gz after running the tests. Nothing is uploaded anywhere.
set -eu
cd "$(dirname "$0")"
version=$(python3 -c 'import samurai_mm; print(samurai_mm.__version__)')
name="samurai-mod-manager-$version"
[ -f LICENSE ] || echo "warning: there is no LICENSE file yet. Do not publish this archive until one is added."
python3 -m unittest discover -s tests
rm -rf "dist/$name"
mkdir -p "dist/$name"
cp -r samurai_mm tests docs install.sh README.md CHANGELOG.md pyproject.toml "dist/$name/"
[ -f LICENSE ] && cp LICENSE "dist/$name/"
find "dist/$name" -name __pycache__ -type d -prune -exec rm -rf {} +
tar -C dist -czf "dist/$name.tar.gz" "$name"
rm -rf "dist/$name"
( cd dist && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256" )
echo "built dist/$name.tar.gz"
