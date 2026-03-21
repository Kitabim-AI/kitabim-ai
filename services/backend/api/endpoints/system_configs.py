"""System configuration API endpoints"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_session
from app.db.models import SystemConfig
from app.db.repositories.system_configs import SystemConfigsRepository
from auth.dependencies import require_admin, require_editor
from app.models.user import User
from app.core.i18n import t
from app.langchain.models import (
    get_circuit_breaker_status,
    reset_circuit_breakers,
    force_open_circuit_breakers,
)

router = APIRouter()


class SystemConfigResponse(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: str

    class Config:
        from_attributes = True


class SystemConfigCreate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


@router.get("/", response_model=List[SystemConfigResponse])
async def list_configs(
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """List all system configurations (admin only)"""
    stmt = select(SystemConfig).order_by(SystemConfig.key)
    result = await session.execute(stmt)
    configs = result.scalars().all()

    return [
        SystemConfigResponse(
            key=config.key,
            value=config.value,
            description=config.description,
            updated_at=config.updated_at.isoformat()
        )
        for config in configs
    ]


@router.get("/{key}", response_model=SystemConfigResponse)
async def get_config(
    key: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific system configuration (admin only)"""
    repo = SystemConfigsRepository(session)
    config = await repo.get(key)

    if not config:
        raise HTTPException(status_code=404, detail=t("errors.config_not_found", key=key))


    return SystemConfigResponse(
        key=config.key,
        value=config.value,
        description=config.description,
        updated_at=config.updated_at.isoformat()
    )


@router.post("/", response_model=SystemConfigResponse)
async def create_config(
    data: SystemConfigCreate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Create a new system configuration (admin only)"""
    repo = SystemConfigsRepository(session)

    # Check if key already exists
    existing = await repo.get(data.key)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=t("errors.config_already_exists", key=data.key)
        )

    config = await repo.create(
        key=data.key,
        value=data.value,
        description=data.description
    )
    await session.commit()

    return SystemConfigResponse(
        key=config.key,
        value=config.value,
        description=config.description,
        updated_at=config.updated_at.isoformat()
    )


@router.put("/{key}", response_model=SystemConfigResponse)
async def update_config(
    key: str,
    data: SystemConfigUpdate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update a system configuration (admin only)"""
    repo = SystemConfigsRepository(session)

    config = await repo.get(key)
    if not config:
        raise HTTPException(status_code=404, detail=t("errors.config_not_found", key=key))

    config.value = data.value
    if data.description is not None:
        config.description = data.description

    await session.commit()
    await session.refresh(config)

    return SystemConfigResponse(
        key=config.key,
        value=config.value,
        description=config.description,
        updated_at=config.updated_at.isoformat()
    )


@router.get("/circuit-breaker/status")
async def get_circuit_breaker_status_endpoint(
    current_user: User = Depends(require_editor),
):
    """Get circuit breaker status (editor and above)"""
    return await get_circuit_breaker_status()


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker_endpoint(
    name: Optional[str] = None,
    current_user: User = Depends(require_admin),
):
    """Manually reset (close) circuit breakers (admin only)"""
    return await reset_circuit_breakers(name=name)


@router.post("/circuit-breaker/open")
async def force_open_circuit_breaker_endpoint(
    name: Optional[str] = None,
    current_user: User = Depends(require_editor),
):
    """Manually open circuit breakers (admin only)"""
    return await force_open_circuit_breakers(name=name)
