from __future__ import annotations

from app.core.config import Settings
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("console")
class ConsoleEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, message: EmailMessage) -> EmailSendResult:
        print(
            "\n".join(
                [
                    "=== EMAIL ===",
                    f"From: {message.from_email}",
                    f"To: {', '.join(message.to)}",
                    f"Subject: {message.subject}",
                    "",
                    message.text_body,
                    "=============",
                ]
            )
        )
        return EmailSendResult(provider="console")

