from __future__ import annotations

import json
import os
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_providers import build_email_provider
from app.services.email_providers.amazon_ses_provider import AmazonSesEmailProvider
from app.services.email_providers.console_provider import ConsoleEmailProvider
from app.services.email_providers.mailgun_provider import MailgunEmailProvider
from app.services.email_providers.mock_provider import MockEmailProvider, get_mock_outbox
from app.services.email_providers.resend_provider import ResendEmailProvider
from app.services.email_providers.sendgrid_provider import SendGridEmailProvider
from app.services.email_providers.zoho_mail_provider import ZohoMailProvider
from app.services.email_service import EmailService
from app.workers.email_tasks import _send_email, send_email_task


def build_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb",
        "TEST_DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/eventdb_test",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET": "changeme",
        "EMAIL_PROVIDER": "mock",
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
        }
        assert get_mock_outbox() == [message.model_dump(mode="json")]
    finally:
        if "EMAIL_PROVIDER" in os.environ:
            del os.environ["EMAIL_PROVIDER"]
        get_settings.cache_clear()


def test_send_email_task_is_configured_for_retries() -> None:
    assert send_email_task.max_retries == 3
    assert send_email_task.autoretry_for == (EmailDeliveryError,)
    assert send_email_task.retry_backoff is True
