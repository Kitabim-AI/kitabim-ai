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
from app.auth.dependencies import require_admin
from app.models.user import User

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
    current_user: User = Depends(require_admin),
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
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific system configuration (admin only)"""
    repo = SystemConfigsRepository(session)
    config = await repo.get(key)

    if not config:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")

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
            detail=f"Config key '{data.key}' already exists"
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
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")

    config.value = data.value
    if data.description is not None:
        config.description = data.description

    await session.commit()

    return SystemConfigResponse(
        key=config.key,
        value=config.value,
        description=config.description,
        updated_at=config.updated_at.isoformat()
    )


@router.delete("/{key}")
async def delete_config(
    key: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a system configuration (admin only)"""
    repo = SystemConfigsRepository(session)

    config = await repo.get(key)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")

    await repo.delete_one(key)
    await session.commit()

    return {"status": "deleted", "key": key}
