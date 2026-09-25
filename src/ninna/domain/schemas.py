from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ref(StrictModel):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$")
    version: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$")


class TrainingSpec(StrictModel):
    dataset: Ref
    model: Ref
    recipe: Ref


class WorkspaceRef(StrictModel):
    name: str = "mnist-hf"
    snapshot: str = "current"


class Resources(StrictModel):
    device: str = "cpu"
    gpu_count: int = 0
    cpu_threads: int = Field(default=4, ge=1, le=32)
    memory_mb: int = Field(default=4096, ge=512, le=65536)

    @model_validator(mode="after")
    def cpu_only(self):
        if self.device != "cpu" or self.gpu_count != 0:
            raise ValueError("MVP supports CPU only; use device=cpu and gpu_count=0")
        return self


class ExecutionSpec(StrictModel):
    runtime: Ref
    workspace: WorkspaceRef
    resources: Resources = Field(default_factory=Resources)


class CreateRun(StrictModel):
    training_spec: TrainingSpec
    execution_spec: ExecutionSpec
    parent_run_id: str | None = None


class Status(str, Enum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL = {"SUCCESS", "FAILED", "CANCELLED"}
TRANSITIONS = {
    "CREATED": {"PREPARING", "CANCELLED", "FAILED"},
    "PREPARING": {"RUNNING", "CANCELLED", "FAILED"},
    "RUNNING": TERMINAL,
}
