from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.schemas.email import EmailMessage
from app.services.email_providers import EmailSendResult, build_email_provider


@dataclass
class EmailService:
    settings: Settings

    async def send_message(self, message: EmailMessage) -> EmailSendResult:
        provider = build_email_provider(self.settings)
        return await provider.send(message)

    def enqueue_message(self, message: EmailMessage) -> None:
        from app.workers.email_tasks import send_email_task

        send_email_task.delay(message.model_dump(mode="json"))

    def enqueue_messages(self, messages: list[EmailMessage]) -> None:
        for message in messages:
            self.enqueue_message(message)
