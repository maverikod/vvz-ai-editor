#!/usr/bin/env bash
# Синхронизация контейнеров с /etc/hosts в сети Docker (по умолчанию smart-assistant):
#   - FQDN вида <имя>.<HOSTS_DOMAIN> → контейнер <имя>.
#   - Перед стартом: docker stop для ВСЕХ контейнеров, подключённых к этой сети
#     (кроме имён с 1c / 1csrv), по убыванию текущего IPv4 — чтобы освободить адреса
#     (в т.ч. у ollama/mac-server и т.д.).
#   - Затем docker start только для контейнеров из плана hosts — по возрастанию IP.
#   - Контейнеры на сети без записи в hosts останутся остановлены (поднимите вручную при необходимости).
#   - В конце сверка IP с hosts.
#
# Переменные: HOSTS_FILE  HOSTS_DOMAIN  DOCKER_NETWORK
#   DOCKER_STOP_TIMEOUT  SLEEP_BETWEEN_STARTS  DRY_RUN=1
#
set -euo pipefail

HOSTS_FILE="${HOSTS_FILE:-/etc/hosts}"
HOSTS_DOMAIN="${HOSTS_DOMAIN:-techsup.od.ua}"
DOCKER_NETWORK="${DOCKER_NETWORK:-smart-assistant}"
DOCKER_STOP_TIMEOUT="${DOCKER_STOP_TIMEOUT:-10}"
SLEEP_BETWEEN_STARTS="${SLEEP_BETWEEN_STARTS:-1}"
DRY_RUN="${DRY_RUN:-0}"

# Не local: иначе при set -u trap EXIT не видит переменную после выхода из main.
SYNC_PLAN_FILE=""

cleanup_sync_plan() {
  [[ -n "${SYNC_PLAN_FILE:-}" ]] && rm -f -- "$SYNC_PLAN_FILE"
}

should_skip_container() {
  local name="$1"
  local lc
  lc="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
  [[ "$lc" == *1csrv* || "$lc" == *1c-srv* ]] && return 0
  [[ "$lc" =~ 1c ]] && return 0
  return 1
}

parse_hosts_for_domain() {
  awk -v DOM="$HOSTS_DOMAIN" '
    /^#/ { next }
    NF < 2 { next }
    {
      ip = $1
      if (ip !~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) next
      suf = "." DOM
      lsuf = length(suf)
      for (i = 2; i <= NF; i++) {
        sub(/\r$/, "", $i)
        h = $i
        if (length(h) <= lsuf) continue
        if (substr(h, length(h) - lsuf + 1) != suf) continue
        n = split(h, parts, ".")
        if (n < 3) continue
        short = parts[1]
        if (short == "") continue
        print short "\t" ip "\t" h
      }
    }
  ' "$HOSTS_FILE"
}

container_ip_on_network() {
  local cname="$1"
  docker inspect -f "{{(index .NetworkSettings.Networks \"${DOCKER_NETWORK}\").IPAddress}}" "$cname" 2>/dev/null | tr -d '\r' || true
}

run_docker() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] docker %q\n' "$@"
    return 0
  fi
  docker "$@"
}

build_plan_sorted_by_ip() {
  local short ip fqdn
  while IFS=$'\t' read -r short ip fqdn; do
    [[ -z "$short" ]] && continue

    if should_skip_container "$short"; then
      echo "skip (1C policy): $short ($fqdn)" >&2
      continue
    fi

    if ! docker inspect "$short" >/dev/null 2>&1; then
      echo "warn: в $HOSTS_FILE есть $fqdn -> контейнер '$short' не найден" >&2
      continue
    fi

    printf '%s\t%s\t%s\n' "$ip" "$short" "$fqdn"
  done < <(parse_hosts_for_domain) | sort -t $'\t' -k1,1 -V
}

check_duplicate_ips() {
  local plan_file="$1"
  local dups
  dups="$(awk -F'\t' '{print $1}' "$plan_file" | sort | uniq -d)"
  if [[ -n "$dups" ]]; then
    echo "error: в $HOSTS_FILE один IPv4 назначен нескольким записям (исправьте hosts):" >&2
    echo "$dups" >&2
    exit 1
  fi
}

# Все имена контейнеров на сети (по одному в строке).
network_container_names() {
  local raw
  raw="$(docker network inspect "$DOCKER_NETWORK" --format '{{range .Containers}}{{.Name}}|{{end}}' 2>/dev/null || true)"
  raw="${raw%|}"
  [[ -z "$raw" ]] && return 0
  printf '%s\n' "${raw//|/$'\n'}"
}

stop_all_on_network_by_ip_desc() {
  local stop_list tf ip name
  tf="$(mktemp)"
  # shellcheck disable=SC2064
  trap 'rm -f -- "$tf"' RETURN

  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    if should_skip_container "$name"; then
      echo "skip stop (1C policy): $name" >&2
      continue
    fi
    ip="$(container_ip_on_network "$name")"
    if [[ -z "$ip" ]]; then
      echo "warn: $name — нет endpoint в $DOCKER_NETWORK, пробуем stop всё равно" >&2
      printf '0.0.0.0\t%s\n' "$name"
      continue
    fi
    printf '%s\t%s\n' "$ip" "$name"
  done < <(network_container_names) | sort -t $'\t' -k1,1 -rV >"$tf"

  echo "=== stop ВСЕ на сети $DOCKER_NETWORK (по убыванию IP) ==="
  while IFS=$'\t' read -r ip name; do
    [[ -z "$name" ]] && continue
    echo "stop: $name (был $ip)"
    if [[ "$DRY_RUN" == "1" ]]; then
      printf '[dry-run] docker stop -t %q %q\n' "$DOCKER_STOP_TIMEOUT" "$name"
    else
      docker stop -t "$DOCKER_STOP_TIMEOUT" "$name" 2>/dev/null || true
    fi
  done <"$tf"

  rm -f -- "$tf"
  trap - RETURN
}

main() {
  if [[ ! -r "$HOSTS_FILE" ]]; then
    echo "error: cannot read $HOSTS_FILE" >&2
    exit 1
  fi

  SYNC_PLAN_FILE="$(mktemp)"
  trap 'cleanup_sync_plan' EXIT

  build_plan_sorted_by_ip >"$SYNC_PLAN_FILE"

  if [[ ! -s "$SYNC_PLAN_FILE" ]]; then
    echo "нет контейнеров для синхронизации (по $HOSTS_DOMAIN и существующим именам)."
    exit 0
  fi

  check_duplicate_ips "$SYNC_PLAN_FILE"

  stop_all_on_network_by_ip_desc

  echo "=== start (по возрастанию IP из hosts, только план из hosts) ==="
  local ip short fqdn actual
  local start_failed=0
  while IFS=$'\t' read -r ip short fqdn; do
    [[ -z "$short" ]] && continue
    echo "start: $short -> $ip ($fqdn)"
    if run_docker start "$short"; then
      :
    else
      echo "error: не удалось start $short" >&2
      start_failed=1
    fi
    sleep "$SLEEP_BETWEEN_STARTS"
  done <"$SYNC_PLAN_FILE"

  echo "=== проверка IP в сети $DOCKER_NETWORK ==="
  while IFS=$'\t' read -r ip short fqdn; do
    [[ -z "$short" ]] && continue
    actual="$(container_ip_on_network "$short")"
    if [[ -z "$actual" ]]; then
      echo "warn: $short — нет IPv4 в сети $DOCKER_NETWORK"
      continue
    fi
    if [[ "$actual" == "$ip" ]]; then
      echo "ok: $short @ $ip ($fqdn)"
    else
      echo "warn: $short — в hosts $ip ($fqdn), в сети $DOCKER_NETWORK сейчас $actual (нужен ipv4_address в compose)"
    fi
  done <"$SYNC_PLAN_FILE"

  if [[ "$start_failed" -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
