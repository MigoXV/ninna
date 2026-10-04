from typing import Literal

from pydantic import Field

from ninna.domain.schemas import StrictModel, Ref, Resources


class Mutation(StrictModel):
    request_id: str = Field(min_length=1, max_length=160)


class SourceInput(Mutation):
    name: str = Field(min_length=1, max_length=120)
    endpoint: str
    protocol: Literal["hf"] = "hf"
    token_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    enabled: bool = True


class SourceUpdate(SourceInput):
    expected_version: int


class Acquire(Mutation):
    kind: Literal["model", "dataset"]
    name: str = Field(min_length=1, max_length=160)
    source_id: str | None = None
    repo_id: str | None = None
    revision: str = "main"
    url: str | None = None
    local_path: str | None = None


class PublishAsset(Mutation):
    source_id: str
    repo_id: str
    private: bool = True


class EnvironmentInput(Mutation):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    image_ref: Ref
    workspace_name: str | None = None
    framework: Ref | None = None
    git_url: str | None = None
    git_revision: str | None = None


class WorkInput(Mutation):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=20000)
    environment_revision_id: str
    constraints: str = Field(default="", max_length=10000)


class WorkUpdate(Mutation):
    expected_version: int
    summary: str = Field(default="", max_length=20000)
    next_step: str = Field(default="", max_length=10000)
    status: Literal["ACTIVE", "WAITING", "COMPLETED", "ARCHIVED"] = "ACTIVE"


class FileEdit(Mutation):
    path: str
    content: str | None = Field(default=None, max_length=1_000_000)
    expected_sha256: str | None = None
    delete: bool = False


class Command(Mutation):
    argv: list[str] = Field(min_length=1, max_length=200)
    cwd: str = "."
    timeout_seconds: int = Field(default=600, ge=1, le=86400)


class PlanInput(Mutation):
    work_item_id: str
    task: str
    operation: Literal["prepare", "train", "evaluate", "export", "infer"] = "train"
    inputs: dict[str, str] = Field(default_factory=dict)
    recipe: Ref
    resources: Resources = Field(default_factory=Resources)
    source_run_id: str | None = None
    source_path: str | None = None
    parent_run_id: str | None = None


class SubmitRun(Mutation):
    plan_id: str


class Binding(Mutation):
    """Explicit training metadata for a downloaded immutable payload."""

    metadata: dict


class UploadInput(Mutation):
    kind: Literal["model", "dataset"]
    name: str = Field(min_length=1, max_length=160)


class UploadFile(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=0)
