"""Versioned API package."""

from fastapi import APIRouter

from app.api.v1.admin.staff import router as admin_staff_router
from app.api.v1.auth import router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_staff_router)
