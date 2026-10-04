"""Versioned, declarative framework capabilities; no executable documentation."""

from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
from ninna.domain.schemas import StrictModel, Ref


class Operation(StrictModel):
    argv: list[str] = Field(min_length=1)
    required_inputs: dict[str, Literal["dataset", "model"]] = Field(default_factory=dict)
    required_artifacts: list[str] = Field(default_factory=list)
    needs_source: bool = False


class TaskDefinition(StrictModel):
    description: str
    operations: dict[str, Operation]
    metrics: dict[str, Literal["min", "max", "none"]] = Field(default_factory=dict)


class FrameworkManifest(Ref):
    protocol_version: Literal[1] = 1
    workdir: Literal["/app"] = "/app"
    skill: str
    python: str = "3.10"
    imports: list[str] = Field(
        default_factory=lambda: ["torch", "lightning", "transformers", "datasets"]
    )
    tasks: dict[str, TaskDefinition]

    @model_validator(mode="after")
    def validate_paths(self):
        from pathlib import PurePosixPath

        path = PurePosixPath(self.skill)
        if path.is_absolute() or ".." in path.parts or not str(path).startswith(".agents/skills/"):
            raise ValueError("skill must be a relative path under .agents/skills")
        allowed = {"prepare", "train", "evaluate", "export", "infer"}
        if not self.tasks or any(
            not t.operations or not set(t.operations) <= allowed for t in self.tasks.values()
        ):
            raise ValueError("Framework tasks must declare supported operations")
        return self


class ImportFramework(StrictModel):
    image: Ref
    workspace_name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
