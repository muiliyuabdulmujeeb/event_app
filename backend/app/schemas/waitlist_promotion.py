from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.registration import RegistrationState
from app.models.waitlist_promotion_offer import WaitlistPromotionOfferStatus


class WaitlistPromotionRequest(BaseModel):
    offer_expires_at: datetime | None = None

    @field_validator("offer_expires_at")
    @classmethod
    def validate_timezone_aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("offer_expires_at must include timezone information.")
        return value


class WaitlistPromotionResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    promotion_offer_status: WaitlistPromotionOfferStatus
    offer_expires_at: datetime
    payment_action_url: str
    message: str


class RegistrationLookupPromotionOfferResponse(BaseModel):
    public_token: str
    status: WaitlistPromotionOfferStatus
    offer_expires_at: datetime
    payment_action_url: str | None
