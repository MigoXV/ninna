#!/usr/bin/env bash
set -euo pipefail
if docker compose version >/dev/null 2>&1; then exit 0; fi
version=v2.39.4
case "$(uname -m)" in x86_64) arch=x86_64;; aarch64) arch=aarch64;; *) echo 'Unsupported architecture'; exit 1;; esac
plugin_dir="${DOCKER_CONFIG:-$HOME/.docker}/cli-plugins"
mkdir -p "$plugin_dir"
curl -fL --retry 3 "https://github.com/docker/compose/releases/download/$version/docker-compose-linux-$arch" -o "$plugin_dir/docker-compose"
chmod +x "$plugin_dir/docker-compose"
docker compose version
