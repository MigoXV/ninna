#!/usr/bin/env python3
"""Resolve bind sources from an explicitly named outer container's inspect."""
import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
local_config = {}
config_file = root / '.env'
if config_file.exists():
    for line in config_file.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            if key.strip() in {'NINNA_OUTER_CONTAINER', 'NINNA_HOST_ROOT'}:
                local_config[key.strip()] = value.strip().strip('"').strip("'")
host = os.environ.get('NINNA_HOST_ROOT') or local_config.get('NINNA_HOST_ROOT')
if not host:
    container = os.environ.get('NINNA_OUTER_CONTAINER') or local_config.get('NINNA_OUTER_CONTAINER')
    if not container and Path('/.dockerenv').exists():
        # Match this container's cgroup/hostname only when it is unambiguous.
        candidates = [os.environ.get('HOSTNAME', '')]
        for candidate in candidates:
            if candidate and subprocess.run(['docker', 'inspect', candidate], capture_output=True).returncode == 0:
                container = candidate
                break
        if not container:
            raise SystemExit('Set NINNA_OUTER_CONTAINER or NINNA_HOST_ROOT for this container environment')
    if container:
        info = json.loads(subprocess.check_output(['docker', 'inspect', container]))[0]
        matches = [m for m in info['Mounts'] if m['Type'] == 'bind'
                   and root.is_relative_to(Path(m['Destination']))]
        if not matches:
            raise SystemExit('Project is not on a shared bind mount; set NINNA_HOST_ROOT explicitly')
        mount = max(matches, key=lambda m: len(m['Destination']))
        host = str(Path(mount['Source']) / root.relative_to(mount['Destination']))
    else:
        host = str(root)
print(json.dumps({'root': str(root), 'host_root': host}))
