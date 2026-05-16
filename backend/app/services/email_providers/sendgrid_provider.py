from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("sendgrid")
class SendGridEmailProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.settings.sendgrid_api_key:
            raise EmailConfigurationError("SENDGRID_API_KEY must be configured when EMAIL_PROVIDER=sendgrid.")

        body: dict[str, Any] = {
            "personalizations": [
                {
                    "to": [{"email": email} for email in message.to],
                    **({"cc": [{"email": email} for email in message.cc]} if message.cc else {}),
                    **({"bcc": [{"email": email} for email in message.bcc]} if message.bcc else {}),
                    **({"headers": message.headers} if message.headers else {}),
                    **({"custom_args": {key: str(value) for key, value in message.metadata.items()}} if message.metadata else {}),
                }
            ],
            "from": {
                "email": message.from_email,
                **({"name": message.from_name} if message.from_name else {}),
            },
            "subject": message.subject,
            "content": [{"type": "text/plain", "value": message.text_body}],
        }
        if message.html_body:
            body["content"].append({"type": "text/html", "value": message.html_body})
        if message.reply_to:
            body["reply_to"] = {"email": message.reply_to}

        response = await self._post(
            f"{self.settings.sendgrid_api_base_url.rstrip('/')}/v3/mail/send",
            headers={
                "Authorization": f"Bearer {self.settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            },
            json_body=body,
        )
        external_id = response.headers.get("X-Message-Id")
        return EmailSendResult(provider="sendgrid", external_id=external_id)

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any],
    ) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=json_body)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Could not reach SendGrid to deliver email.") from exc

        if response.status_code >= 400:
            raise EmailDeliveryError(self._extract_gateway_message(response, "SendGrid email delivery failed."))
        return response

    def _extract_gateway_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            message = errors[0].get("message")
            if message:
                return str(message)
        return fallback

