from __future__ import annotations

from datetime import timedelta

import pytest
from jose import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import ALGORITHM, create_access_token, create_refresh_token, hash_token, utc_now
from app.models.staff import RefreshToken
from app.repositories.staff_repository import StaffRepository


async def login(client, email: str, password: str):
    return await client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


@pytest.mark.asyncio
async def test_admin_login_returns_access_and_refresh_tokens(client, seeded_admin_account, db_session) -> None:
    response = await login(client, "admin@eventapp.local", "Admin1234!")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"
    assert body["access_token_expires_in"] == 3600
    assert body["refresh_token_expires_in"] == 604800
    assert body["access_token"]
    assert body["refresh_token"]

    refresh_tokens = (await db_session.execute(select(RefreshToken))).scalars().all()
    assert len(refresh_tokens) == 1
    assert refresh_tokens[0].staff_id == seeded_admin_account.id
    assert refresh_tokens[0].token_hash == hash_token(body["refresh_token"])


@pytest.mark.asyncio
async def test_staff_login_returns_access_and_refresh_tokens(client, seeded_staff_account) -> None:
    response = await login(client, "staff@eventapp.local", "Staff1234!")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "staff"
    assert body["access_token"]
    assert body["refresh_token"]


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client, seeded_admin_account) -> None:
    response = await login(client, "admin@eventapp.local", "WrongPassword!")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_401(client) -> None:
    response = await login(client, "unknown@eventapp.local", "Admin1234!")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


@pytest.mark.asyncio
async def test_disabled_account_cannot_log_in(client, disabled_staff_account) -> None:
    response = await login(client, "disabled@eventapp.local", "Disabled1234!")

    assert response.status_code == 403
    assert response.json() == {"detail": "This account has been disabled."}


@pytest.mark.asyncio
async def test_valid_refresh_token_returns_new_access_token(client, seeded_admin_account) -> None:
    login_response = await login(client, "admin@eventapp.local", "Admin1234!")
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token_expires_in"] == 3600
    assert body["access_token"]


@pytest.mark.asyncio
async def test_expired_refresh_token_returns_401(client, seeded_admin_account, db_session) -> None:
    settings = get_settings()
    refresh_token, expires_at, token_id = create_refresh_token(
        account=seeded_admin_account,
        settings=settings,
        expires_delta=timedelta(seconds=-60),
    )
    repository = StaffRepository(db_session)
    await repository.create_refresh_token(
        token_id=token_id,
        staff_id=seeded_admin_account.id,
        token_hash=hash_token(refresh_token),
        expires_at=expires_at,
    )
    await db_session.commit()

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token is invalid or has expired. Please log in again."}


@pytest.mark.asyncio
async def test_tampered_refresh_token_returns_401(client, seeded_admin_account) -> None:
    login_response = await login(client, "admin@eventapp.local", "Admin1234!")
    refresh_token = login_response.json()["refresh_token"]
    tampered = f"{refresh_token[:-1]}x"

    response = await client.post("/auth/refresh", json={"refresh_token": tampered})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token is invalid or has expired. Please log in again."}


@pytest.mark.asyncio
async def test_unknown_refresh_token_returns_401(client, seeded_admin_account) -> None:
    settings = get_settings()
    now = utc_now()
    token = jwt.encode(
        {
            "sub": seeded_admin_account.id,
            "role": seeded_admin_account.role.value,
            "token_type": "refresh",
            "jti": "missing-refresh-token-id",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=7)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )

    response = await client.post("/auth/refresh", json={"refresh_token": token})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token is invalid or has expired. Please log in again."}


@pytest.mark.asyncio
async def test_revoked_refresh_token_returns_401(client, seeded_admin_account, db_session) -> None:
    settings = get_settings()
    refresh_token, expires_at, token_id = create_refresh_token(account=seeded_admin_account, settings=settings)
    repository = StaffRepository(db_session)
    await repository.create_refresh_token(
        token_id=token_id,
        staff_id=seeded_admin_account.id,
        token_hash=hash_token(refresh_token),
        expires_at=expires_at,
    )
    await repository.revoke_refresh_token(token_id, utc_now())
    await db_session.commit()

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token is invalid or has expired. Please log in again."}


@pytest.mark.asyncio
async def test_expired_access_token_rejected_on_admin_route(client, seeded_admin_account) -> None:
    settings = get_settings()
    access_token, _ = create_access_token(
        account=seeded_admin_account,
        settings=settings,
        expires_delta=timedelta(seconds=-60),
    )

    response = await client.get(
        "/admin/staff",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staff_token_cannot_access_admin_route(client, seeded_staff_account) -> None:
    login_response = await login(client, "staff@eventapp.local", "Staff1234!")
    access_token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/staff",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_token_can_access_admin_route(client, seeded_admin_account) -> None:
    login_response = await login(client, "admin@eventapp.local", "Admin1234!")
    access_token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/staff",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["email"] == "admin@eventapp.local"
