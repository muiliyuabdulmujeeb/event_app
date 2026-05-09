from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.registration import RegistrationState


class RegistrationCustomFieldValueInput(BaseModel):
    field_definition_id: str = Field(min_length=1, max_length=36)
    value: str

    @field_validator("value")
    @classmethod
    def validate_non_empty_value(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("custom field values must not be empty")
        return stripped


class RegistrationCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str
    acknowledge_duplicate: bool = False
    custom_field_values: list[RegistrationCustomFieldValueInput] = Field(default_factory=list)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        stripped = value.strip()
        if not re.fullmatch(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$", stripped):
            raise ValueError("value is not a valid email address")
        return stripped


class RegistrationCreateResponse(BaseModel):
    reg_id: str
    state: RegistrationState
    is_free: bool
    payment_url: str | None
    message: str


class RegistrationServiceResult(BaseModel):
    response: RegistrationCreateResponse
    ticket_email_payload: dict | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
