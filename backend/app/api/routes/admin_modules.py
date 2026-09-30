"""Modules switched on and off from the admin (R4 / S6-S7).

  GET /admin/modules        — every module, its state and why
  PUT /admin/modules/{key}  — switch one on or off (no restart needed)

The public state (``enabled`` only) is part of ``GET /system/config`` so the
storefront and the admin menus follow it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentSuperUser, SessionDep
from app.features.system.modules import (
    MODULES,
    set_module,
    spec_for,
    stored_switches,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/modules", tags=["admin-modules"])


class ModuleState(BaseModel):
    key: str
    label: str
    description: str
    group: str
    #: The stored switch (what the admin chose).
    switched_on: bool
    #: What the storefront and the back end actually do.
    enabled: bool
    #: Value a fresh install gets in the current SHOP_MODE.
    preset: bool
    #: Environment variable that keeps the module off whatever the switch.
    blocked_by_env: str | None = None


class ModuleWrite(BaseModel):
    enabled: bool


async def _states(session: SessionDep) -> list[ModuleState]:
    stored = await stored_switches(session)
    states: list[ModuleState] = []
    for spec in MODULES:
        env_ok = spec.env_allows()
        states.append(
            ModuleState(
                key=spec.key,
                label=spec.label,
                description=spec.description,
                group=spec.group,
                switched_on=stored[spec.key],
                enabled=stored[spec.key] and env_ok,
                preset=spec.preset,
                blocked_by_env=None if env_ok else spec.env_gate_name,
            )
        )
    return states


@router.get("", response_model=list[ModuleState])
async def list_modules(
    session: SessionDep, _current_user: CurrentSuperUser
) -> list[ModuleState]:
    """Every module with its switch, its effective state and its preset."""
    return await _states(session)


@router.put("/{key}", response_model=ModuleState)
async def switch_module(
    key: str,
    payload: ModuleWrite,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> ModuleState:
    """Turn a module on or off. Nothing is deleted either way."""
    actor_id = current_user.id
    spec_for(key)  # 404 on an unknown key, before any write
    await set_module(session, key, payload.enabled)
    await session.commit()
    logger.warning(
        "Admin %s switched module %s %s",
        actor_id,
        key,
        "on" if payload.enabled else "off",
    )
    return next(state for state in await _states(session) if state.key == key)
