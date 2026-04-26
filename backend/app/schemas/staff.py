from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    access_token_expires_in: int
    refresh_token_expires_in: int
    role: str


class RefreshAccessTokenRequest(BaseModel):
    refresh_token: str


class RefreshAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str
    access_token_expires_in: int


class StaffAccountSummary(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
