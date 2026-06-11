# Installation Scripts

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Project root and `casmgr`

Run project scripts from the repository root (where `config.json` lives).
The `casmgr` launcher (`scripts/casmgr`, installed into `.venv/bin` on `pip install -e .`)
sets `cwd` to that root and uses project-relative paths (`config.json`, `./logs`, …).

```bash
cd /path/to/code_analysis
./scripts/casmgr status
# or after pip install -e .
casmgr --config config.json start
```

## Quick Start

### Installation

```bash
sudo ./scripts/install.sh
```

### Uninstallation

```bash
sudo ./scripts/uninstall.sh
```

## Files

- `install.sh` - Installation script that sets up code-analysis-server as a systemd service
- `uninstall.sh` - Uninstallation script that removes the service
- `systemd/code-analysis-server.service` - Systemd unit file

## What Gets Installed

- **System user**: `code-analysis` (dedicated user for the service)
- **Configuration**: `/etc/code-analysis-server/config.json`
- **Application**: `/usr/lib/code-analysis-server/`
- **Data**: `/var/lib/code-analysis-server/` (databases, indexes)
- **Logs**: `/var/log/code-analysis-server/`
- **Systemd service**: `code-analysis-server.service`

## After Installation

1. Review configuration: `sudo nano /etc/code-analysis-server/config.json`
2. Configure watch directories in the config file
3. Copy SSL certificates if using mTLS: `/etc/code-analysis-server/mtls_certificates/`
4. Start service: `sudo systemctl start code-analysis-server`
5. Enable auto-start: `sudo systemctl enable code-analysis-server`

## Service Management

```bash
# Start/Stop/Restart
sudo systemctl start code-analysis-server
sudo systemctl stop code-analysis-server
sudo systemctl restart code-analysis-server

# Status and logs
sudo systemctl status code-analysis-server
sudo journalctl -u code-analysis-server -f
```

For detailed documentation, see [docs/INSTALLATION.md](../docs/INSTALLATION.md).

## PostgreSQL: application role and empty database

Use this when the server already has PostgreSQL, but you need an **application login** and an **empty** database named like in `code_analysis.database.driver.config`. **Tables and indexes are not created here** — the running server applies DDL via `sync_schema` (`CodeDatabase` / PostgreSQL driver) on first connect.

### Scripts

| File | Role |
|------|------|
| `setup_postgres_code_analysis_db.sh` | Shell entry: calls the helper, then `psql` for `CREATE ROLE` (if missing), `ALTER ROLE` (password), `CREATE DATABASE` (if missing), grants on `public`. |
| `setup_postgres_code_analysis_credentials.py` | Resolves credentials using the same code paths as the app: `load_dotenv_near_config` from `code_analysis.core.env_loader` and `load_postgres_cli_config` from `code_analysis.core.postgres_cli_backup` (host, port, `dbname`, `user`, `password` / `password_env`). Prints `export …` lines for the shell script. |

### Prerequisites

- Client `psql` on `PATH`.
- Project venv (`.venv/bin/python`) or `python3` with the package installed so `code_analysis` imports work.
- `python-dotenv` if you use a `.env` file (same as for the server).

### Configuration and `.env`

1. Copy [`.env.example`](../.env.example) to `.env` at the repo root (or next to your config file — `load_dotenv_near_config` loads both patterns).
2. Set the **application** password (the name is taken from `password_env` in JSON, e.g. `CODE_ANALYSIS_POSTGRES_PASSWORD`).
3. Set a **superuser** password for `psql` (user `postgres` or whatever you export as `PGUSER` / `POSTGRES_SUPERUSER_USER`), e.g. `POSTGRES_SUPERUSER_PASSWORD` in `.env` (see comments in `.env.example`). If that is unset, the helper tries `POSTGRES_PASSWORD` or `PGPASSWORD` after loading `.env`.

The application user name and database name default from `code_analysis.database.driver.config` (`user`, `dbname`, …). You can override with environment variables before running the script (e.g. `CODE_ANALYSIS_POSTGRES_USER`, `PGHOST`, `CODE_ANALYSIS_DB_NAME`) — the same idea as for the driver.

### Usage

From the repository root:

```bash
./scripts/setup_postgres_code_analysis_db.sh
```

Config file resolution:

- First argument: path to `config.json` / `config-venv.json`, or  
- `--config /path/to/config.json`, or  
- `CONFIG_PATH` / `CASMGR_CONFIG`, or  
- otherwise `config-venv.json` if present, else `config.json` in the repo root.

Examples:

```bash
./scripts/setup_postgres_code_analysis_db.sh config-venv.json
CONFIG_PATH=/path/to/config.json ./scripts/setup_postgres_code_analysis_db.sh
```

If the database already exists but is owned by another role, you can transfer ownership (requires superuser):

```bash
FIX_EXISTING_DB_OWNER=yes ./scripts/setup_postgres_code_analysis_db.sh
```

### Behaviour notes

- Role and database names must match `[a-zA-Z0-9_]+` (validated in the shell script).
- `CREATE ROLE` uses plain `psql` variables (`:"app_role"`, `:'dbpass'`); a `DO $$ … $$` block is **not** used, because `psql` does not expand `:'var'` inside dollar-quoted bodies.
- After this script, start the server with the same config and `.env` — it will create schema objects on connect.

## Command Inventory Utility

**`command_inventory.py`** - Comprehensive command discovery and verification tool.

This utility provides multiple modes:
- **discover**: Find all commands from registry and update documentation
- **check**: Verify command files, imports, and registration
- **verify**: Check command availability via MCP interface
- **full**: Run all checks (default)

### Usage

```bash
# Run full inventory (discover + check + verify)
python scripts/command_inventory.py

# Only discover commands and update documentation
python scripts/command_inventory.py --mode discover

# Only check command registration
python scripts/command_inventory.py --mode check

# Only verify via MCP
python scripts/command_inventory.py --mode verify

# Custom output file
python scripts/command_inventory.py --mode discover --output custom_inventory.md

# Verbose output
python scripts/command_inventory.py --mode full --verbose
```

### Options

- `--mode {discover,check,verify,full}` - Operation mode (default: full)
- `--output OUTPUT` - Output file for discover mode (default: docs/COMMAND_INVENTORY.md)
- `--server-id SERVER_ID` - Server ID for verify mode (default: code-analysis-server)
- `-v, --verbose` - Verbose output

