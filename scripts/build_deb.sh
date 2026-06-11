#!/bin/bash
#
# Build script for creating Debian package
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

error() {
    echo -e "${RED}ERROR:${NC} $1" >&2
    exit 1
}

info() {
    echo -e "${GREEN}INFO:${NC} $1"
}

warn() {
    echo -e "${YELLOW}WARN:${NC} $1"
}

# Check if we're in the project root
if [[ ! -f "debian/control" ]]; then
    error "debian/control not found. Please run this script from the project root."
fi

# Check for required tools
for cmd in dpkg-buildpackage debhelper; do
    if ! command -v "$cmd" &>/dev/null; then
        error "$cmd is not installed. Install with: sudo apt-get install devscripts debhelper"
    fi
done

# Clean previous builds
info "Cleaning previous builds..."
rm -rf debian/ai-editor-server
rm -rf debian/files
rm -rf ../ai-editor-server_*.deb
rm -rf ../ai-editor-server_*.dsc
rm -rf ../ai-editor-server_*.tar.gz
rm -rf ../ai-editor-server_*.buildinfo
rm -rf ../ai-editor-server_*.changes

# Build package
info "Building Debian package..."
dpkg-buildpackage -us -uc -b

# Check result
if [[ -f ../ai-editor-server_*.deb ]]; then
    DEB_FILE=$(ls -t ../ai-editor-server_*.deb | head -1)
    info "Package built successfully: $DEB_FILE"
    info ""
    info "To install:"
    info "  sudo dpkg -i $DEB_FILE"
    info ""
    info "To install with dependencies:"
    info "  sudo apt-get install -f"
    info "  sudo dpkg -i $DEB_FILE"
else
    error "Package build failed. Check output above for errors."
fi

