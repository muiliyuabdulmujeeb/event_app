from __future__ import annotations

from app.core.config import Settings
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


MOCK_EMAIL_OUTBOX: list[dict] = []


def clear_mock_outbox() -> None:
    MOCK_EMAIL_OUTBOX.clear()


def get_mock_outbox() -> list[dict]:
    return list(MOCK_EMAIL_OUTBOX)


@register_email_provider("mock")
class MockEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, message: EmailMessage) -> EmailSendResult:
        MOCK_EMAIL_OUTBOX.append(message.model_dump(mode="json"))
        return EmailSendResult(provider="mock")

