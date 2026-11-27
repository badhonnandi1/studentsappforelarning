"""Response models for ``/v1/config/*``."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KillSwitches(BaseModel):
    tutor: bool
    photo_solve: bool
    registrations: bool
    payments: bool


class MinAppVersion(BaseModel):
    android: str
    web: str


class ClientConfigOut(BaseModel):
    kill_switches: KillSwitches
    min_app_version: MinAppVersion
    support: dict[str, str]
    server_time: datetime


class PresignOut(BaseModel):
    upload_url: str
    fields: dict[str, str] | None
    key: str
    expires_at: datetime
    max_bytes: int
