from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.registration import RegistrationState
from app.schemas.email import EmailMessage


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


class BatchParticipantRegistrationInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str
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


class BatchRegistrationCreateRequest(BaseModel):
    submitter_name: str = Field(min_length=1, max_length=255)
    submitter_email: str
    acknowledge_duplicates: bool = False
    participants: list[BatchParticipantRegistrationInput]

    @field_validator("submitter_name")
    @classmethod
    def validate_submitter_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("submitter_email")
    @classmethod
    def validate_submitter_email(cls, value: str) -> str:
        stripped = value.strip()
        if not re.fullmatch(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$", stripped):
            raise ValueError("value is not a valid email address")
        return stripped


class BatchRegistrationParticipantResponse(BaseModel):
    reg_id: str
    first_name: str
    last_name: str
    email: str


class BatchRegistrationCreateResponse(BaseModel):
    batch_id: str
    total_amount: int
    currency: str
    participant_count: int
    state: RegistrationState
    payment_url: str | None
    participants: list[BatchRegistrationParticipantResponse]
    message: str


class RegistrationServiceResult(BaseModel):
    response: RegistrationCreateResponse
    ticket_email_message: EmailMessage | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BatchRegistrationServiceResult(BaseModel):
    response: BatchRegistrationCreateResponse
    ticket_email_messages: list[EmailMessage] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
