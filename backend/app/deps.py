"""Common FastAPI dependencies.

Module-specific dependencies (current customer, current admin, current cart…)
live inside the modules themselves so each module is self-contained.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.db import get_db

DbDep = Annotated[AsyncIOMotorDatabase[Any], Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
