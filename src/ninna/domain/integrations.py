from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class HubSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    endpoint: str
    namespace: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    token: str | None = Field(default=None, repr=False)


class AimSettingsUpdate(BaseModel):
    enabled: bool


class IntegrationUpdate(BaseModel):
    hub: HubSettingsUpdate | None = None
    aim: AimSettingsUpdate | None = None


class HubPublish(BaseModel):
    kind: Literal["model", "dataset"]
    name: str
    version: str
    repo_id: str = Field(pattern=r"^[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+$")
    private: bool = True


class HubImport(BaseModel):
    kind: Literal["model", "dataset"]
    repo_id: str = Field(pattern=r"^[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+$")
    revision: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    version: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
