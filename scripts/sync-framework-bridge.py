"""同步受版本控制的轻量桥接代码；不包含模型实现。"""

from pathlib import Path
import argparse
import shutil

parser = argparse.ArgumentParser()
parser.add_argument("repositories", nargs="+", type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[1] / "integrations/framework_bridge"
for repo in args.repositories:
    destination = repo / "integrations/ninna"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("runner.py", "callbacks.py", "prepare.py"):
        shutil.copyfile(source / name, destination / name)
    (repo / "integrations/__init__.py").touch()
    (destination / "__init__.py").touch()
