from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.event import EventState
from app.models.payment import PaymentStatus
from app.models.registration import RegistrationState
from app.schemas.waitlist_promotion import RegistrationLookupPromotionOfferResponse


class NotificationMethod(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"


class AdminNotificationType(str, enum.Enum):
    PRICE_CHANGE = "price_change"
    EVENT_CANCELLATION = "event_cancellation"
    REFUND = "refund"


class PriceChangeScope(str, enum.Enum):
    NEW_REGISTRATIONS_ONLY = "new_registrations_only"
    ALL_EXISTING_CONFIRMED = "all_existing_confirmed"


class RegistrationLookupCustomFieldValueResponse(BaseModel):
    label: str
    value: str


class RegistrationLookupRegistrationResponse(BaseModel):
    reg_id: str
    first_name: str
    last_name: str
    email: str
    state: RegistrationState
    is_checked_in: bool
    checked_in_at: datetime | None
    registered_at: datetime
    is_batch: bool
    custom_field_values: list[RegistrationLookupCustomFieldValueResponse]


class RegistrationLookupEventResponse(BaseModel):
    id: str
    title: str
    event_date: datetime
    location: str
    is_free: bool
    state: EventState


class RegistrationLookupPaymentResponse(BaseModel):
    status: PaymentStatus
    amount_paid: int
    currency: str
    paid_at: datetime | None


class UserNotificationResponse(BaseModel):
    id: str
    title: str
    body: str
    is_seen: bool
    created_at: datetime


class RegistrationLookupResponse(BaseModel):
    registration: RegistrationLookupRegistrationResponse
    event: RegistrationLookupEventResponse
    payment: RegistrationLookupPaymentResponse | None
    promotion_offer: RegistrationLookupPromotionOfferResponse | None = None
    notifications: list[UserNotificationResponse]


class UserNotificationSeenResponse(BaseModel):
    id: str
    is_seen: bool


class RegistrationRefundUpdateRequest(BaseModel):
    state: RegistrationState
    notification_method: NotificationMethod
    message_body: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("message_body", "title")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("state")
    @classmethod
    def validate_refund_state(cls, value: RegistrationState) -> RegistrationState:
        if value not in {RegistrationState.REFUND_REQUESTED, RegistrationState.REFUNDED}:
            raise ValueError("state must be one of: refund_requested, refunded")
        return value


class RegistrationRefundUpdateResponse(BaseModel):
    reg_id: str
    state: RegistrationState


class AdminNotificationCreateRequest(BaseModel):
    notification_type: AdminNotificationType
    notification_method: NotificationMethod = NotificationMethod.IN_APP
    body: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    event_id: str | None = Field(default=None, min_length=1, max_length=36)
    reg_id: str | None = Field(default=None, min_length=1, max_length=18)

    @field_validator("body", "title", "event_id", "reg_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @model_validator(mode="after")
    def validate_target(self) -> "AdminNotificationCreateRequest":
        if self.notification_type in {
            AdminNotificationType.PRICE_CHANGE,
            AdminNotificationType.EVENT_CANCELLATION,
        }:
            if self.event_id is None:
                raise ValueError("event_id is required for this notification type")
            if self.reg_id is not None:
                raise ValueError("reg_id is not allowed for this notification type")
        elif self.notification_type == AdminNotificationType.REFUND:
            if self.reg_id is None:
                raise ValueError("reg_id is required for refund notifications")
            if self.event_id is not None:
                raise ValueError("event_id is not allowed for refund notifications")
        return self


class AdminNotificationDispatchResponse(BaseModel):
    notification_type: AdminNotificationType
    notification_method: NotificationMethod
    user_notifications_created: int
    staff_notifications_created: int
    email_recipients_count: int
    message: str
