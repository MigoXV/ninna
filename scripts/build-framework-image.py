"""构建最小显式上下文，兼容未安装 buildx 的 Docker。"""

import argparse
import hashlib
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("repository", type=Path)
parser.add_argument("--tag", required=True)
parser.add_argument(
    "--dependency-image",
    help="Reuse an existing image only when dependency declarations match exactly",
)
args = parser.parse_args()
repo = args.repository.resolve()
revision = subprocess.check_output(
    ["git", "-c", f"safe.directory={repo}", "-C", str(repo), "rev-parse", "HEAD"], text=True
).strip()
with tempfile.TemporaryDirectory(prefix="ninna-build-") as tmp:
    dest = Path(tmp)
    names = [
        "pyproject.toml",
        "poetry.lock",
        "README.md",
        "AGENTS.md",
        "ninna-framework.yaml",
        "Dockerfile.ninna",
        "src",
        "scripts",
        "examples",
        "model-zoo",
        "integrations",
        ".agents",
        "NOTICE",
        "LICENSE",
        "THIRD_PARTY.md",
    ]
    names.extend(p.name for p in repo.glob("requirements-*.txt"))
    for name in names:
        source = repo / name
        if source.is_dir():
            shutil.copytree(
                source,
                dest / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*", ".git", ".venv"),
                symlinks=True,
            )
        elif source.is_file():
            shutil.copyfile(source, dest / name)
    if any(p.is_symlink() for p in dest.rglob("*")):
        raise ValueError(
            "Build context contains symlinks; materialize the intended source explicitly"
        )
    digest = hashlib.sha256()
    for file in sorted(dest.rglob("*")):
        if file.is_file():
            digest.update(str(file.relative_to(dest)).encode())
            digest.update(file.read_bytes())
    revision += "+context." + digest.hexdigest()
    if args.dependency_image:
        image_id = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", args.dependency_image], text=True
        ).strip()
        container = subprocess.check_output(["docker", "create", image_id], text=True).strip()
        try:
            with tempfile.TemporaryDirectory(prefix="ninna-dependencies-") as comparison:
                declarations = ["pyproject.toml", "poetry.lock", "Dockerfile.ninna"]
                declarations.extend(p.name for p in dest.glob("requirements-*.txt"))
                for name in declarations:
                    previous = Path(comparison) / name
                    subprocess.run(
                        ["docker", "cp", f"{container}:/app/{name}", str(previous)],
                        check=True,
                        capture_output=True,
                    )
                    before, after = previous.read_text(), (dest / name).read_text()
                    if name == "pyproject.toml":
                        # Root package inclusion is reinstalled below; dependency declarations cannot change.
                        before = re.sub(r"(?m)^packages = .*\n", "", before)
                        after = re.sub(r"(?m)^packages = .*\n", "", after)
                    if before != after:
                        raise ValueError(f"Dependency image differs at {name}; use a full build")
        finally:
            subprocess.run(["docker", "rm", container], check=True, capture_output=True)
        (dest / "Dockerfile.ninna-reuse").write_text(
            f"FROM {image_id}\nUSER root\nWORKDIR /app\n"
            "RUN test -x /opt/venv/bin/python && rm -rf /app && mkdir /app\n"
            "COPY . .\nRUN poetry install --only-root --no-interaction && python -m pip check\n"
            'ARG SOURCE_REVISION\nLABEL org.opencontainers.image.revision=$SOURCE_REVISION\nCMD ["bash"]\n'
        )
    subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(dest / ("Dockerfile.ninna-reuse" if args.dependency_image else "Dockerfile.ninna")),
            "--build-arg",
            f"SOURCE_REVISION={revision}",
            "-t",
            args.tag,
            str(dest),
        ],
        check=True,
    )
