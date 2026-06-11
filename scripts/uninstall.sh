#!/bin/bash
#
# Uninstallation script for ai-editor-server systemd service
# Ubuntu/Debian compatible
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="ai-editor-server"
SERVICE_USER="ai-editor"
INSTALL_DIR="/usr/lib/ai-editor-server"
CONFIG_DIR="/etc/ai-editor-server"
DATA_DIR="/var/lib/ai-editor-server"
LOG_DIR="/var/log/ai-editor-server"
RUN_DIR="/var/run/ai-editor-server"
SYSTEMD_DIR="/etc/systemd/system"

# Functions
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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
    fi
}

stop_service() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        info "Stopping $SERVICE_NAME service..."
        systemctl stop "$SERVICE_NAME" || warn "Failed to stop service"
    else
        info "Service $SERVICE_NAME is not running"
    fi
}

disable_service() {
    if systemctl is-enabled --quiet "$SERVICE_NAME"; then
        info "Disabling $SERVICE_NAME service..."
        systemctl disable "$SERVICE_NAME" || warn "Failed to disable service"
    fi
}

remove_systemd_service() {
    if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME.service" ]]; then
        info "Removing systemd service file..."
        rm -f "$SYSTEMD_DIR/$SERVICE_NAME.service"
        systemctl daemon-reload
        systemctl reset-failed
    fi
}

remove_directories() {
    local remove_data=false
    local remove_logs=false
    
    read -p "Remove data directory ($DATA_DIR)? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        remove_data=true
    fi
    
    read -p "Remove log directory ($LOG_DIR)? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        remove_logs=true
    fi
    
    # Remove installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
    fi
    
    # Remove configuration directory
    read -p "Remove configuration directory ($CONFIG_DIR)? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ -d "$CONFIG_DIR" ]]; then
            info "Removing configuration directory..."
            rm -rf "$CONFIG_DIR"
        fi
    else
        warn "Configuration directory kept at $CONFIG_DIR"
    fi
    
    # Remove data directory
    if [[ "$remove_data" == true && -d "$DATA_DIR" ]]; then
        info "Removing data directory..."
        rm -rf "$DATA_DIR"
    else
        warn "Data directory kept at $DATA_DIR"
    fi
    
    # Remove log directory
    if [[ "$remove_logs" == true && -d "$LOG_DIR" ]]; then
        info "Removing log directory..."
        rm -rf "$LOG_DIR"
    else
        warn "Log directory kept at $LOG_DIR"
    fi
    
    # Remove runtime directory
    if [[ -d "$RUN_DIR" ]]; then
        info "Removing runtime directory..."
        rm -rf "$RUN_DIR"
    fi
}

remove_user() {
    read -p "Remove system user $SERVICE_USER? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if id "$SERVICE_USER" &>/dev/null; then
            info "Removing system user $SERVICE_USER..."
            userdel "$SERVICE_USER" || warn "Failed to remove user (may be in use)"
        fi
    else
        warn "User $SERVICE_USER kept"
    fi
}

main() {
    info "Starting uninstallation of $SERVICE_NAME..."
    
    check_root
    
    stop_service
    disable_service
    remove_systemd_service
    remove_directories
    remove_user
    
    info ""
    info "Uninstallation completed!"
    info ""
}

main "$@"

