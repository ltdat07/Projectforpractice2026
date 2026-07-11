from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProfileStatus = Literal["inactive", "active", "error"]
ActionResult = Literal["success", "error"]
CoreMode = Literal["demo", "xray"]


class NetworkProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    protocol: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    config: dict[str, Any] = Field(default_factory=dict)


class NetworkProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    config: dict[str, Any] | None = None


class NetworkProfileRead(BaseModel):
    id: int
    name: str
    host: str
    port: int
    protocol: str
    status: ProfileStatus
    description: str | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CoreValidationRead(BaseModel):
    profile_id: int
    mode: CoreMode
    valid: bool
    message: str
    config_path: str | None = None


class RuntimeStatusRead(BaseModel):
    profile_id: int
    mode: CoreMode
    status: ProfileStatus
    running: bool
    pid: int | None = None
    message: str


class ProfileLogsRead(BaseModel):
    profile_id: int
    lines: list[str]


class ActionLogRead(BaseModel):
    id: int
    profile_id: int | None
    action: str
    result: ActionResult
    message: str
    created_at: datetime
