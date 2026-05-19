"""Versioned API package."""

from fastapi import APIRouter

from app.api.v1.admin.analytics import router as admin_analytics_router
from app.api.v1.admin.events import router as admin_events_router
from app.api.v1.admin.notifications import router as admin_notifications_router
from app.api.v1.admin.registrations import router as admin_registrations_router
from app.api.v1.admin.staff import router as admin_staff_router
from app.api.v1.auth import router as auth_router
from app.api.v1.payments import router as payments_router
from app.api.v1.public.events import router as public_events_router
from app.api.v1.public.exception_registrations import router as public_exception_registrations_router
from app.api.v1.public.lookup import router as public_lookup_router
from app.api.v1.public.payment_offers import router as public_payment_offers_router
from app.api.v1.public.registrations import router as public_registrations_router
from app.api.v1.public.self_service_registrations import router as public_self_service_registrations_router
from app.api.v1.staff import router as staff_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_staff_router)
api_router.include_router(admin_events_router)
api_router.include_router(admin_registrations_router)
api_router.include_router(admin_notifications_router)
api_router.include_router(admin_analytics_router)
api_router.include_router(payments_router)
api_router.include_router(staff_router)
api_router.include_router(public_events_router)
api_router.include_router(public_registrations_router)
api_router.include_router(public_self_service_registrations_router)
api_router.include_router(public_exception_registrations_router)
api_router.include_router(public_lookup_router)
api_router.include_router(public_payment_offers_router)
