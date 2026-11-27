"""Shared fixtures. The environment is set before anything imports ``app``."""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("TEST_PHONE_OTP", "123456")
