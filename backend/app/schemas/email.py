from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


EMAIL_REGEX = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class EmailMessage(BaseModel):
    from_email: str
    from_name: str | None = None
    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1)
    text_body: str = Field(min_length=1)
    html_body: str | None = None
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    reply_to: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("from_email", "reply_to")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not EMAIL_REGEX.fullmatch(stripped):
            raise ValueError("value is not a valid email address")
        return stripped

    @field_validator("to", "cc", "bcc")
    @classmethod
    def validate_email_list(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for email in value:
            stripped = email.strip()
            if not EMAIL_REGEX.fullmatch(stripped):
                raise ValueError("value is not a valid email address")
            normalized.append(stripped)
        return normalized

    @field_validator("subject", "text_body")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

