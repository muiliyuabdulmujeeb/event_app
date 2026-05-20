from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError, EmailMessageValidationError
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("zoho_mail", "zoho")
class ZohoMailProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.settings.zoho_mail_access_token:
            raise EmailConfigurationError(
                "ZOHO_MAIL_ACCESS_TOKEN must be configured when EMAIL_PROVIDER=zoho_mail."
            )
        if not self.settings.zoho_mail_account_id:
            raise EmailConfigurationError(
                "ZOHO_MAIL_ACCOUNT_ID must be configured when EMAIL_PROVIDER=zoho_mail."
            )
        self._validate_single_recipient(message)

        body: dict[str, Any] = {
            "fromAddress": message.from_email,
            "toAddress": message.to[0],
            "subject": message.subject,
            "content": message.html_body or message.text_body,
            "mailFormat": "html" if message.html_body else "plaintext",
        }
        if message.cc:
            body["ccAddress"] = message.cc[0]
        if message.bcc:
            body["bccAddress"] = message.bcc[0]
        if message.reply_to:
            body["replyTo"] = message.reply_to

        await self._post_json(
            f"{self.settings.zoho_mail_api_base_url.rstrip('/')}/api/accounts/{self.settings.zoho_mail_account_id}/messages",
            headers={
                "Authorization": f"Zoho-oauthtoken {self.settings.zoho_mail_access_token}",
                "Content-Type": "application/json",
            },
            json_body=body,
        )
        return EmailSendResult(provider="zoho_mail")

    def _validate_single_recipient(self, message: EmailMessage) -> None:
        if len(message.to) != 1 or len(message.cc) > 1 or len(message.bcc) > 1:
            raise EmailMessageValidationError(
                "Zoho Mail provider supports one recipient per field in this implementation."
            )

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
            raise EmailDeliveryError("Could not reach Zoho Mail to deliver email.") from exc

        if response.status_code >= 400:
            raise EmailDeliveryError(self._extract_gateway_message(response, "Zoho Mail email delivery failed."))

        try:
            return response.json()
        except ValueError:
            return {}

    def _extract_gateway_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        data = payload.get("data")
        if isinstance(data, dict):
            message = data.get("message")
            if message:
                return str(message)
        return fallback
