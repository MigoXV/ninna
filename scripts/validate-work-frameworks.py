"""Replay the ten registered framework training scenarios through the v2 work API."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("NINNA_INTEGRATION") != "1":
        raise SystemExit("Set NINNA_INTEGRATION=1 for real Docker acceptance")
    previous = json.loads((ROOT / "docs/framework-verification.json").read_text())
    db = sqlite3.connect(
        f"file:{ROOT}/outputs/framework-integration/platform/ninna.sqlite3?mode=ro", uri=True
    )
    api = os.environ.get("NINNA_API_URL", "http://127.0.0.1:8021")
    gpu = os.environ.get("NINNA_TEST_GPU")
    records = []
    destination = ROOT / "outputs/work-v2-validation/frameworks"
    destination.mkdir(parents=True, exist_ok=True)
    for chain in previous["chains"]:
        run = json.loads(
            db.execute("SELECT body FROM runs WHERE id=?", (chain["train"],)).fetchone()[0]
        )
        spec = run["task_spec"]
        registered = next(r for r in previous["registered"] if r["framework"] == chain["framework"])
        command = [
            sys.executable,
            str(ROOT / "scripts/framework-smoke.py"),
            chain["framework"],
            chain["task"],
            spec["recipe"]["name"],
            "--runtime-version",
            registered["runtime_version"],
            "--workspace-name",
            registered["workspace"],
            "--recipe-version",
            registered["runtime_version"],
            "--api",
            api,
            "--memory",
            str(spec["execution_spec"]["resources"]["memory_mb"]),
        ]
        for kind in ("model", "dataset"):
            command.extend(["--" + kind, spec["inputs"][kind]["ref"]["name"]])
        if spec["execution_spec"]["resources"]["device"] == "cuda":
            if not gpu:
                raise SystemExit("NINNA_TEST_GPU must explicitly select a free GPU UUID")
            command.extend(["--gpu", gpu])
        key = chain["framework"] + "-" + chain["task"]
        with (destination / (key + ".log")).open("w") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        lines = (destination / (key + ".log")).read_text().splitlines()
        evidence = next(
            (json.loads(line) for line in reversed(lines) if line.startswith('{"id":')), {}
        )
        records.append(
            {
                "framework": chain["framework"],
                "task": chain["task"],
                "exit_code": result.returncode,
                "evidence": evidence,
            }
        )
        (destination / "evidence.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2)
        )
        print(
            json.dumps(
                {"scenario": key, "exit_code": result.returncode, "run_id": evidence.get("id")}
            ),
            flush=True,
        )
        if result.returncode:
            raise SystemExit(f"Inspect {destination / (key + '.log')}")


if __name__ == "__main__":
    main()
