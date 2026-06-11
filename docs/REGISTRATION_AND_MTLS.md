# Registration and mTLS — Proxy Setup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Rule

The **MCP Proxy works with mTLS**. The server must use the **config as-is**: bind to the address the proxy expects (e.g. `172.28.0.1`) and keep **mTLS enabled**. Do **not** override host/port or disable mTLS when running with the proxy.

## Start server for proxy

```bash
python -m code_analysis.main --config config.json --daemon
```

- **Do not** use `--host 127.0.0.1` or `--port` unless you intentionally change the environment (e.g. proxy on the same host without Docker).
- The server will:
  - Bind to `server.host` and `server.port` from config (e.g. 172.28.0.1:15000).
  - Use mTLS from `server.ssl` (cert, key, ca).
  - Auto-register with the proxy at `registration.register_url` (e.g. https://172.28.0.2:3004/register) using `registration.ssl` and `registration.instance_uuid`.

## config.json

- `server.host`: e.g. `172.28.0.1` (address the proxy expects).
- `server.ssl`: cert, key, ca for the server.
- `registration.enabled`: true.
- `registration.register_url`: proxy register endpoint (e.g. https://172.28.0.2:3004/register).
- `registration.instance_uuid`: UUID4 (e.g. 550e8400-e29b-41d4-a716-446655440000).
- `registration.ssl`: client cert, key, ca for registering with the proxy.

If the server was previously started with `--host 127.0.0.1`, restart it **without** that override so the proxy can connect and registration can succeed.
