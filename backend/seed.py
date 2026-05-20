from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskFailureStatus, AsyncTaskType
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.exception_registration_offer import ExceptionRegistrationOffer, ExceptionRegistrationOfferStatus
from app.models.exception_registration_offer_audit import (
    ExceptionRegistrationOfferAudit,
    ExceptionRegistrationOfferAuditAction,
    ExceptionRegistrationOfferAuditActorType,
)
from app.models.manual_review_case import ManualReviewCase, ManualReviewCaseStatus, ManualReviewCaseType
from app.models.notification import StaffNotification, UserNotification
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.refund_request import RefundRequest, RefundRequestedBy, RefundRequestStatus
from app.models.registration import (
    BatchRegistration,
    CancellationReason,
    Registration,
    RegistrationFieldValue,
    RegistrationState,
)
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffEventAccess, StaffRole
from app.models.staff_event_authorization import StaffEventAuthorization
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus

SEED_LOGIN_PASSWORD = "SeedDemo123!"

STAFF_BLUEPRINTS = {
    "creator_admin": {
        "email": "creator.admin@eventapp.local",
        "role": StaffRole.ADMIN,
        "mode": StaffAccessMode.ALL_EVENTS,
    },
    "delegated_admin": {
        "email": "delegated.admin@eventapp.local",
        "role": StaffRole.ADMIN,
        "mode": StaffAccessMode.ALL_EVENTS,
    },
    "ops_admin": {
        "email": "ops.admin@eventapp.local",
        "role": StaffRole.ADMIN,
        "mode": StaffAccessMode.ALL_EVENTS,
    },
    "events_staff": {
        "email": "events.staff@eventapp.local",
        "role": StaffRole.STAFF,
        "mode": StaffAccessMode.ALL_EVENTS,
    },
    "review_staff": {
        "email": "review.staff@eventapp.local",
        "role": StaffRole.STAFF,
        "mode": StaffAccessMode.SELECTED_EVENTS,
    },
    "selected_staff": {
        "email": "selected.staff@eventapp.local",
        "role": StaffRole.STAFF,
        "mode": StaffAccessMode.SELECTED_EVENTS,
    },
}

SEED_STAFF_EMAILS = {key: blueprint["email"] for key, blueprint in STAFF_BLUEPRINTS.items()}

EVENT_BLUEPRINTS = {
    "community_free": {
        "title": "Community Meetup 2026",
        "description": "Free community meetup used for public event browsing and simple registrations.",
        "event_date": datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        "location": "Lagos, Nigeria",
        "prefix": "CMT",
        "price": 0,
        "capacity": None,
        "overflow_rule": OverflowRule.HARD_REJECTION,
        "state": EventState.PUBLISHED,
        "fields": [
            {"label": "Phone Number", "field_type": FieldType.PHONE, "is_required": True},
            {"label": "Community Track", "field_type": FieldType.TEXT, "is_required": False},
        ],
    },
    "tech_paid": {
        "title": "Tech Conference 2026",
        "description": "Primary paid event with single, batch, refund, and requeue coverage.",
        "event_date": datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        "location": "Abuja, Nigeria",
        "prefix": "TEC",
        "price": 15000,
        "capacity": 120,
        "overflow_rule": OverflowRule.WAITLIST,
        "state": EventState.PUBLISHED,
        "fields": [
            {"label": "Phone Number", "field_type": FieldType.PHONE, "is_required": True},
            {"label": "Company", "field_type": FieldType.TEXT, "is_required": False},
            {"label": "T-Shirt Size", "field_type": FieldType.TEXT, "is_required": False},
        ],
    },
    "waitlist_forum": {
        "title": "Design Leadership Forum",
        "description": "Capacity-limited paid event used to demonstrate waitlist flows.",
        "event_date": datetime(2026, 6, 25, 9, 0, tzinfo=UTC),
        "location": "Port Harcourt, Nigeria",
        "prefix": "WLT",
        "price": 8000,
        "capacity": 3,
        "overflow_rule": OverflowRule.WAITLIST,
        "state": EventState.PUBLISHED,
        "fields": [
            {"label": "Phone Number", "field_type": FieldType.PHONE, "is_required": True},
            {"label": "Team", "field_type": FieldType.TEXT, "is_required": False},
        ],
    },
    "full_override": {
        "title": "Investor Roundtable",
        "description": "Small paid event with capacity override and exception registration history.",
        "event_date": datetime(2026, 6, 15, 18, 0, tzinfo=UTC),
        "location": "Lagos, Nigeria",
        "prefix": "VIPX",
        "price": 25000,
        "capacity": 2,
        "overflow_rule": OverflowRule.WAITLIST,
        "state": EventState.PUBLISHED,
        "fields": [
            {"label": "Phone Number", "field_type": FieldType.PHONE, "is_required": True},
        ],
    },
    "roadmap_draft": {
        "title": "Roadmap Planning Session",
        "description": "Draft internal planning event.",
        "event_date": datetime(2026, 9, 5, 14, 0, tzinfo=UTC),
        "location": "Ibadan, Nigeria",
        "prefix": "RMP",
        "price": 5000,
        "capacity": 25,
        "overflow_rule": OverflowRule.HARD_REJECTION,
        "state": EventState.DRAFT,
        "fields": [],
    },
    "annual_completed": {
        "title": "Annual Summit 2026",
        "description": "Completed historical event with checked-in attendance data.",
        "event_date": datetime(2026, 4, 10, 8, 0, tzinfo=UTC),
        "location": "Enugu, Nigeria",
        "prefix": "SUM",
        "price": 10000,
        "capacity": 80,
        "overflow_rule": OverflowRule.HARD_REJECTION,
        "state": EventState.COMPLETED,
        "fields": [],
    },
    "partner_cancelled": {
        "title": "Partner Expo 2026",
        "description": "Cancelled partner event preserved for administrative review.",
        "event_date": datetime(2026, 10, 2, 11, 0, tzinfo=UTC),
        "location": "Kano, Nigeria",
        "prefix": "PEX",
        "price": 6000,
        "capacity": 40,
        "overflow_rule": OverflowRule.HARD_REJECTION,
        "state": EventState.CANCELLED,
        "fields": [],
    },
}

SEED_EVENT_PREFIXES = {key: blueprint["prefix"] for key, blueprint in EVENT_BLUEPRINTS.items()}

BATCH_BLUEPRINTS = {
    "tech_batch_main": {
        "event_key": "tech_paid",
        "submitter_name": "Batch Submitter",
        "submitter_email": "batch.submitter@example.com",
        "total_amount": 45000,
        "payment_reference": "SEED_TEC_BATCH_001",
    }
}

REGISTRATION_BLUEPRINTS = [
    {
        "event_key": "community_free",
        "reg_id": "CMT-2026-CNF001",
        "first_name": "Ada",
        "last_name": "Okafor",
        "email": "ada.okafor@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000001", "Community Track": "Backend"},
    },
    {
        "event_key": "community_free",
        "reg_id": "CMT-2026-CAN001",
        "first_name": "Musa",
        "last_name": "Bello",
        "email": "musa.bello@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 3, 9, 0, tzinfo=UTC),
        "cancellation_reason": CancellationReason.USER_CANCELLED,
        "fields": {"Phone Number": "+2348000000002", "Community Track": "Design"},
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-CNF001",
        "first_name": "Amaka",
        "last_name": "Nwosu",
        "email": "amaka.nwosu@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
        "fields": {
            "Phone Number": "+2348000000101",
            "Company": "Alpha Labs",
            "T-Shirt Size": "M",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-PND001",
        "first_name": "Kunle",
        "last_name": "Adebayo",
        "email": "kunle.adebayo@example.com",
        "state": RegistrationState.PENDING_PAYMENT,
        "registered_at": datetime(2026, 5, 5, 9, 0, tzinfo=UTC),
        "fields": {
            "Phone Number": "+2348000000102",
            "Company": "Beta Works",
            "T-Shirt Size": "L",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-FLD001",
        "first_name": "Ifeoma",
        "last_name": "Obi",
        "email": "ifeoma.obi@example.com",
        "state": RegistrationState.FAILED,
        "registered_at": datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
        "fields": {
            "Phone Number": "+2348000000103",
            "Company": "Gamma Studio",
            "T-Shirt Size": "S",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-RFD001",
        "first_name": "Tolu",
        "last_name": "Aina",
        "email": "tolu.aina@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 7, 9, 0, tzinfo=UTC),
        "cancellation_reason": CancellationReason.USER_CANCELLED,
        "fields": {
            "Phone Number": "+2348000000104",
            "Company": "Acme Ventures",
            "T-Shirt Size": "M",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-RRQ001",
        "first_name": "Lara",
        "last_name": "Ibrahim",
        "email": "lara.ibrahim@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        "cancellation_reason": CancellationReason.USER_CANCELLED,
        "fields": {
            "Phone Number": "+2348000000105",
            "Company": "Delta Grid",
            "T-Shirt Size": "XL",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-RRJ001",
        "first_name": "Bisi",
        "last_name": "Ojo",
        "email": "bisi.ojo@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 9, 9, 0, tzinfo=UTC),
        "cancellation_reason": CancellationReason.USER_CANCELLED,
        "fields": {
            "Phone Number": "+2348000000106",
            "Company": "Echo Retail",
            "T-Shirt Size": "L",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-BAT001",
        "first_name": "Chika",
        "last_name": "Team",
        "email": "batch1@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        "batch_key": "tech_batch_main",
        "fields": {
            "Phone Number": "+2348000000107",
            "Company": "BatchCo A",
            "T-Shirt Size": "M",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-BAT002",
        "first_name": "Femi",
        "last_name": "Team",
        "email": "batch2@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 10, 9, 5, tzinfo=UTC),
        "batch_key": "tech_batch_main",
        "fields": {
            "Phone Number": "+2348000000108",
            "Company": "BatchCo B",
            "T-Shirt Size": "S",
        },
    },
    {
        "event_key": "tech_paid",
        "reg_id": "TEC-2026-BAT003",
        "first_name": "Ngozi",
        "last_name": "Team",
        "email": "batch3@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 10, 9, 10, tzinfo=UTC),
        "batch_key": "tech_batch_main",
        "fields": {
            "Phone Number": "+2348000000109",
            "Company": "BatchCo C",
            "T-Shirt Size": "XL",
        },
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-CNF001",
        "first_name": "Dayo",
        "last_name": "Ola",
        "email": "dayo.ola@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000201", "Team": "Core UX"},
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-CNF002",
        "first_name": "Sade",
        "last_name": "Adewale",
        "email": "sade.adewale@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 11, 9, 5, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000202", "Team": "Research"},
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-CNF003",
        "first_name": "Yemi",
        "last_name": "Ajayi",
        "email": "yemi.ajayi@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 11, 9, 10, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000203", "Team": "Platform"},
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-WTL001",
        "first_name": "Nkechi",
        "last_name": "Agu",
        "email": "nkechi.agu@example.com",
        "state": RegistrationState.WAITLISTED,
        "registered_at": datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        "waitlist_position": 1,
        "was_waitlisted": True,
        "fields": {"Phone Number": "+2348000000204", "Team": "Ops"},
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-WTL002",
        "first_name": "Paul",
        "last_name": "Anyanwu",
        "email": "paul.anyanwu@example.com",
        "state": RegistrationState.WAITLISTED,
        "registered_at": datetime(2026, 5, 12, 9, 5, tzinfo=UTC),
        "waitlist_position": 2,
        "was_waitlisted": True,
        "fields": {"Phone Number": "+2348000000205", "Team": "Design"},
    },
    {
        "event_key": "waitlist_forum",
        "reg_id": "WLT-2026-WTL003",
        "first_name": "Ruth",
        "last_name": "Daniels",
        "email": "ruth.daniels@example.com",
        "state": RegistrationState.WAITLISTED,
        "registered_at": datetime(2026, 5, 12, 9, 10, tzinfo=UTC),
        "waitlist_position": 3,
        "was_waitlisted": True,
        "fields": {"Phone Number": "+2348000000206", "Team": "Growth"},
    },
    {
        "event_key": "full_override",
        "reg_id": "VIPX-2026-CNF001",
        "first_name": "Morenike",
        "last_name": "Cole",
        "email": "morenike.cole@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 13, 9, 0, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000301"},
    },
    {
        "event_key": "full_override",
        "reg_id": "VIPX-2026-CNF002",
        "first_name": "Tari",
        "last_name": "Tamuno",
        "email": "tari.tamuno@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 13, 9, 5, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000302"},
    },
    {
        "event_key": "full_override",
        "reg_id": "VIPX-2026-EXC001",
        "first_name": "Chioma",
        "last_name": "Udeh",
        "email": "chioma.udeh@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 5, 13, 9, 10, tzinfo=UTC),
        "fields": {"Phone Number": "+2348000000303"},
    },
    {
        "event_key": "full_override",
        "reg_id": "VIPX-2026-CAN001",
        "first_name": "Ikenna",
        "last_name": "Nnamdi",
        "email": "ikenna.nnamdi@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 13, 9, 15, tzinfo=UTC),
        "was_waitlisted": True,
        "previous_waitlist_position": 1,
        "cancellation_reason": CancellationReason.OVERFLOW_RULE_CHANGED,
        "fields": {"Phone Number": "+2348000000304"},
    },
    {
        "event_key": "annual_completed",
        "reg_id": "SUM-2026-CNF001",
        "first_name": "Janet",
        "last_name": "Kingsley",
        "email": "janet.kingsley@example.com",
        "state": RegistrationState.CONFIRMED,
        "registered_at": datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
        "is_checked_in": True,
        "checked_in_at": datetime(2026, 4, 10, 8, 30, tzinfo=UTC),
        "fields": {},
    },
    {
        "event_key": "partner_cancelled",
        "reg_id": "PEX-2026-CAN001",
        "first_name": "Segun",
        "last_name": "Adisa",
        "email": "segun.adisa@example.com",
        "state": RegistrationState.CANCELLED,
        "registered_at": datetime(2026, 5, 14, 9, 0, tzinfo=UTC),
        "cancellation_reason": CancellationReason.USER_CANCELLED,
        "fields": {},
    },
]

SEED_REFERENCE_REG_IDS = {
    "completed_refund": "TEC-2026-RFD001",
    "active_refund_request": "TEC-2026-RRQ001",
    "waitlist_offer": "WLT-2026-WTL001",
    "waitlist_manual_review": "WLT-2026-WTL003",
    "capacity_override": "VIPX-2026-EXC001",
    "former_waitlist_history": "VIPX-2026-CAN001",
    "checked_in_completed": "SUM-2026-CNF001",
}

PAYMENT_BLUEPRINTS = [
    {
        "payment_reference": "SEED_TEC_CNF001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "TEC-2026-CNF001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 4, 9, 15, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_PND001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.FAILED,
        "registration_reg_id": "TEC-2026-PND001",
        "attempt_number": 1,
        "current_for_registration": False,
    },
    {
        "payment_reference": "SEED_TEC_PND001_ATT2",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.PENDING,
        "registration_reg_id": "TEC-2026-PND001",
        "attempt_number": 2,
        "gateway_checkout_url": "https://example.local/checkout/seed-tec-pnd001",
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_FLD001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.FAILED,
        "registration_reg_id": "TEC-2026-FLD001",
        "attempt_number": 1,
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_RFD001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "TEC-2026-RFD001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 7, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_RRQ001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "TEC-2026-RRQ001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 8, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_RRJ001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 15000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "TEC-2026-RRJ001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 9, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_TEC_BATCH_001",
        "gateway": PaymentGateway.MOCK,
        "amount": 45000,
        "status": PaymentStatus.SUCCESSFUL,
        "batch_key": "tech_batch_main",
        "paid_at": datetime(2026, 5, 10, 9, 30, tzinfo=UTC),
    },
    {
        "payment_reference": "SEED_WLT_CNF001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 8000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "WLT-2026-CNF001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 11, 9, 15, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_WLT_CNF002_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 8000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "WLT-2026-CNF002",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 11, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_WLT_CNF003_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 8000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "WLT-2026-CNF003",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 11, 9, 25, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_WLT_WTL003_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 8000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "WLT-2026-WTL003",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 12, 9, 30, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_VIPX_CNF001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 25000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "VIPX-2026-CNF001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 13, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_VIPX_CNF002_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 25000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "VIPX-2026-CNF002",
        "attempt_number": 1,
        "paid_at": datetime(2026, 5, 13, 9, 25, tzinfo=UTC),
        "current_for_registration": True,
    },
    {
        "payment_reference": "SEED_SUM_CNF001_ATT1",
        "gateway": PaymentGateway.MOCK,
        "amount": 10000,
        "status": PaymentStatus.SUCCESSFUL,
        "registration_reg_id": "SUM-2026-CNF001",
        "attempt_number": 1,
        "paid_at": datetime(2026, 3, 10, 9, 20, tzinfo=UTC),
        "current_for_registration": True,
    },
]

REFUND_BLUEPRINTS = [
    {
        "registration_reg_id": "TEC-2026-RFD001",
        "status": RefundRequestStatus.COMPLETED,
        "requested_by": RefundRequestedBy.PUBLIC,
        "reason": "Speaker schedule conflict",
        "requested_at": datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
        "processed_by_staff_key": "ops_admin",
        "processed_at": datetime(2026, 5, 9, 10, 0, tzinfo=UTC),
        "resolution_notes": "Refund settled and communicated.",
    },
    {
        "registration_reg_id": "TEC-2026-RRQ001",
        "status": RefundRequestStatus.REQUESTED,
        "requested_by": RefundRequestedBy.PUBLIC,
        "reason": "Employer travel freeze",
        "requested_at": datetime(2026, 5, 9, 10, 0, tzinfo=UTC),
    },
    {
        "registration_reg_id": "TEC-2026-RRJ001",
        "status": RefundRequestStatus.REJECTED,
        "requested_by": RefundRequestedBy.PUBLIC,
        "reason": "Duplicate booking request",
        "requested_at": datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        "processed_by_staff_key": "ops_admin",
        "processed_at": datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
        "resolution_notes": "Refund rejected after review.",
    },
]

WAITLIST_PROMOTION_BLUEPRINTS = [
    {
        "registration_reg_id": "WLT-2026-WTL001",
        "event_key": "waitlist_forum",
        "offered_by_staff_key": "review_staff",
        "offer_expires_at": datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        "status": WaitlistPromotionOfferStatus.OFFERED,
        "gateway_checkout_url": "https://example.local/offers/wlt-001",
        "public_token": "01JSEEDWLT0000000000000001",
    },
    {
        "registration_reg_id": "WLT-2026-WTL002",
        "event_key": "waitlist_forum",
        "offered_by_staff_key": "review_staff",
        "offer_expires_at": datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        "status": WaitlistPromotionOfferStatus.EXPIRED,
        "public_token": "01JSEEDWLT0000000000000002",
    },
    {
        "registration_reg_id": "WLT-2026-WTL003",
        "event_key": "waitlist_forum",
        "offered_by_staff_key": "review_staff",
        "offer_expires_at": datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        "status": WaitlistPromotionOfferStatus.MANUAL_REVIEW,
        "payment_reference": "SEED_WLT_WTL003_ATT1",
        "gateway_checkout_url": "https://example.local/offers/wlt-003",
        "public_token": "01JSEEDWLT0000000000000003",
    },
]

EXCEPTION_OFFER_BLUEPRINTS = [
    {
        "key": "vip_used",
        "event_key": "full_override",
        "issued_by_staff_key": "creator_admin",
        "target_email": "chioma.udeh@example.com",
        "target_first_name": "Chioma",
        "target_last_name": "Udeh",
        "payment_waived": True,
        "capacity_override": True,
        "expires_at": datetime(2026, 5, 14, 12, 0, tzinfo=UTC),
        "status": ExceptionRegistrationOfferStatus.USED,
        "used_registration_reg_id": "VIPX-2026-EXC001",
        "public_token": "01JSEEDVIP0000000000000001",
        "audits": [
            {
                "action": ExceptionRegistrationOfferAuditAction.ISSUED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.STAFF,
                "actor_staff_key": "creator_admin",
                "details": "VIP speaker invite",
            },
            {
                "action": ExceptionRegistrationOfferAuditAction.REGISTRATION_ATTEMPTED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.PUBLIC,
                "details": "Invitee opened the exception registration link.",
            },
            {
                "action": ExceptionRegistrationOfferAuditAction.REGISTRATION_SUCCEEDED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.SYSTEM,
                "details": "Capacity override registration completed without payment.",
            },
        ],
    },
    {
        "key": "tech_revoked",
        "event_key": "tech_paid",
        "issued_by_staff_key": "delegated_admin",
        "target_email": "speaker.priority@example.com",
        "target_first_name": "Priority",
        "target_last_name": "Speaker",
        "source_reg_id": "TEC-2026-FLD001",
        "payment_waived": False,
        "capacity_override": True,
        "expires_at": datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        "status": ExceptionRegistrationOfferStatus.REVOKED,
        "public_token": "01JSEEDTEC0000000000000002",
        "audits": [
            {
                "action": ExceptionRegistrationOfferAuditAction.ISSUED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.STAFF,
                "actor_staff_key": "delegated_admin",
                "details": "Recovery offer for failed VIP attendee.",
            },
            {
                "action": ExceptionRegistrationOfferAuditAction.REVOKED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.STAFF,
                "actor_staff_key": "creator_admin",
                "details": "Revoked after attendee confirmed they could not travel.",
            },
        ],
    },
    {
        "key": "vip_expired",
        "event_key": "full_override",
        "issued_by_staff_key": "creator_admin",
        "target_email": "expired.vip@example.com",
        "payment_waived": False,
        "capacity_override": True,
        "expires_at": datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
        "status": ExceptionRegistrationOfferStatus.EXPIRED,
        "public_token": "01JSEEDVIP0000000000000003",
        "audits": [
            {
                "action": ExceptionRegistrationOfferAuditAction.ISSUED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.STAFF,
                "actor_staff_key": "creator_admin",
                "details": "Reserved seat for investor guest.",
            },
            {
                "action": ExceptionRegistrationOfferAuditAction.EXPIRED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.SYSTEM,
                "details": "Offer expired without use.",
            },
        ],
    },
    {
        "key": "tech_issued",
        "event_key": "tech_paid",
        "issued_by_staff_key": "creator_admin",
        "target_email": "founder.guest@example.com",
        "payment_waived": False,
        "capacity_override": True,
        "expires_at": datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        "status": ExceptionRegistrationOfferStatus.ISSUED,
        "public_token": "01JSEEDTEC0000000000000004",
        "audits": [
            {
                "action": ExceptionRegistrationOfferAuditAction.ISSUED,
                "actor_type": ExceptionRegistrationOfferAuditActorType.STAFF,
                "actor_staff_key": "creator_admin",
                "details": "Executive guest exception offer.",
            }
        ],
    },
]

MANUAL_REVIEW_BLUEPRINTS = [
    {
        "summary": "Late payment success requires waitlist reconciliation",
        "details": "A promoted waitlist payment succeeded after the offer had effectively expired.",
        "event_key": "waitlist_forum",
        "registration_reg_id": "WLT-2026-WTL003",
        "payment_reference": "SEED_WLT_WTL003_ATT1",
        "case_type": ManualReviewCaseType.LATE_PAYMENT_SUCCESS,
        "status": ManualReviewCaseStatus.OPEN,
        "created_by_system": True,
        "assigned_to_staff_key": "review_staff",
    },
    {
        "summary": "Requeue completed for pending payment attendee",
        "details": "Finance reopened the attendee after the first attempt timed out.",
        "event_key": "tech_paid",
        "registration_reg_id": "TEC-2026-PND001",
        "payment_reference": "SEED_TEC_PND001_ATT1",
        "case_type": ManualReviewCaseType.PAYMENT_TIMEOUT_REQUEUE,
        "status": ManualReviewCaseStatus.RESOLVED,
        "created_by_system": False,
        "created_by_staff_key": "ops_admin",
        "resolved_by_staff_key": "review_staff",
        "resolution_action": "requeue_registration",
        "resolution_notes": "Fresh payment attempt issued to attendee.",
        "resolved_at": datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    },
    {
        "summary": "Exception registration details under review",
        "details": "Team is validating guest list details before reissuing an executive exception offer.",
        "event_key": "full_override",
        "case_type": ManualReviewCaseType.EXCEPTION_REGISTRATION_ISSUE,
        "status": ManualReviewCaseStatus.IN_PROGRESS,
        "created_by_system": False,
        "created_by_staff_key": "creator_admin",
        "assigned_to_staff_key": "ops_admin",
    },
]

ASYNC_TASK_FAILURE_BLUEPRINTS = [
    {
        "task_name": "send_email:tech-payment-reminder",
        "task_type": AsyncTaskType.EMAIL,
        "failure_category": "provider_exhausted",
        "status": AsyncTaskFailureStatus.OPEN,
        "event_key": "tech_paid",
        "registration_reg_id": "TEC-2026-PND001",
        "payment_reference": "SEED_TEC_PND001_ATT2",
        "provider_attempts": [
            {"provider": "resend", "attempt": 1, "error_class": "EmailDeliveryError", "error_message": "503 service unavailable", "timestamp": "2026-05-06T09:00:00Z"},
            {"provider": "resend", "attempt": 2, "error_class": "EmailDeliveryError", "error_message": "503 service unavailable", "timestamp": "2026-05-06T09:01:00Z"},
            {"provider": "zoho_mail", "attempt": 1, "error_class": "EmailDeliveryError", "error_message": "rate limit", "timestamp": "2026-05-06T09:02:00Z"},
            {"provider": "zoho_mail", "attempt": 2, "error_class": "EmailDeliveryError", "error_message": "rate limit", "timestamp": "2026-05-06T09:03:00Z"},
            {"provider": "sendgrid", "attempt": 1, "error_class": "EmailDeliveryError", "error_message": "provider unavailable", "timestamp": "2026-05-06T09:04:00Z"},
        ],
        "attempt_count": 5,
        "error_class": "EmailDeliveryError",
        "error_message": "All configured email providers failed to deliver the reminder.",
        "payload_metadata": {"to": ["kunle.adebayo@example.com"], "subject": "Complete your payment", "template": "payment_reminder"},
        "final_failed_at": datetime(2026, 5, 6, 9, 4, tzinfo=UTC),
    },
    {
        "task_name": "send_email:waitlist-promotion",
        "task_type": AsyncTaskType.EMAIL,
        "failure_category": "provider_exhausted",
        "status": AsyncTaskFailureStatus.ACKNOWLEDGED,
        "event_key": "waitlist_forum",
        "registration_reg_id": "WLT-2026-WTL001",
        "provider_attempts": [
            {"provider": "resend", "attempt": 1, "error_class": "EmailDeliveryError", "error_message": "temporary outage", "timestamp": "2026-05-12T10:00:00Z"},
            {"provider": "resend", "attempt": 2, "error_class": "EmailDeliveryError", "error_message": "temporary outage", "timestamp": "2026-05-12T10:01:00Z"},
            {"provider": "zoho_mail", "attempt": 1, "error_class": "EmailDeliveryError", "error_message": "temporary outage", "timestamp": "2026-05-12T10:02:00Z"},
            {"provider": "zoho_mail", "attempt": 2, "error_class": "EmailDeliveryError", "error_message": "temporary outage", "timestamp": "2026-05-12T10:03:00Z"},
        ],
        "attempt_count": 4,
        "error_class": "EmailDeliveryError",
        "error_message": "Waitlist promotion email exhausted the configured providers.",
        "payload_metadata": {"to": ["nkechi.agu@example.com"], "subject": "Your waitlist promotion is ready", "template": "waitlist_promotion"},
        "acknowledged_by_staff_key": "review_staff",
        "acknowledged_at": datetime(2026, 5, 12, 11, 0, tzinfo=UTC),
        "final_failed_at": datetime(2026, 5, 12, 10, 3, tzinfo=UTC),
    },
    {
        "task_name": "send_email:system-summary",
        "task_type": AsyncTaskType.EMAIL,
        "failure_category": "validation_failure",
        "status": AsyncTaskFailureStatus.RESOLVED,
        "provider_attempts": [
            {"provider": "resend", "attempt": 1, "error_class": "EmailMessageValidationError", "error_message": "missing recipient", "timestamp": "2026-05-13T10:00:00Z"},
        ],
        "attempt_count": 1,
        "error_class": "EmailMessageValidationError",
        "error_message": "System summary email failed validation before provider fallback.",
        "payload_metadata": {"template": "system_summary", "recipient_group": "finance-ops"},
        "resolved_by_staff_key": "ops_admin",
        "resolved_at": datetime(2026, 5, 13, 11, 0, tzinfo=UTC),
        "resolution_notes": "Template recipient list corrected for next run.",
        "final_failed_at": datetime(2026, 5, 13, 10, 0, tzinfo=UTC),
    },
]

USER_NOTIFICATION_BLUEPRINTS = [
    {
        "reg_id": "TEC-2026-RFD001",
        "title": "Refund Completed",
        "body": "Your refund has been completed successfully.",
        "is_seen": False,
    },
    {
        "reg_id": "TEC-2026-RRQ001",
        "title": "Refund Request Received",
        "body": "Your refund request is awaiting review.",
        "is_seen": False,
    },
    {
        "reg_id": "WLT-2026-WTL001",
        "title": "Waitlist Promotion Available",
        "body": "Your promotion offer is active and awaiting your response.",
        "is_seen": False,
    },
    {
        "reg_id": "VIPX-2026-CAN001",
        "title": "Waitlist Preserved For Analytics",
        "body": "Your prior waitlist position is still visible in lookup history.",
        "is_seen": True,
    },
]

STAFF_NOTIFICATION_BLUEPRINTS = [
    {
        "staff_key": "review_staff",
        "title": "Manual Review Assigned",
        "body": "A late payment success case requires review on Design Leadership Forum.",
        "is_read": False,
    },
    {
        "staff_key": "ops_admin",
        "title": "Dead Letter Requires Follow-Up",
        "body": "A system summary email failed validation and needs a recipient fix.",
        "is_read": True,
    },
    {
        "staff_key": "creator_admin",
        "title": "Exception Offer Revoked",
        "body": "The delegated admin exception offer for speaker.priority@example.com was revoked.",
        "is_read": False,
    },
]


@dataclass
class SeedRegistry:
    staff: dict[str, StaffAccount] = field(default_factory=dict)
    events: dict[str, Event] = field(default_factory=dict)
    fields: dict[tuple[str, str], EventFieldDefinition] = field(default_factory=dict)
    batches: dict[str, BatchRegistration] = field(default_factory=dict)
    registrations: dict[str, Registration] = field(default_factory=dict)
    payments: dict[str, Payment] = field(default_factory=dict)
    exception_offers: dict[str, ExceptionRegistrationOffer] = field(default_factory=dict)


async def seed_database(session: AsyncSession) -> dict[str, int]:
    registry = SeedRegistry()
    await seed_staff_accounts(session, registry)
    await seed_events(session, registry)
    await seed_staff_access_and_authorizations(session, registry)
    await seed_batch_registrations(session, registry)
    await seed_registrations(session, registry)
    await seed_payments(session, registry)
    await seed_refund_requests(session, registry)
    await seed_waitlist_promotions(session, registry)
    await seed_exception_offers(session, registry)
    await seed_manual_review_cases(session, registry)
    await seed_async_task_failures(session, registry)
    await seed_notifications(session, registry)
    await session.flush()
    return await build_seed_summary(session)


async def seed_staff_accounts(session: AsyncSession, registry: SeedRegistry) -> None:
    for key, blueprint in STAFF_BLUEPRINTS.items():
        account = await fetch_one_or_none(session, StaffAccount, email=blueprint["email"])
        if account is None:
            account = StaffAccount(email=blueprint["email"], password_hash="", role=blueprint["role"])
            session.add(account)
        account.password_hash = hash_password(SEED_LOGIN_PASSWORD)
        account.role = blueprint["role"]
        account.is_active = True
        await session.flush()
        access_mode_record = await fetch_one_or_none(session, StaffAccessModeRecord, staff_id=account.id)
        if access_mode_record is None:
            access_mode_record = StaffAccessModeRecord(staff_id=account.id, mode=blueprint["mode"])
            session.add(access_mode_record)
        else:
            access_mode_record.mode = blueprint["mode"]
        registry.staff[key] = account
    await session.flush()


async def seed_events(session: AsyncSession, registry: SeedRegistry) -> None:
    creator = registry.staff["creator_admin"]
    for event_key, blueprint in EVENT_BLUEPRINTS.items():
        event = await fetch_one_or_none(session, Event, prefix=blueprint["prefix"])
        if event is None:
            event = Event(prefix=blueprint["prefix"], created_by=creator.id)
            session.add(event)
        event.title = blueprint["title"]
        event.description = blueprint["description"]
        event.event_date = blueprint["event_date"]
        event.location = blueprint["location"]
        event.price = blueprint["price"]
        event.capacity = blueprint["capacity"]
        event.overflow_rule = blueprint["overflow_rule"]
        event.state = blueprint["state"]
        event.created_by = creator.id
        await session.flush()
        registry.events[event_key] = event
        for display_order, field_blueprint in enumerate(blueprint["fields"], start=1):
            field_definition = await fetch_one_or_none(
                session,
                EventFieldDefinition,
                event_id=event.id,
                display_order=display_order,
            )
            if field_definition is None:
                field_definition = EventFieldDefinition(event_id=event.id, display_order=display_order)
                session.add(field_definition)
            field_definition.label = field_blueprint["label"]
            field_definition.field_type = field_blueprint["field_type"]
            field_definition.is_required = field_blueprint["is_required"]
            field_definition.display_order = display_order
            registry.fields[(event_key, field_definition.label)] = field_definition
        await session.flush()


async def seed_staff_access_and_authorizations(session: AsyncSession, registry: SeedRegistry) -> None:
    await ensure_staff_event_access(session, registry.staff["review_staff"], registry.events["tech_paid"])
    await ensure_staff_event_access(session, registry.staff["review_staff"], registry.events["waitlist_forum"])
    await ensure_staff_event_access(session, registry.staff["selected_staff"], registry.events["community_free"])

    await ensure_staff_event_authorization(
        session,
        staff=registry.staff["delegated_admin"],
        event=registry.events["full_override"],
        granted_by=registry.staff["creator_admin"],
        can_manage_exception_offers=True,
        can_change_overflow_rule=True,
    )
    await ensure_staff_event_authorization(
        session,
        staff=registry.staff["review_staff"],
        event=registry.events["tech_paid"],
        granted_by=registry.staff["creator_admin"],
        can_manage_manual_reviews=True,
        can_requeue_registrations=True,
    )
    await ensure_staff_event_authorization(
        session,
        staff=registry.staff["review_staff"],
        event=registry.events["waitlist_forum"],
        granted_by=registry.staff["creator_admin"],
        can_manage_manual_reviews=True,
        can_requeue_registrations=True,
    )
    await session.flush()


async def seed_batch_registrations(session: AsyncSession, registry: SeedRegistry) -> None:
    for key, blueprint in BATCH_BLUEPRINTS.items():
        event = registry.events[blueprint["event_key"]]
        batch = await fetch_one_or_none(
            session,
            BatchRegistration,
            event_id=event.id,
            submitter_email=blueprint["submitter_email"],
        )
        if batch is None:
            batch = BatchRegistration(event_id=event.id, submitter_email=blueprint["submitter_email"])
            session.add(batch)
        batch.submitter_name = blueprint["submitter_name"]
        batch.submitter_email = blueprint["submitter_email"]
        batch.total_amount = blueprint["total_amount"]
        batch.payment_reference = blueprint["payment_reference"]
        registry.batches[key] = batch
    await session.flush()


async def seed_registrations(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in REGISTRATION_BLUEPRINTS:
        event = registry.events[blueprint["event_key"]]
        registration = await fetch_one_or_none(session, Registration, reg_id=blueprint["reg_id"])
        if registration is None:
            registration = Registration(reg_id=blueprint["reg_id"], event_id=event.id)
            session.add(registration)
        registration.event_id = event.id
        registration.first_name = blueprint["first_name"]
        registration.last_name = blueprint["last_name"]
        registration.email = blueprint["email"]
        registration.state = blueprint["state"]
        registration.is_checked_in = blueprint.get("is_checked_in", False)
        registration.checked_in_at = blueprint.get("checked_in_at")
        registration.waitlist_position = blueprint.get("waitlist_position")
        registration.was_waitlisted = blueprint.get("was_waitlisted", False)
        registration.previous_waitlist_position = blueprint.get("previous_waitlist_position")
        registration.cancellation_reason = blueprint.get("cancellation_reason")
        registration.registered_at = blueprint["registered_at"]
        batch_key = blueprint.get("batch_key")
        registration.batch_id = registry.batches[batch_key].id if batch_key else None
        await session.flush()
        for label, value in blueprint["fields"].items():
            field_definition = registry.fields[(blueprint["event_key"], label)]
            field_value = await fetch_one_or_none(
                session,
                RegistrationFieldValue,
                registration_id=registration.id,
                field_definition_id=field_definition.id,
            )
            if field_value is None:
                field_value = RegistrationFieldValue(
                    registration_id=registration.id,
                    field_definition_id=field_definition.id,
                    value=value,
                )
                session.add(field_value)
            else:
                field_value.value = value
        registry.registrations[registration.reg_id] = registration
    await session.flush()


async def seed_payments(session: AsyncSession, registry: SeedRegistry) -> None:
    current_payment_mapping: dict[str, str] = {}
    for blueprint in PAYMENT_BLUEPRINTS:
        payment = await fetch_one_or_none(session, Payment, payment_reference=blueprint["payment_reference"])
        if payment is None:
            payment = Payment(payment_reference=blueprint["payment_reference"], gateway=blueprint["gateway"], amount=0, status=blueprint["status"])
            session.add(payment)
        payment.gateway = blueprint["gateway"]
        payment.amount = blueprint["amount"]
        payment.currency = "NGN"
        payment.status = blueprint["status"]
        payment.attempt_number = blueprint.get("attempt_number", 1)
        payment.paid_at = blueprint.get("paid_at")
        payment.gateway_checkout_url = blueprint.get("gateway_checkout_url")
        if "registration_reg_id" in blueprint:
            payment.registration_id = registry.registrations[blueprint["registration_reg_id"]].id
            payment.batch_id = None
            if blueprint.get("current_for_registration"):
                current_payment_mapping[blueprint["registration_reg_id"]] = payment.payment_reference
        else:
            payment.registration_id = None
            payment.batch_id = registry.batches[blueprint["batch_key"]].id
        registry.payments[payment.payment_reference] = payment
    await session.flush()
    for reg_id, payment_reference in current_payment_mapping.items():
        registry.registrations[reg_id].current_payment_id = registry.payments[payment_reference].id
    await session.flush()


async def seed_refund_requests(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in REFUND_BLUEPRINTS:
        registration = registry.registrations[blueprint["registration_reg_id"]]
        refund_request = await fetch_one_or_none(session, RefundRequest, registration_id=registration.id)
        if refund_request is None:
            refund_request = RefundRequest(registration_id=registration.id, requested_by=blueprint["requested_by"])
            session.add(refund_request)
        refund_request.status = blueprint["status"]
        refund_request.requested_by = blueprint["requested_by"]
        refund_request.reason = blueprint.get("reason")
        refund_request.requested_at = blueprint["requested_at"]
        processed_by_staff_key = blueprint.get("processed_by_staff_key")
        refund_request.processed_by_staff_id = registry.staff[processed_by_staff_key].id if processed_by_staff_key else None
        refund_request.processed_at = blueprint.get("processed_at")
        refund_request.resolution_notes = blueprint.get("resolution_notes")
    await session.flush()


async def seed_waitlist_promotions(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in WAITLIST_PROMOTION_BLUEPRINTS:
        registration = registry.registrations[blueprint["registration_reg_id"]]
        offer = await fetch_one_or_none(session, WaitlistPromotionOffer, registration_id=registration.id)
        if offer is None:
            offer = WaitlistPromotionOffer(registration_id=registration.id, event_id=registry.events[blueprint["event_key"]].id)
            session.add(offer)
        offer.public_token = blueprint["public_token"]
        offer.event_id = registry.events[blueprint["event_key"]].id
        offer.offered_by_staff_id = registry.staff[blueprint["offered_by_staff_key"]].id
        offer.offer_expires_at = blueprint["offer_expires_at"]
        offer.status = blueprint["status"]
        offer.gateway_checkout_url = blueprint.get("gateway_checkout_url")
        payment_reference = blueprint.get("payment_reference")
        offer.payment_id = registry.payments[payment_reference].id if payment_reference else None
    await session.flush()


async def seed_exception_offers(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in EXCEPTION_OFFER_BLUEPRINTS:
        event = registry.events[blueprint["event_key"]]
        offer = await fetch_one_or_none(session, ExceptionRegistrationOffer, event_id=event.id, target_email=blueprint["target_email"])
        if offer is None:
            offer = ExceptionRegistrationOffer(event_id=event.id, target_email=blueprint["target_email"], issued_by_staff_id=registry.staff[blueprint["issued_by_staff_key"]].id, expires_at=blueprint["expires_at"])
            session.add(offer)
        offer.public_token = blueprint["public_token"]
        offer.event_id = event.id
        offer.issued_by_staff_id = registry.staff[blueprint["issued_by_staff_key"]].id
        offer.target_email = blueprint["target_email"]
        offer.target_first_name = blueprint.get("target_first_name")
        offer.target_last_name = blueprint.get("target_last_name")
        offer.source_reg_id = blueprint.get("source_reg_id")
        offer.payment_waived = blueprint["payment_waived"]
        offer.capacity_override = blueprint["capacity_override"]
        offer.expires_at = blueprint["expires_at"]
        offer.status = blueprint["status"]
        used_registration_reg_id = blueprint.get("used_registration_reg_id")
        offer.used_registration_id = registry.registrations[used_registration_reg_id].id if used_registration_reg_id else None
        registry.exception_offers[blueprint["key"]] = offer
        await session.flush()
        for audit_blueprint in blueprint["audits"]:
            audit_entry = await fetch_one_or_none(
                session,
                ExceptionRegistrationOfferAudit,
                offer_id=offer.id,
                action=audit_blueprint["action"],
                details=audit_blueprint.get("details"),
            )
            if audit_entry is None:
                audit_entry = ExceptionRegistrationOfferAudit(
                    offer_id=offer.id,
                    action=audit_blueprint["action"],
                    actor_type=audit_blueprint["actor_type"],
                )
                session.add(audit_entry)
            audit_entry.action = audit_blueprint["action"]
            audit_entry.actor_type = audit_blueprint["actor_type"]
            actor_staff_key = audit_blueprint.get("actor_staff_key")
            audit_entry.actor_staff_id = registry.staff[actor_staff_key].id if actor_staff_key else None
            audit_entry.details = audit_blueprint.get("details")
    await session.flush()


async def seed_manual_review_cases(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in MANUAL_REVIEW_BLUEPRINTS:
        case = await fetch_one_or_none(session, ManualReviewCase, summary=blueprint["summary"])
        if case is None:
            case = ManualReviewCase(summary=blueprint["summary"], case_type=blueprint["case_type"], status=blueprint["status"])
            session.add(case)
        case.summary = blueprint["summary"]
        case.details = blueprint.get("details")
        case.event_id = registry.events[blueprint["event_key"]].id if blueprint.get("event_key") else None
        case.registration_id = registry.registrations[blueprint["registration_reg_id"]].id if blueprint.get("registration_reg_id") else None
        payment_reference = blueprint.get("payment_reference")
        case.payment_id = registry.payments[payment_reference].id if payment_reference else None
        case.case_type = blueprint["case_type"]
        case.status = blueprint["status"]
        case.created_by_system = blueprint.get("created_by_system", False)
        created_by_staff_key = blueprint.get("created_by_staff_key")
        assigned_to_staff_key = blueprint.get("assigned_to_staff_key")
        resolved_by_staff_key = blueprint.get("resolved_by_staff_key")
        case.created_by_staff_id = registry.staff[created_by_staff_key].id if created_by_staff_key else None
        case.assigned_to_staff_id = registry.staff[assigned_to_staff_key].id if assigned_to_staff_key else None
        case.resolved_by_staff_id = registry.staff[resolved_by_staff_key].id if resolved_by_staff_key else None
        case.resolution_action = blueprint.get("resolution_action")
        case.resolution_notes = blueprint.get("resolution_notes")
        case.resolved_at = blueprint.get("resolved_at")
    await session.flush()


async def seed_async_task_failures(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in ASYNC_TASK_FAILURE_BLUEPRINTS:
        failure = await fetch_one_or_none(session, AsyncTaskFailure, task_name=blueprint["task_name"])
        if failure is None:
            failure = AsyncTaskFailure(
                task_name=blueprint["task_name"],
                task_type=blueprint["task_type"],
                failure_category=blueprint["failure_category"],
                attempt_count=blueprint["attempt_count"],
                error_class=blueprint["error_class"],
                error_message=blueprint["error_message"],
                final_failed_at=blueprint["final_failed_at"],
            )
            session.add(failure)
        failure.task_name = blueprint["task_name"]
        failure.task_type = blueprint["task_type"]
        failure.failure_category = blueprint["failure_category"]
        failure.status = blueprint["status"]
        failure.event_id = registry.events[blueprint["event_key"]].id if blueprint.get("event_key") else None
        failure.registration_id = registry.registrations[blueprint["registration_reg_id"]].id if blueprint.get("registration_reg_id") else None
        payment_reference = blueprint.get("payment_reference")
        failure.payment_id = registry.payments[payment_reference].id if payment_reference else None
        acknowledged_by_staff_key = blueprint.get("acknowledged_by_staff_key")
        resolved_by_staff_key = blueprint.get("resolved_by_staff_key")
        failure.acknowledged_by_staff_id = registry.staff[acknowledged_by_staff_key].id if acknowledged_by_staff_key else None
        failure.acknowledged_at = blueprint.get("acknowledged_at")
        failure.resolved_by_staff_id = registry.staff[resolved_by_staff_key].id if resolved_by_staff_key else None
        failure.resolved_at = blueprint.get("resolved_at")
        failure.resolution_notes = blueprint.get("resolution_notes")
        failure.provider_attempts = blueprint.get("provider_attempts")
        failure.attempt_count = blueprint["attempt_count"]
        failure.error_class = blueprint["error_class"]
        failure.error_message = blueprint["error_message"]
        failure.payload_metadata = blueprint.get("payload_metadata")
        failure.final_failed_at = blueprint["final_failed_at"]
    await session.flush()


async def seed_notifications(session: AsyncSession, registry: SeedRegistry) -> None:
    for blueprint in USER_NOTIFICATION_BLUEPRINTS:
        notification = await fetch_one_or_none(
            session,
            UserNotification,
            reg_id=blueprint["reg_id"],
            title=blueprint["title"],
        )
        if notification is None:
            notification = UserNotification(reg_id=blueprint["reg_id"], title=blueprint["title"], body=blueprint["body"])
            session.add(notification)
        notification.body = blueprint["body"]
        notification.is_seen = blueprint["is_seen"]

    for blueprint in STAFF_NOTIFICATION_BLUEPRINTS:
        staff = registry.staff[blueprint["staff_key"]]
        notification = await fetch_one_or_none(
            session,
            StaffNotification,
            staff_id=staff.id,
            title=blueprint["title"],
        )
        if notification is None:
            notification = StaffNotification(staff_id=staff.id, title=blueprint["title"], body=blueprint["body"])
            session.add(notification)
        notification.body = blueprint["body"]
        notification.is_read = blueprint["is_read"]
    await session.flush()


async def ensure_staff_event_access(session: AsyncSession, staff: StaffAccount, event: Event) -> None:
    access = await fetch_one_or_none(session, StaffEventAccess, staff_id=staff.id, event_id=event.id)
    if access is None:
        session.add(StaffEventAccess(staff_id=staff.id, event_id=event.id))


async def ensure_staff_event_authorization(
    session: AsyncSession,
    *,
    staff: StaffAccount,
    event: Event,
    granted_by: StaffAccount,
    can_manage_exception_offers: bool = False,
    can_change_overflow_rule: bool = False,
    can_manage_manual_reviews: bool = False,
    can_requeue_registrations: bool = False,
) -> None:
    authorization = await fetch_one_or_none(session, StaffEventAuthorization, staff_id=staff.id, event_id=event.id)
    if authorization is None:
        authorization = StaffEventAuthorization(staff_id=staff.id, event_id=event.id, granted_by_staff_id=granted_by.id)
        session.add(authorization)
    authorization.can_manage_exception_offers = can_manage_exception_offers
    authorization.can_change_overflow_rule = can_change_overflow_rule
    authorization.can_manage_manual_reviews = can_manage_manual_reviews
    authorization.can_requeue_registrations = can_requeue_registrations
    authorization.granted_by_staff_id = granted_by.id
    authorization.revoked_by_staff_id = None
    authorization.revoked_at = None


async def fetch_one_or_none(
    session: AsyncSession,
    model,
    /,
    **filters: Any,
):
    statement = select(model)
    for key, value in filters.items():
        statement = statement.where(getattr(model, key) == value)
    return (await session.execute(statement)).scalar_one_or_none()


async def build_seed_summary(session: AsyncSession) -> dict[str, int]:
    return {
        "staff_accounts": await count_rows(session, StaffAccount),
        "events": await count_rows(session, Event),
        "event_field_definitions": await count_rows(session, EventFieldDefinition),
        "batch_registrations": await count_rows(session, BatchRegistration),
        "registrations": await count_rows(session, Registration),
        "payments": await count_rows(session, Payment),
        "refund_requests": await count_rows(session, RefundRequest),
        "waitlist_promotion_offers": await count_rows(session, WaitlistPromotionOffer),
        "exception_registration_offers": await count_rows(session, ExceptionRegistrationOffer),
        "exception_registration_offer_audits": await count_rows(session, ExceptionRegistrationOfferAudit),
        "manual_review_cases": await count_rows(session, ManualReviewCase),
        "async_task_failures": await count_rows(session, AsyncTaskFailure),
        "user_notifications": await count_rows(session, UserNotification),
        "staff_notifications": await count_rows(session, StaffNotification),
    }


async def count_rows(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


def format_seed_report(summary: dict[str, int]) -> str:
    report_lines = [
        "Seed data applied successfully.",
        "",
        "Demo login password:",
        f"  {SEED_LOGIN_PASSWORD}",
        "",
        "Staff accounts:",
    ]
    for key, email in SEED_STAFF_EMAILS.items():
        report_lines.append(f"  {key}: {email}")
    report_lines.extend(
        [
            "",
            "Reference registration IDs:",
        ]
    )
    for key, reg_id in SEED_REFERENCE_REG_IDS.items():
        report_lines.append(f"  {key}: {reg_id}")
    report_lines.extend(
        [
            "",
            "Summary counts:",
        ]
    )
    for table_name, count in summary.items():
        report_lines.append(f"  {table_name}: {count}")
    return "\n".join(report_lines)


async def run_seed() -> dict[str, int]:
    async with SessionLocal() as session:
        try:
            summary = await seed_database(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return summary


def main() -> None:
    summary = asyncio.run(run_seed())
    print(format_seed_report(summary))


if __name__ == "__main__":
    main()
