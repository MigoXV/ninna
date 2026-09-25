import json
import os
import socket
from pathlib import Path

from checkpoint import atomic_json
from trainer import train

if __name__ == "__main__":
    config = json.loads(Path("/config/run.json").read_text())
    atomic_json(
        Path("/output/process.json"),
        {
            "run_id": config["run_id"],
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "docker_env": Path("/.dockerenv").exists(),
            "cwd": os.getcwd(),
            "mountinfo": Path("/proc/self/mountinfo").read_text(),
        },
    )
    train(config)
