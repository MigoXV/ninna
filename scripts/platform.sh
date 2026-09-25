#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export NINNA_ROOT="$PWD"
if [[ -z "${NINNA_HOST_ROOT:-}" ]]; then
  NINNA_HOST_ROOT="$(python3 scripts/resolve-paths.py | python3 -c 'import json,sys; print(json.load(sys.stdin)["host_root"])')"
  export NINNA_HOST_ROOT
fi
case "${1:-up}" in
  up)
    if ! docker image inspect ninna/pytorch-runtime:v1 >/dev/null 2>&1; then
      docker build -t ninna/pytorch-runtime:v1 runtimes/pytorch
    fi
    if ! docker image inspect ninna/pytorch-runtime:v2 >/dev/null 2>&1; then
      docker build -t ninna/pytorch-runtime:v2 runtimes/pytorch-hf
    fi
    docker build -t ninna/platform:0.1.0 .
    docker compose up -d --no-build --wait platform
    docker compose exec -T platform poetry run ninna initialize
    ;;
  *) docker compose "$@" ;;
esac
