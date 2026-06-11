#!/bin/bash
# Build ai-editor-docker Debian package (image tag must match package version).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEBIAN_SRC="$SCRIPT_DIR/debian"
PKG_WORK="$SCRIPT_DIR/dist/deb-build"
OUTPUT_DIR="$SCRIPT_DIR/dist"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"

VERSION="${1:-}"
DOCKERHUB_REPO="$(dockerhub_repo_default)"
ARCH="${AI_EDITOR_DEB_ARCH:-amd64}"

if [ -z "$VERSION" ]; then
  VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
if not m:
    raise SystemExit("Cannot read version from pyproject.toml")
print(m.group(1))
PY
)"
fi

PKG_NAME="ai-editor-docker"
DEB_FILE="${OUTPUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "[INFO] Building Debian package ${PKG_NAME} ${VERSION} (image ${DOCKERHUB_REPO}:${VERSION})"

rm -rf "$PKG_WORK"
mkdir -p "$PKG_WORK/DEBIAN" "$OUTPUT_DIR"
cp -a "$DEBIAN_SRC/DEBIAN/"* "$PKG_WORK/DEBIAN/"
cp -a "$DEBIAN_SRC/etc" "$PKG_WORK/"
cp -a "$DEBIAN_SRC/lib" "$PKG_WORK/"

mkdir -p "$PKG_WORK/usr/lib/ai-editor" "$PKG_WORK/usr/bin" "$PKG_WORK/usr/share/ai-editor" \
  "$PKG_WORK/usr/share/doc/ai-editor-docker" "$PKG_WORK/etc/ai-editor/mtls_certificates"

install -m 755 "$SCRIPT_DIR/pkg/docker-run.sh" "$PKG_WORK/usr/lib/ai-editor/docker-run.sh"
install -m 755 "$SCRIPT_DIR/pkg/ai-editor-info" "$PKG_WORK/usr/bin/ai-editor-info"
install -m 755 "$SCRIPT_DIR/pkg/ai-editor-docker" "$PKG_WORK/usr/bin/ai-editor-docker"
install -m 644 "$SCRIPT_DIR/pkg/image-spec.in" "$PKG_WORK/usr/lib/ai-editor/image-spec"
sed -i "s|@DOCKERHUB_REPO@|${DOCKERHUB_REPO}|g; s|@IMAGE_TAG@|${VERSION}|g" \
  "$PKG_WORK/usr/lib/ai-editor/image-spec"

install -m 644 "$PROJECT_ROOT/config/ai_editor_container.json" \
  "$PKG_WORK/usr/share/ai-editor/ai_editor_container.json"
install -m 644 "$PKG_WORK/usr/share/ai-editor/ai_editor_container.json" \
  "$PKG_WORK/etc/ai-editor/ai_editor_container.json"
install -m 644 "$SCRIPT_DIR/README.md" "$PKG_WORK/usr/share/doc/ai-editor-docker/README.md"

MAN_SRC="$DEBIAN_SRC/man"
if [ -d "$MAN_SRC" ]; then
  mkdir -p "$PKG_WORK/usr/share/man/man1"
  for man_page in ai-editor-docker.1 ai-editor-info.1; do
    if [ -f "$MAN_SRC/$man_page" ]; then
      sed "s|@VERSION@|${VERSION}|g" "$MAN_SRC/$man_page" | gzip -9 -n \
        >"$PKG_WORK/usr/share/man/man1/${man_page}.gz"
    fi
  done
fi

sed "s|@VERSION@|${VERSION}|g" "$PKG_WORK/DEBIAN/control" > "$PKG_WORK/DEBIAN/control.tmp"
mv "$PKG_WORK/DEBIAN/control.tmp" "$PKG_WORK/DEBIAN/control"

chmod 755 "$PKG_WORK/DEBIAN/postinst" "$PKG_WORK/DEBIAN/prerm" "$PKG_WORK/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$PKG_WORK" "$DEB_FILE"

echo "[SUCCESS] Debian package: $DEB_FILE"
ls -lh "$DEB_FILE"
