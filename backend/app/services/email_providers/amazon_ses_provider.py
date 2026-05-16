from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError, EmailDeliveryError
from app.schemas.email import EmailMessage
from app.services.email_providers.base import EmailSendResult, register_email_provider


@register_email_provider("amazon_ses", "ses")
class AmazonSesEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.settings.aws_ses_region:
            raise EmailConfigurationError("AWS_SES_REGION must be configured when EMAIL_PROVIDER=amazon_ses.")

        client = self._build_client()
        try:
            response = await asyncio.to_thread(
                client.send_email,
                FromEmailAddress=message.from_email,
                Destination={
                    "ToAddresses": message.to,
                    **({"CcAddresses": message.cc} if message.cc else {}),
                    **({"BccAddresses": message.bcc} if message.bcc else {}),
                },
                ReplyToAddresses=[message.reply_to] if message.reply_to else [],
                Content={
                    "Simple": {
                        "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                        "Body": {
                            "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                            **(
                                {"Html": {"Data": message.html_body, "Charset": "UTF-8"}}
                                if message.html_body
                                else {}
                            ),
                        },
                    }
                },
                EmailTags=[
                    {"Name": key, "Value": str(value)}
                    for key, value in message.metadata.items()
                ],
            )
        except (BotoCoreError, ClientError) as exc:
            raise EmailDeliveryError("Amazon SES email delivery failed.") from exc
        finally:
            client.close()

        return EmailSendResult(
            provider="amazon_ses",
            external_id=response.get("MessageId"),
        )

    def _build_client(self):
        session = boto3.session.Session(
            aws_access_key_id=self.settings.aws_ses_access_key_id or None,
            aws_secret_access_key=self.settings.aws_ses_secret_access_key or None,
            aws_session_token=self.settings.aws_ses_session_token or None,
            region_name=self.settings.aws_ses_region or None,
        )
        return session.client(
            "sesv2",
            endpoint_url=self.settings.aws_ses_endpoint_url or None,
        )
