from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.models.async_task_failure import AsyncTaskFailure, AsyncTaskType
from app.models.event import Event, EventState, OverflowRule
from app.models.registration import Registration, RegistrationState
from app.models.staff import StaffAccount
from app.schemas.email import EmailMessage
from app.services.email_providers import build_email_provider
from app.services.email_providers.base import EmailSendResult
from app.services.email_providers.amazon_ses_provider import AmazonSesEmailProvider
from app.services.email_providers.console_provider import ConsoleEmailProvider
from app.services.email_providers.mailgun_provider import MailgunEmailProvider
from app.services.email_providers.mock_provider import MockEmailProvider, get_mock_outbox
from app.services.email_providers.resend_provider import ResendEmailProvider
from app.services.email_providers.sendgrid_provider import SendGridEmailProvider
from app.services.email_providers.zoho_mail_provider import ZohoMailProvider
from app.services.email_service import EmailService
from app.workers.email_tasks import EmailRetryRequired, _send_email, send_email_task


def build_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb",
        "TEST_DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb_test",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "changeme",
        "EMAIL_PROVIDER": "mock",
        "EMAIL_PROVIDER_FAILOVER_CHAIN": "resend,zoho_mail,sendgrid,mailgun,amazon_ses",
        "EMAIL_PROVIDER_ATTEMPTS_PER_PROVIDER": 2,
        "EMAIL_FROM": "noreply@eventapp.local",
        "EMAIL_FROM_NAME": "Event Management",
        "RESEND_API_BASE_URL": "https://api.resend.com",
        "SENDGRID_API_BASE_URL": "https://api.sendgrid.com",
        "MAILGUN_API_BASE_URL": "https://api.mailgun.net",
        "ZOHO_MAIL_API_BASE_URL": "https://mail.zoho.com",
        "ACTIVE_PAYMENT_GATEWAY": "mock",
        "MOCK_PAYMENT_BASE_URL": "http://localhost:8000",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_message(**overrides: object) -> EmailMessage:
    payload = {
        "from_email": "noreply@eventapp.local",
        "from_name": "Event Management",
        "to": ["amina@example.com"],
        "subject": "Your ticket for Community Meetup 2026",
        "text_body": "Ticket details",
        "html_body": "<p>Ticket details</p>",
        "metadata": {"reg_id": "CMT-2026-ABC123"},
    }
    payload.update(overrides)
    return EmailMessage(**payload)


class FakeEmailProvider:
    def __init__(self, provider_name: str, outcomes: dict[str, list[object]]) -> None:
        self.provider_name = provider_name
        self._outcomes = outcomes

    async def send(self, message: EmailMessage) -> EmailSendResult:
        outcome = self._outcomes[self.provider_name].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return EmailSendResult(provider=self.provider_name, external_id=str(outcome) if outcome is not None else None)


async def create_registration_for_dead_letter(db_session, seeded_admin_account: StaffAccount) -> Registration:
    event = Event(
        title="Email Dead Letter Event",
        description="Email failure linkage event",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix="EDL",
        price=5000,
        capacity=20,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.PUBLISHED,
        created_by=seeded_admin_account.id,
    )
    db_session.add(event)
    await db_session.flush()

    registration = Registration(
        event_id=event.id,
        first_name="Amina",
        last_name="Deadletter",
        email="deadletter@example.com",
        reg_id="EDL-2026-ABC123",
        state=RegistrationState.CONFIRMED,
    )
    db_session.add(registration)
    await db_session.commit()
    await db_session.refresh(registration)
    return registration


def test_build_email_provider_rejects_unknown_provider() -> None:
    settings = build_settings(EMAIL_PROVIDER="unknown")

    with pytest.raises(EmailConfigurationError, match="EMAIL_PROVIDER 'unknown' is not supported"):
        build_email_provider(settings)


@pytest.mark.asyncio
async def test_email_service_enqueue_message_uses_celery_task(
    captured_email_tasks: list[dict],
) -> None:
    service = EmailService(settings=build_settings())
    message = build_message()

    service.enqueue_message(message)

    assert captured_email_tasks == [message.model_dump(mode="json")]


@pytest.mark.asyncio
async def test_console_email_provider_prints_email_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    provider = ConsoleEmailProvider(build_settings(EMAIL_PROVIDER="console"))

    result = await provider.send(build_message())

    captured = capsys.readouterr()
    assert result.provider == "console"
    assert "=== EMAIL ===" in captured.out
    assert "Subject: Your ticket for Community Meetup 2026" in captured.out
    assert "To: amina@example.com" in captured.out


@pytest.mark.asyncio
async def test_mock_email_provider_captures_email_in_memory() -> None:
    provider = MockEmailProvider(build_settings(EMAIL_PROVIDER="mock"))
    message = build_message()

    result = await provider.send(message)

    assert result.provider == "mock"
    assert get_mock_outbox() == [message.model_dump(mode="json")]


@pytest.mark.asyncio
async def test_resend_provider_uses_documented_send_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["user_agent"] = request.headers["User-Agent"]
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"id": "email_123"})

    settings = build_settings(EMAIL_PROVIDER="resend", RESEND_API_KEY="re_test_key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ResendEmailProvider(settings, client=client)
        result = await provider.send(build_message(reply_to="support@example.com", headers={"X-Test": "yes"}))

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["authorization"] == "Bearer re_test_key"
    assert captured["user_agent"] == "event-manager/0.1"
    assert captured["body"] == {
        "from": "Event Management <noreply@eventapp.local>",
        "to": ["amina@example.com"],
        "subject": "Your ticket for Community Meetup 2026",
        "text": "Ticket details",
        "html": "<p>Ticket details</p>",
        "reply_to": "support@example.com",
        "headers": {"X-Test": "yes"},
        "tags": [{"name": "reg_id", "value": "CMT-2026-ABC123"}],
    }
    assert result.provider == "resend"
    assert result.external_id == "email_123"


@pytest.mark.asyncio
async def test_sendgrid_provider_uses_documented_mail_send_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(202, headers={"X-Message-Id": "sg_123"})

    settings = build_settings(EMAIL_PROVIDER="sendgrid", SENDGRID_API_KEY="SG.test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SendGridEmailProvider(settings, client=client)
        result = await provider.send(
            build_message(
                cc=["staff@example.com"],
                bcc=["audit@example.com"],
                reply_to="support@example.com",
                headers={"X-Test": "yes"},
                metadata={"reg_id": "CMT-2026-ABC123", "event_id": "evt_123"},
            )
        )

    assert captured["url"] == "https://api.sendgrid.com/v3/mail/send"
    assert captured["authorization"] == "Bearer SG.test"
    assert captured["body"] == {
        "personalizations": [
            {
                "to": [{"email": "amina@example.com"}],
                "cc": [{"email": "staff@example.com"}],
                "bcc": [{"email": "audit@example.com"}],
                "headers": {"X-Test": "yes"},
                "custom_args": {"reg_id": "CMT-2026-ABC123", "event_id": "evt_123"},
            }
        ],
        "from": {"email": "noreply@eventapp.local", "name": "Event Management"},
        "subject": "Your ticket for Community Meetup 2026",
        "content": [
            {"type": "text/plain", "value": "Ticket details"},
            {"type": "text/html", "value": "<p>Ticket details</p>"},
        ],
        "reply_to": {"email": "support@example.com"},
    }
    assert result.provider == "sendgrid"
    assert result.external_id == "sg_123"


@pytest.mark.asyncio
async def test_mailgun_provider_uses_documented_messages_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = parse_qs(request.content.decode())
        return httpx.Response(200, json={"id": "<20260515120000.1.1234567890@sandbox.mailgun.org>"})

    settings = build_settings(
        EMAIL_PROVIDER="mailgun",
        MAILGUN_API_KEY="key-test",
        MAILGUN_DOMAIN="sandbox.mailgun.org",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MailgunEmailProvider(settings, client=client)
        result = await provider.send(
            build_message(
                cc=["staff@example.com"],
                bcc=["audit@example.com"],
                reply_to="support@example.com",
                headers={"X-Ticket": "yes"},
                metadata={"reg_id": "CMT-2026-ABC123"},
            )
        )

    assert captured["url"] == "https://api.mailgun.net/v3/sandbox.mailgun.org/messages"
    assert str(captured["authorization"]).startswith("Basic ")
    assert captured["body"] == {
        "from": ["Event Management <noreply@eventapp.local>"],
        "to": ["amina@example.com"],
        "subject": ["Your ticket for Community Meetup 2026"],
        "text": ["Ticket details"],
        "html": ["<p>Ticket details</p>"],
        "cc": ["staff@example.com"],
        "bcc": ["audit@example.com"],
        "h:Reply-To": ["support@example.com"],
        "h:X-Ticket": ["yes"],
        "v:reg_id": ["CMT-2026-ABC123"],
    }
    assert result.provider == "mailgun"
    assert result.external_id == "<20260515120000.1.1234567890@sandbox.mailgun.org>"


@pytest.mark.asyncio
async def test_zoho_mail_provider_uses_documented_send_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": {"code": 200}})

    settings = build_settings(
        EMAIL_PROVIDER="zoho_mail",
        ZOHO_MAIL_ACCESS_TOKEN="zoho_token",
        ZOHO_MAIL_ACCOUNT_ID="123456789",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ZohoMailProvider(settings, client=client)
        result = await provider.send(build_message())

    assert captured["url"] == "https://mail.zoho.com/api/accounts/123456789/messages"
    assert captured["authorization"] == "Zoho-oauthtoken zoho_token"
    assert captured["body"] == {
        "fromAddress": "noreply@eventapp.local",
        "toAddress": "amina@example.com",
        "subject": "Your ticket for Community Meetup 2026",
        "content": "<p>Ticket details</p>",
        "mailFormat": "html",
    }
    assert result.provider == "zoho_mail"
    assert result.external_id is None


@pytest.mark.asyncio
async def test_zoho_mail_provider_rejects_multiple_primary_recipients() -> None:
    provider = ZohoMailProvider(
        build_settings(
            EMAIL_PROVIDER="zoho_mail",
            ZOHO_MAIL_ACCESS_TOKEN="zoho_token",
            ZOHO_MAIL_ACCOUNT_ID="123456789",
        )
    )

    with pytest.raises(EmailDeliveryError, match="supports one recipient per field"):
        await provider.send(build_message(to=["amina@example.com", "fatima@example.com"]))


@pytest.mark.asyncio
async def test_amazon_ses_provider_uses_documented_send_email_contract() -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def send_email(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"MessageId": "ses_123"}

        def close(self) -> None:
            captured["closed"] = True

    provider = AmazonSesEmailProvider(
        build_settings(
            EMAIL_PROVIDER="amazon_ses",
            AWS_SES_REGION="us-east-1",
        )
    )
    provider._build_client = lambda: FakeClient()  # type: ignore[method-assign]

    result = await provider.send(
        build_message(
            cc=["staff@example.com"],
            bcc=["audit@example.com"],
            reply_to="support@example.com",
            metadata={"reg_id": "CMT-2026-ABC123"},
        )
    )

    assert captured["kwargs"] == {
        "FromEmailAddress": "noreply@eventapp.local",
        "Destination": {
            "ToAddresses": ["amina@example.com"],
            "CcAddresses": ["staff@example.com"],
            "BccAddresses": ["audit@example.com"],
        },
        "ReplyToAddresses": ["support@example.com"],
        "Content": {
            "Simple": {
                "Subject": {"Data": "Your ticket for Community Meetup 2026", "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": "Ticket details", "Charset": "UTF-8"},
                    "Html": {"Data": "<p>Ticket details</p>", "Charset": "UTF-8"},
                },
            }
        },
        "EmailTags": [{"Name": "reg_id", "Value": "CMT-2026-ABC123"}],
    }
    assert captured["closed"] is True
    assert result.provider == "amazon_ses"
    assert result.external_id == "ses_123"


@pytest.mark.asyncio
async def test_send_email_task_uses_mock_provider_for_actual_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    get_settings.cache_clear()
    message = build_message()

    try:
        result = await _send_email(message.model_dump(mode="json"))

        assert result == {
            "provider": "mock",
            "external_id": None,
            "to": ["amina@example.com"],
            "subject": "Your ticket for Community Meetup 2026",
            "provider_attempts": [
                {
                    "provider": "mock",
                    "provider_attempt": 1,
                    "success": True,
                    "error_class": None,
                    "error_message": None,
                    "attempted_at": result["provider_attempts"][0]["attempted_at"],
                }
            ],
        }
        assert get_mock_outbox() == [message.model_dump(mode="json")]
    finally:
        if "EMAIL_PROVIDER" in os.environ:
            del os.environ["EMAIL_PROVIDER"]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_email_service_fails_over_from_resend_to_zoho_after_two_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        EMAIL_PROVIDER="resend",
        EMAIL_PROVIDER_FAILOVER_CHAIN="resend,zoho_mail,sendgrid",
        RESEND_API_KEY="re_test_key",
        ZOHO_MAIL_ACCESS_TOKEN="zoho_token",
        ZOHO_MAIL_ACCOUNT_ID="123456789",
        SENDGRID_API_KEY="SG.test",
    )
    outcomes: dict[str, list[object]] = {
        "resend": [EmailDeliveryError("Resend attempt 1 failed."), EmailDeliveryError("Resend attempt 2 failed.")],
        "zoho_mail": ["zoho_success"],
        "sendgrid": ["sendgrid_success"],
    }

    def fake_build_email_provider(settings: Settings, provider_name: str | None = None):
        assert provider_name is not None
        return FakeEmailProvider(provider_name, outcomes)

    monkeypatch.setattr("app.services.email_service.build_email_provider", fake_build_email_provider)
    service = EmailService(settings=settings)
    message = build_message()

    first_result = await service.send_message(message)
    second_result = await service.send_message(message, previous_attempts=first_result.provider_attempts)
    third_result = await service.send_message(message, previous_attempts=second_result.provider_attempts)

    assert first_result.success is False
    assert first_result.should_retry is True
    assert first_result.provider_attempts[0]["provider"] == "resend"
    assert first_result.provider_attempts[0]["success"] is False
    assert second_result.success is False
    assert second_result.should_retry is True
    assert [attempt["provider"] for attempt in second_result.provider_attempts] == ["resend", "resend"]
    assert third_result.success is True
    assert third_result.send_result is not None
    assert third_result.send_result.provider == "zoho_mail"
    assert [attempt["provider"] for attempt in third_result.provider_attempts] == ["resend", "resend", "zoho_mail"]
    assert third_result.provider_attempts[-1]["success"] is True


@pytest.mark.asyncio
async def test_email_service_fails_over_from_zoho_to_next_available_provider_after_two_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        EMAIL_PROVIDER="resend",
        EMAIL_PROVIDER_FAILOVER_CHAIN="resend,zoho_mail,sendgrid",
        ZOHO_MAIL_ACCESS_TOKEN="zoho_token",
        ZOHO_MAIL_ACCOUNT_ID="123456789",
        SENDGRID_API_KEY="SG.test",
    )
    outcomes: dict[str, list[object]] = {
        "zoho_mail": [EmailDeliveryError("Zoho attempt 1 failed."), EmailDeliveryError("Zoho attempt 2 failed.")],
        "sendgrid": ["sendgrid_success"],
    }

    def fake_build_email_provider(settings: Settings, provider_name: str | None = None):
        assert provider_name is not None
        return FakeEmailProvider(provider_name, outcomes)

    monkeypatch.setattr("app.services.email_service.build_email_provider", fake_build_email_provider)
    service = EmailService(settings=settings)
    message = build_message()

    first_result = await service.send_message(message)
    second_result = await service.send_message(message, previous_attempts=first_result.provider_attempts)
    third_result = await service.send_message(message, previous_attempts=second_result.provider_attempts)

    assert [attempt["provider"] for attempt in first_result.provider_attempts] == ["zoho_mail"]
    assert [attempt["provider"] for attempt in second_result.provider_attempts] == ["zoho_mail", "zoho_mail"]
    assert third_result.success is True
    assert third_result.send_result is not None
    assert third_result.send_result.provider == "sendgrid"


@pytest.mark.asyncio
async def test_invalid_email_payload_does_not_cascade_through_providers_and_creates_dead_letter(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_PROVIDER_FAILOVER_CHAIN", "resend,zoho_mail")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("ZOHO_MAIL_ACCESS_TOKEN", "zoho_token")
    monkeypatch.setenv("ZOHO_MAIL_ACCOUNT_ID", "123456789")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("build_email_provider should not be called for invalid payloads")

    monkeypatch.setattr("app.services.email_service.build_email_provider", fail_if_called)

    invalid_payload = {
        "from_email": "noreply@eventapp.local",
        "from_name": "Event Management",
        "to": ["not-an-email"],
        "subject": "Broken email",
        "text_body": "This payload should fail validation.",
        "html_body": "<p>This payload should fail validation.</p>",
        "metadata": {"reg_id": "CMT-2026-ABC123"},
    }

    try:
        with pytest.raises(EmailDeliveryError, match="Email payload validation failed."):
            await _send_email(invalid_payload)

        failures = (await db_session.execute(select(AsyncTaskFailure))).scalars().all()
        assert len(failures) == 1
        failure = failures[0]
        assert failure.task_type == AsyncTaskType.EMAIL
        assert failure.failure_category == "message_validation"
        assert failure.provider_attempts == []
        assert failure.error_class == "ValidationError"
        assert failure.payload_metadata == {
            "from_email": "noreply@eventapp.local",
            "from_name": "Event Management",
            "to": ["not-an-email"],
            "cc": [],
            "bcc": [],
            "reply_to": None,
            "subject": "Broken email",
            "metadata": {"reg_id": "CMT-2026-ABC123"},
        }
    finally:
        for key in ("EMAIL_PROVIDER", "EMAIL_PROVIDER_FAILOVER_CHAIN", "RESEND_API_KEY", "ZOHO_MAIL_ACCESS_TOKEN", "ZOHO_MAIL_ACCOUNT_ID"):
            if key in os.environ:
                del os.environ[key]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_message_validation_does_not_fail_over_to_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings(
        EMAIL_PROVIDER="zoho_mail",
        EMAIL_PROVIDER_FAILOVER_CHAIN="zoho_mail,sendgrid",
        ZOHO_MAIL_ACCESS_TOKEN="zoho_token",
        ZOHO_MAIL_ACCOUNT_ID="123456789",
        SENDGRID_API_KEY="SG.test",
    )
    outcomes: dict[str, list[object]] = {
        "sendgrid": ["sendgrid_success"],
    }

    def fake_build_email_provider(settings: Settings, provider_name: str | None = None):
        assert provider_name is not None
        if provider_name == "zoho_mail":
            return ZohoMailProvider(settings)
        return FakeEmailProvider(provider_name, outcomes)

    monkeypatch.setattr("app.services.email_service.build_email_provider", fake_build_email_provider)
    service = EmailService(settings=settings)
    result = await service.send_message(build_message(to=["amina@example.com", "fatima@example.com"]))

    assert result.success is False
    assert result.should_retry is False
    assert result.failure_category == "message_validation"
    assert [attempt["provider"] for attempt in result.provider_attempts] == ["zoho_mail"]
    assert outcomes["sendgrid"] == ["sendgrid_success"]


@pytest.mark.asyncio
async def test_no_configured_real_providers_creates_configuration_dead_letter(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_PROVIDER_FAILOVER_CHAIN", "resend,zoho_mail,sendgrid")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ZOHO_MAIL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ZOHO_MAIL_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)

    try:
        with pytest.raises(EmailDeliveryError, match="No configured real email providers are available for failover."):
            await _send_email(build_message().model_dump(mode="json"))

        failures = (await db_session.execute(select(AsyncTaskFailure))).scalars().all()
        assert len(failures) == 1
        failure = failures[0]
        assert failure.task_type == AsyncTaskType.EMAIL
        assert failure.failure_category == "configuration_failure"
        assert failure.provider_attempts == []
        assert failure.attempt_count == 1
        assert failure.payload_metadata == {
            "from_email": "noreply@eventapp.local",
            "from_name": "Event Management",
            "to": ["amina@example.com"],
            "cc": [],
            "bcc": [],
            "reply_to": None,
            "subject": "Your ticket for Community Meetup 2026",
            "metadata": {"reg_id": "CMT-2026-ABC123"},
        }
    finally:
        for key in (
            "EMAIL_PROVIDER",
            "EMAIL_PROVIDER_FAILOVER_CHAIN",
            "RESEND_API_KEY",
            "ZOHO_MAIL_ACCESS_TOKEN",
            "ZOHO_MAIL_ACCOUNT_ID",
            "SENDGRID_API_KEY",
        ):
            if key in os.environ:
                del os.environ[key]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_terminal_email_chain_failure_creates_single_dead_letter_with_safe_metadata(
    db_session,
    seeded_admin_account: StaffAccount,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = await create_registration_for_dead_letter(db_session, seeded_admin_account)
    get_settings.cache_clear()
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_PROVIDER_FAILOVER_CHAIN", "resend,zoho_mail")
    monkeypatch.setenv("EMAIL_PROVIDER_ATTEMPTS_PER_PROVIDER", "2")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("ZOHO_MAIL_ACCESS_TOKEN", "zoho_token")
    monkeypatch.setenv("ZOHO_MAIL_ACCOUNT_ID", "123456789")

    outcomes: dict[str, list[object]] = {
        "resend": [EmailDeliveryError("Resend attempt 1 failed."), EmailDeliveryError("Resend attempt 2 failed.")],
        "zoho_mail": [EmailDeliveryError("Zoho attempt 1 failed."), EmailDeliveryError("Zoho attempt 2 failed.")],
    }

    def fake_build_email_provider(settings: Settings, provider_name: str | None = None):
        assert provider_name is not None
        return FakeEmailProvider(provider_name, outcomes)

    monkeypatch.setattr("app.services.email_service.build_email_provider", fake_build_email_provider)
    payload = build_message(
        to=[registration.email],
        metadata={"reg_id": registration.reg_id, "event_id": registration.event_id},
    ).model_dump(mode="json")

    try:
        for retry_count in range(4):
            try:
                await _send_email(payload, retry_count=retry_count)
            except EmailRetryRequired as retry_signal:
                payload = retry_signal.payload
                continue
            except EmailDeliveryError as exc:
                assert "Zoho attempt 2 failed." in str(exc)
                break
        else:
            raise AssertionError("Expected terminal email delivery failure.")

        failures = (await db_session.execute(select(AsyncTaskFailure))).scalars().all()
        assert len(failures) == 1
        failure = failures[0]
        assert failure.task_type == AsyncTaskType.EMAIL
        assert failure.registration_id == registration.id
        assert failure.event_id == registration.event_id
        assert failure.attempt_count == 4
        assert [attempt["provider"] for attempt in failure.provider_attempts or []] == [
            "resend",
            "resend",
            "zoho_mail",
            "zoho_mail",
        ]
        assert failure.payload_metadata == {
            "from_email": "noreply@eventapp.local",
            "from_name": "Event Management",
            "to": [registration.email],
            "cc": [],
            "bcc": [],
            "reply_to": None,
            "subject": "Your ticket for Community Meetup 2026",
            "metadata": {"reg_id": registration.reg_id, "event_id": registration.event_id},
        }
    finally:
        for key in (
            "EMAIL_PROVIDER",
            "EMAIL_PROVIDER_FAILOVER_CHAIN",
            "EMAIL_PROVIDER_ATTEMPTS_PER_PROVIDER",
            "RESEND_API_KEY",
            "ZOHO_MAIL_ACCESS_TOKEN",
            "ZOHO_MAIL_ACCOUNT_ID",
        ):
            if key in os.environ:
                del os.environ[key]
        get_settings.cache_clear()
