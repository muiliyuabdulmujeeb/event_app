from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("resend")
class ResendEmailProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.settings.resend_api_key:
            raise EmailConfigurationError("RESEND_API_KEY must be configured when EMAIL_PROVIDER=resend.")

        body: dict[str, Any] = {
            "from": self._format_from_header(message),
            "to": message.to,
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body:
            body["html"] = message.html_body
        if message.cc:
            body["cc"] = message.cc
        if message.bcc:
            body["bcc"] = message.bcc
        if message.reply_to:
            body["reply_to"] = message.reply_to
        if message.headers:
            body["headers"] = message.headers
        if message.metadata:
            body["tags"] = [{"name": key, "value": str(value)} for key, value in message.metadata.items()]

        response_data = await self._post_json(
            f"{self.settings.resend_api_base_url.rstrip('/')}/emails",
            headers={
                "Authorization": f"Bearer {self.settings.resend_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "event-manager/0.1",
            },
            json_body=body,
        )
        external_id = response_data.get("id")
        return EmailSendResult(provider="resend", external_id=str(external_id) if external_id else None)

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=json_body)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Could not reach Resend to deliver email.") from exc

        if response.status_code >= 400:
            raise EmailDeliveryError(self._extract_gateway_message(response, "Resend email delivery failed."))

        try:
            return response.json()
        except ValueError as exc:
            raise EmailDeliveryError("Resend returned a non-JSON response.") from exc

    def _extract_gateway_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        message = payload.get("message")
        return str(message) if message else fallback

    def _format_from_header(self, message: EmailMessage) -> str:
        if message.from_name:
            return f"{message.from_name} <{message.from_email}>"
        return message.from_email

