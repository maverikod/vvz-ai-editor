#!/bin/bash
#
# Installation script for ai-editor-server as systemd service
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
SERVICE_GROUP="ai-editor"
INSTALL_DIR="/usr/lib/ai-editor-server"
CONFIG_DIR="/etc/ai-editor-server"
DATA_DIR="/var/lib/ai-editor-server"
LOG_DIR="/var/log/ai-editor-server"
RUN_DIR="/var/run/ai-editor-server"
SYSTEMD_DIR="/etc/systemd/system"
VENV_DIR="${INSTALL_DIR}/.venv"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

check_system() {
    if [[ ! -f /etc/os-release ]]; then
        error "Cannot detect operating system"
    fi
    
    source /etc/os-release
    if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
        warn "This script is designed for Ubuntu/Debian. Other distributions may work but are not tested."
    fi
    
    info "Detected OS: $PRETTY_NAME"
}

create_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        info "User $SERVICE_USER already exists"
    else
        info "Creating system user $SERVICE_USER"
        useradd --system --no-create-home --shell /bin/false --group "$SERVICE_USER" "$SERVICE_USER" || \
        useradd --system --no-create-home --shell /bin/false "$SERVICE_USER" || \
        error "Failed to create user $SERVICE_USER"
    fi
}

create_directories() {
    info "Creating directories..."
    
    # Installation directory
    mkdir -p "$INSTALL_DIR"
    chown root:root "$INSTALL_DIR"
    chmod 755 "$INSTALL_DIR"
    
    # Configuration directory
    mkdir -p "$CONFIG_DIR"
    chown root:root "$CONFIG_DIR"
    chmod 755 "$CONFIG_DIR"
    
    # Data directory (databases, indexes)
    mkdir -p "$DATA_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
    chmod 750 "$DATA_DIR"
    
    # Log directory
    mkdir -p "$LOG_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    chmod 750 "$LOG_DIR"
    
    # Runtime directory (PID files, sockets)
    mkdir -p "$RUN_DIR"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$RUN_DIR"
    chmod 750 "$RUN_DIR"
}

install_package() {
    info "Installing package files to $INSTALL_DIR..."
    
    # Copy package files
    rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
          --exclude='*.pyc' --exclude='.pytest_cache' --exclude='htmlcov' \
          --exclude='test_data' --exclude='logs' --exclude='data' \
          --exclude='*.db' --exclude='*.db-*' \
          "$PROJECT_ROOT/" "$INSTALL_DIR/" || error "Failed to copy package files"
    
    chown -R root:root "$INSTALL_DIR"
    find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
    find "$INSTALL_DIR" -type f -exec chmod 644 {} \;
    find "$INSTALL_DIR" -name "*.sh" -exec chmod 755 {} \;
}

create_venv() {
    info "Creating Python virtual environment..."
    
    if [[ -d "$VENV_DIR" ]]; then
        warn "Virtual environment already exists, removing..."
        rm -rf "$VENV_DIR"
    fi
    
    # Create venv
    python3 -m venv "$VENV_DIR" || error "Failed to create virtual environment"
    
    # Upgrade pip
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel || error "Failed to upgrade pip"
    
    # Install package
    info "Installing ai-editor-tool package..."
    "$VENV_DIR/bin/pip" install "$INSTALL_DIR" || error "Failed to install package"
    
    # Install additional dependencies from requirements.txt if exists
    if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
        info "Installing additional dependencies..."
        "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || error "Failed to install dependencies"
    fi
    
    # Fix permissions
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$VENV_DIR"
}

install_config() {
    info "Installing configuration file..."
    
    if [[ -f "$CONFIG_DIR/config.json" ]]; then
        warn "Configuration file already exists at $CONFIG_DIR/config.json"
        warn "Backing up existing config to $CONFIG_DIR/config.json.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$CONFIG_DIR/config.json" "$CONFIG_DIR/config.json.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Create config from template if exists, otherwise from example
    if [[ -f "$INSTALL_DIR/config.example.json" ]]; then
        cp "$INSTALL_DIR/config.example.json" "$CONFIG_DIR/config.json"
    elif [[ -f "$INSTALL_DIR/config.json" ]]; then
        cp "$INSTALL_DIR/config.json" "$CONFIG_DIR/config.json"
    else
        error "No configuration template found"
    fi
    
    # Update paths in config for system installation
    python3 <<EOF
import json
import sys
import os

config_path = "$CONFIG_DIR/config.json"
with open(config_path, 'r') as f:
    config = json.load(f)

# Update database path (must be absolute)
if 'ai_editor' in config:
    config['ai_editor']['db_path'] = "$DATA_DIR/ai_editor.db"
    if 'faiss_index_path' in config['ai_editor']:
        config['ai_editor']['faiss_index_path'] = "$DATA_DIR/faiss_index.bin"
    
    # Update log paths (must be absolute)
    if 'log' in config['ai_editor']:
        config['ai_editor']['log'] = "$LOG_DIR/ai_editor.log"
    
    # Update server log_dir (must be absolute)
    if 'server' in config:
        config['server']['log_dir'] = "$LOG_DIR"
    
    # Update worker log paths (must be absolute)
    if 'worker' in config['ai_editor']:
        if 'log_path' in config['ai_editor']['worker']:
            config['ai_editor']['worker']['log_path'] = "$LOG_DIR/vectorization_worker.log"
    
    if 'file_watcher' in config['ai_editor']:
        if 'log_path' in config['ai_editor']['file_watcher']:
            config['ai_editor']['file_watcher']['log_path'] = "$LOG_DIR/file_watcher.log"
        if 'version_dir' in config['ai_editor']['file_watcher']:
            config['ai_editor']['file_watcher']['version_dir'] = "$DATA_DIR/versions"

# Update SSL certificate paths if they exist (make absolute)
# Note: User should copy certificates manually or update paths
def make_absolute_path(path, base_dir):
    """Make path absolute if it's relative."""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    # If relative, make it relative to CONFIG_DIR
    return os.path.join(base_dir, path)

if 'server' in config and 'ssl' in config.get('server', {}):
    ssl = config['server']['ssl']
    for key in ['cert', 'key', 'ca', 'crl']:
        if key in ssl and ssl[key]:
            ssl[key] = make_absolute_path(ssl[key], "$CONFIG_DIR")

# Update client SSL paths
if 'client' in config and 'ssl' in config.get('client', {}):
    ssl = config['client']['ssl']
    for key in ['cert', 'key', 'ca', 'crl']:
        if key in ssl and ssl[key]:
            ssl[key] = make_absolute_path(ssl[key], "$CONFIG_DIR")

# Update registration SSL paths
if 'registration' in config and 'ssl' in config.get('registration', {}):
    ssl = config['registration']['ssl']
    for key in ['cert', 'key', 'ca', 'crl']:
        if key in ssl and ssl[key]:
            ssl[key] = make_absolute_path(ssl[key], "$CONFIG_DIR")

# Update server_validation SSL paths
if 'server_validation' in config and 'ssl' in config.get('server_validation', {}):
    ssl = config['server_validation']['ssl']
    for key in ['cert', 'key', 'ca', 'crl']:
        if key in ssl and ssl[key]:
            ssl[key] = make_absolute_path(ssl[key], "$CONFIG_DIR")

# Update chunker and embedding certificate paths
if 'ai_editor' in config:
    for service in ['chunker', 'embedding']:
        if service in config['ai_editor']:
            svc = config['ai_editor'][service]
            for key in ['cert_file', 'key_file', 'ca_cert_file', 'crl_file']:
                if key in svc and svc[key]:
                    svc[key] = make_absolute_path(svc[key], "$CONFIG_DIR")

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print("Configuration updated successfully")
EOF
    
    chown root:root "$CONFIG_DIR/config.json"
    chmod 644 "$CONFIG_DIR/config.json"
    
    info "Configuration installed to $CONFIG_DIR/config.json"
    warn "Please review and update the configuration file before starting the service"
}

install_systemd_service() {
    info "Installing systemd service..."
    
    if [[ -f "$PROJECT_ROOT/scripts/systemd/ai-editor-server.service" ]]; then
        cp "$PROJECT_ROOT/scripts/systemd/ai-editor-server.service" "$SYSTEMD_DIR/$SERVICE_NAME.service"
    else
        error "Systemd service file not found"
    fi
    
    chown root:root "$SYSTEMD_DIR/$SERVICE_NAME.service"
    chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"
    
    # Reload systemd
    systemctl daemon-reload
    
    info "Systemd service installed"
}

main() {
    info "Starting installation of $SERVICE_NAME..."
    
    check_root
    check_system
    create_user
    create_directories
    install_package
    create_venv
    install_config
    install_systemd_service
    
    info ""
    info "Installation completed successfully!"
    info ""
    info "Next steps:"
    info "1. Review and update configuration: $CONFIG_DIR/config.json"
    info "2. Copy SSL certificates to $CONFIG_DIR/mtls_certificates/ if needed"
    info "3. Configure watch directories in $CONFIG_DIR/config.json"
    info "4. Start the service: systemctl start $SERVICE_NAME"
    info "5. Enable auto-start: systemctl enable $SERVICE_NAME"
    info "6. Check status: systemctl status $SERVICE_NAME"
    info ""
}

main "$@"

