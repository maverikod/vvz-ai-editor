# Service packaging and deployment standard

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

This is the house standard for packaging and deploying an MCP service. It is written
from what is actually implemented and verified in `ai-editor`; that project is the
reference implementation. Every other project follows the same shape, so an operator
who has installed one has installed them all.

Substitute the service name for `<svc>` throughout (`ai-editor`, `doc-store`, ...).

---

## 1. The three artefacts

A service ships as three things and nothing else:

| Artefact | What it is | Built by |
|---|---|---|
| Docker image | the runtime: application plus every dependency | `docker/build.sh` |
| Debian package `<svc>-docker` | the host-side installation: user, directories, permissions, settings, systemd unit, container lifecycle | `docker/build-deb.sh` |
| Settings file `/etc/default/<svc>` | everything an operator may change | shipped by the package as a dpkg **conffile** |

The image contains no host configuration. The package contains no secrets. The settings
file is the only place a human edits, and even that is normally reached through the
argument surface (§5) rather than a text editor.

## 2. The package owns identity and access

The package — not a human, not a README step — creates the service's own user and group
and sets ownership and permissions. `postinst` must be idempotent: it runs on every
install and upgrade and always lands on the same state.

```
ensure_user()   -> addgroup --system <svc>; adduser --system --ingroup <svc> \
                     --home /var/lib/<svc> --no-create-home --disabled-login <svc>
ensure_dirs()   -> the table below
ensure_mtls_permissions() -> the access rule for the key material
```

| Path | Owner | Mode | Note |
|---|---|---|---|
| `/etc/<svc>` | `root:root` | 755 | config directory |
| `/etc/<svc>/<svc>_container.json` | `root:root` | 644 | resolved config, a conffile |
| `/etc/<svc>/mtls_certificates` | `root:<svc>` | 750 | key material root |
| ...its directories | `root:<svc>` | 750 | |
| ...its files | `root:<svc>` | 640 | certificates AND keys |
| `/var/log/<svc>` | `<svc>:<svc>` | 755 | |
| `/var/<svc>` and its data subdirs | `<svc>:<svc>` | 755 | |
| `/var/lib/<svc>` | `<svc>:<svc>` | 755 | package state |

Rules that follow from that table and are not negotiable:

- **Key material is never group-writable and never world-readable.** The service's own
  group reads it because that is who the container runs as; nobody else does.
- **The package never ships keys.** Certificates are copied to the host once, out of
  band, before a deploy. The package owns the *access rule* and re-applies it on every
  install, whatever mode the copy left behind.
- **The container runs as the service user**, not as root. Check with
  `docker inspect <svc> --format '{{.Config.User}}'` — it must be the service uid:gid.

## 3. Configuration is templated, never hand-edited

The application config is a template with `${SVC_*}` placeholders. Placeholders are
resolved from `/etc/default/<svc>` at container start; a preflight step refuses to start
the container while any placeholder is unresolved, naming the missing variable.

**A fresh install must end up fully configured and running.** If an install can land in
a state where a human has to open an editor before the service will start, the package
is incomplete. Every value the template needs has a working default in
`/etc/default/<svc>`.

Nothing that an operator may reasonably want to change is hard-coded in the template.
At minimum these are placeholders, never literals:

- advertised host, port, protocol
- registration host and port
- every upstream service host and port
- **every certificate path** (server cert/key/ca and client cert/key/ca), and the mTLS
  directory
- the server id and any host suffix in it
- the docker networks

## 4. The settings file

`/etc/default/<svc>` is a shell fragment sourced with `set -a`, so every assignment is
exported to the container-start path. It is a dpkg conffile: an operator's edits survive
upgrades and dpkg prompts on conflict.

It carries: the service user and group; the port; the config, log, data and mTLS
directories; the container name; the docker networks; the DNS alias; the advertised
host; every upstream host/port; and the registration endpoint. Commented-out entries
document the optional knobs rather than hiding them.

## 5. The argument surface

Settings are changed through arguments, not by editing files by hand:

```
<svc>ctl set --port 15000 --registration-host mcp-proxy --ca-host casmgr --ca-port 15010
<svc>ctl set --client-cert /etc/<svc>/mtls_certificates/.../client/<svc>.crt
<svc>ctl show
```

Requirements:

- It writes `/etc/default/<svc>`, then re-resolves the config and recreates the
  container, so the change is live rather than merely recorded.
- **An unknown key or a malformed value is rejected loudly and nothing is written.**
  A partially applied settings change is worse than a refused one.
- `show` prints the effective values and where each came from (settings file, default).
- Every value listed in §3 is reachable through it.

## 6. Networking: Docker DNS, never IP addresses

Services find each other by **docker network name**. An IP address in a config is a
defect: containers get new addresses on every recreate.

- The package ensures the networks exist (`docker network inspect || docker network
  create`) before creating the container — it does not assume an operator made them.
- The primary network in this installation is **`smart-assistant`**; a service may have
  a secondary network of its own.
- The container publishes itself under a stable alias (`--network-alias`), which is the
  name its peers use: `ai-editor-server`, `casmgr`, `mcp-proxy`.
- Verify by resolution from inside the container, not by reading the config.

## 7. Deployment

```
/usr/lib/<svc>/image-spec        # DOCKERHUB_REPO and IMAGE_TAG, baked at package build
/usr/lib/<svc>/docker-run.sh     # start | stop | restart | recreate
/usr/lib/systemd/system/<svc>-docker.service
```

`docker-run.sh start` recreates the container when the image reference changed, so a
deploy is: point `image-spec` at the new tag, `systemctl restart <svc>-docker`.

The image reaches the host either by registry pull or, when there is no registry, by
`docker save | ssh <host> 'docker load'`. Both are ordinary operations.

**Rollback is part of a deploy, not an afterthought:** keep the previous `image-spec`
and the previous image on the host, so reverting is one edit and one restart.

## 8. Verification: a deploy is not done until it is proven

Claims about a deployment are worth nothing without a call that returned. After every
deploy, prove — with real output, not reasoning:

1. `health` over the real transport reports the expected version and status.
2. The application package is genuinely inside the image:
   `docker run --rm --entrypoint python <image> -c "import <pkg>; print(<pkg>.__path__)"`.
   This is not paranoia — in `ai-editor` the engine was absent from the image for the
   whole of its development because the Dockerfile copied only some directories, and
   `pyproject.toml` being correct hid it.
3. Ownership and permissions match §2: `stat -c "%U:%G %a %n"`.
4. The container is on the expected networks and resolves its peers by name.
5. The live pipeline (§9) passes against the deployed instance.

## 9. The live pipeline

Every service has a pipeline of checks, one check per file, discovered automatically —
adding a file adds a check, with no registry edit:

```
pipeline/registry.py      # register(name, description, func), CheckResult/CheckStatus
pipeline/cli.py           # walks pipeline/checks/, one subcommand per check
pipeline/checks/*.py      # one check per file
pipeline/live/client.py   # transport + schema-driven coverage for live checks
```

Live checks run against the **deployed** service, from wherever is convenient, over its
real transport. Rules learned the hard way:

- **Coverage is driven by the server's own declared schema.** `help(cmdname=...)` returns
  the parameter table (type, required, default, enum) and the map of stable error codes.
  A check reports what is DECLARED BUT UNTESTED, so a parameter or error case added later
  cannot go silently uncovered.
- **Assert real behaviour, not the documentation** — and report every divergence between
  them. A documented error code the server can never emit is a defect worth finding.
- **There is no "skipped" outcome for an unreachable service.** The deployed service is
  part of the project: if it does not answer, bring it up. Unreachable is RED.
- Checks are registered unconditionally. A check that hides itself when it cannot run is
  indistinguishable from a check that was deleted.
- Destructive checks use a dedicated sandbox project, never real data, and clean up
  everything they create even when they fail.

## 10. Checklist for a new service

- [ ] `docker/Dockerfile` copies **every** source directory the package declares
- [ ] `docker/build.sh` builds and tags the image from the single version source
- [ ] `docker/build-deb.sh` builds `<svc>-docker`
- [ ] `postinst` creates the user and group, the directories, and applies the permission
      table and the mTLS access rule — idempotently
- [ ] `/etc/default/<svc>` shipped as a conffile with a working default for every
      template placeholder
- [ ] the config template hard-codes nothing from §3
- [ ] an argument surface sets every one of those values, rejects bad input, and applies
      the change live
- [ ] networks ensured and joined; peers addressed by DNS name
- [ ] `image-spec` + `docker-run.sh` + systemd unit; rollback path kept
- [ ] the pipeline has a live check per command, coverage measured against the declared
      schema
- [ ] the deploy is proven by §8, with the output pasted into the delivery report
