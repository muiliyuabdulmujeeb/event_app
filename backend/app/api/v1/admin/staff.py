from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session, require_admin
from app.repositories.staff_repository import StaffRepository
from app.schemas.staff import StaffAccountSummary

router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])


@router.get("", response_model=list[StaffAccountSummary])
async def list_staff_accounts(
    _: Annotated[object, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[StaffAccountSummary]:
    repository = StaffRepository(session)
    accounts = await repository.list_accounts()
    return [
        StaffAccountSummary(
            id=account.id,
            email=account.email,
            role=account.role.value,
            is_active=account.is_active,
            created_at=account.created_at,
        )
        for account in accounts
    ]
