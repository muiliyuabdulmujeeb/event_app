from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("mailgun")
class MailgunEmailProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.settings.mailgun_api_key:
            raise EmailConfigurationError("MAILGUN_API_KEY must be configured when EMAIL_PROVIDER=mailgun.")
        if not self.settings.mailgun_domain:
            raise EmailConfigurationError("MAILGUN_DOMAIN must be configured when EMAIL_PROVIDER=mailgun.")

        data: dict[str, Any] = {
            "from": self._format_from_header(message),
            "to": message.to,
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body:
            data["html"] = message.html_body
        if message.cc:
            data["cc"] = message.cc
        if message.bcc:
            data["bcc"] = message.bcc
        if message.reply_to:
            data["h:Reply-To"] = message.reply_to
        for header_name, header_value in message.headers.items():
            data[f"h:{header_name}"] = header_value
        for key, value in message.metadata.items():
            data[f"v:{key}"] = str(value)

        response_data = await self._post_form(
            f"{self.settings.mailgun_api_base_url.rstrip('/')}/v3/{self.settings.mailgun_domain}/messages",
            auth=httpx.BasicAuth("api", self.settings.mailgun_api_key),
            data=data,
        )
        external_id = response_data.get("id")
        return EmailSendResult(provider="mailgun", external_id=str(external_id) if external_id else None)

    async def _post_form(
        self,
        url: str,
        *,
        auth: httpx.BasicAuth,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.post(url, auth=auth, data=data)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, auth=auth, data=data)
        except httpx.HTTPError as exc:
            raise EmailDeliveryError("Could not reach Mailgun to deliver email.") from exc

        if response.status_code >= 400:
            raise EmailDeliveryError(self._extract_gateway_message(response, "Mailgun email delivery failed."))

        try:
            return response.json()
        except ValueError as exc:
            raise EmailDeliveryError("Mailgun returned a non-JSON response.") from exc

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

