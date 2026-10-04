"""Runs inside the task container. Results survive MCP/platform disconnection."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys

root = Path(sys.argv[1])
request = json.loads((root / "request.json").read_text())
with (root / "stdout.log").open("wb") as stdout, (root / "stderr.log").open("wb") as stderr:
    process = subprocess.Popen(
        request["argv"], cwd=request["cwd"], stdout=stdout, stderr=stderr, start_new_session=True
    )
    (root / "pid").write_text(str(process.pid))
    try:
        code = process.wait(timeout=request["timeout_seconds"])
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = 124
    finally:
        # Commands must not leave untracked child processes behind.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
(root / "exit.json.tmp").write_text(json.dumps({"exit_code": code}))
(root / "exit.json.tmp").replace(root / "exit.json")
