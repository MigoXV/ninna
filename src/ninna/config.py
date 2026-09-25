from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    root: Path
    host_root: Path
    state: Path
    runtime_image: str = "ninna/pytorch-runtime:v3"

    @classmethod
    def from_env(cls):
        root = Path(os.environ.get("NINNA_ROOT", Path(__file__).resolve().parents[2])).resolve()
        host_root = Path(os.environ.get("NINNA_HOST_ROOT", str(root)))
        return cls(
            root,
            host_root,
            root / "outputs" / "platform",
            os.environ.get("NINNA_RUNTIME_IMAGE", "ninna/pytorch-runtime:v3"),
        )

    def host_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.root)
        return str(self.host_root / relative)
