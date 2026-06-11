# Building and Installing Debian Package

## Quick Start

### Build Package

```bash
./scripts/build_deb.sh
```

### Install Package

```bash
sudo dpkg -i ../code-analysis-server_*.deb
sudo apt-get install -f  # Fix dependencies if needed
```

## Prerequisites

```bash
sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools
```

## Package Structure

- **debian/control** - Package metadata
- **debian/rules** - Build rules
- **debian/preinst** - Pre-installation script
- **debian/postinst** - Post-installation script (creates user, directories, venv)
- **debian/prerm** - Pre-removal script (stops service)
- **debian/postrm** - Post-removal script
- **debian/changelog** - Version history
- **debian/copyright** - License information

## What Gets Installed

- Application: `/usr/lib/code-analysis-server/`
- Config: `/etc/code-analysis-server/`
- Data: `/var/lib/code-analysis-server/`
- Logs: `/var/log/code-analysis-server/`
- Service: `code-analysis-server.service`

## After Installation

1. Configure: `sudo nano /etc/code-analysis-server/config.json`
2. Start: `sudo systemctl start code-analysis-server`
3. Enable: `sudo systemctl enable code-analysis-server`

See `docs/DEB_PACKAGE.md` for detailed documentation.
