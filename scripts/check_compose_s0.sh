#!/usr/bin/env bash
# S0 Compose 结构与就绪检查（AT-22 S0 子集，R10）：在 `docker compose up -d` 之后运行
set -euo pipefail

compose=(docker compose -f deploy/compose.yaml)
services=(postgres redis api-admin worker control gateway)
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

for svc in "${services[@]}"; do
  cid="$("${compose[@]}" ps -q "$svc")"
  [[ -n "$cid" ]] || { echo "服务未运行: $svc" >&2; exit 1; }
  docker inspect "$cid" > "$workdir/$svc.json"
done

"$(dirname "$0")/probe_ready.sh" > "$workdir/ready.json"

# Windows 上的 python3 可能是商店占位程序，先确认可执行
py=python3
"$py" -c "" 2>/dev/null || py=python
"$py" scripts/check_compose_s0.py "$workdir" "${services[@]}"
