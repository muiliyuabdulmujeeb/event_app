from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.exceptions import PaymentConfigurationError, PaymentGatewayError
from app.models.payment import PaymentGateway


SQUAD_PAYMENT_CHANNELS = ["card", "bank", "ussd", "transfer"]


@dataclass(frozen=True)
class PaymentInitializationRequest:
    email: str
    amount: int
    currency: str
    reference: str
    customer_name: str
    callback_url: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PaymentInitializationResult:
    gateway: PaymentGateway
    payment_reference: str
    checkout_url: str


class PaymentProvider(Protocol):
    gateway: PaymentGateway

    async def initialize_payment(
        self,
        payload: PaymentInitializationRequest,
    ) -> PaymentInitializationResult: ...


class MockPaymentProvider:
    gateway = PaymentGateway.MOCK

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def initialize_payment(
        self,
        payload: PaymentInitializationRequest,
    ) -> PaymentInitializationResult:
        checkout_url = f"{self.settings.mock_payment_base_url.rstrip('/')}/mock-payment/pay?ref={payload.reference}"
        return PaymentInitializationResult(
            gateway=self.gateway,
            payment_reference=payload.reference,
            checkout_url=checkout_url,
        )


class PaystackPaymentProvider:
    gateway = PaymentGateway.PAYSTACK

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def initialize_payment(
        self,
        payload: PaymentInitializationRequest,
    ) -> PaymentInitializationResult:
        if not self.settings.paystack_secret_key:
            raise PaymentConfigurationError(
                "PAYSTACK_SECRET_KEY must be configured when ACTIVE_PAYMENT_GATEWAY=paystack."
            )

        body: dict[str, Any] = {
            "email": payload.email,
            "amount": str(payload.amount),
            "reference": payload.reference,
        }
        if payload.callback_url:
            body["callback_url"] = payload.callback_url
        if payload.metadata:
            body["metadata"] = json.dumps(payload.metadata)

        response_data = await self._post_json(
            f"{self.settings.paystack_api_base_url.rstrip('/')}/transaction/initialize",
            headers={
                "Authorization": f"Bearer {self.settings.paystack_secret_key}",
                "Content-Type": "application/json",
            },
            json_body=body,
        )

        try:
            data = response_data["data"]
            checkout_url = str(data["authorization_url"])
            reference = str(data["reference"])
        except (KeyError, TypeError) as exc:
            raise PaymentGatewayError("Paystack returned an invalid initialization response.") from exc

        return PaymentInitializationResult(
            gateway=self.gateway,
            payment_reference=reference,
            checkout_url=checkout_url,
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
            raise PaymentGatewayError("Could not reach Paystack to initialize payment.") from exc

        if response.status_code >= 400:
            raise PaymentGatewayError(self._extract_gateway_message(response, "Paystack payment initialization failed."))

        try:
            return response.json()
        except ValueError as exc:
            raise PaymentGatewayError("Paystack returned a non-JSON initialization response.") from exc

    def _extract_gateway_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        message = payload.get("message")
        return str(message) if message else fallback


class SquadPaymentProvider:
    gateway = PaymentGateway.SQUAD

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def initialize_payment(
        self,
        payload: PaymentInitializationRequest,
    ) -> PaymentInitializationResult:
        if not self.settings.squad_secret_key:
            raise PaymentConfigurationError(
                "SQUAD_SECRET_KEY must be configured when ACTIVE_PAYMENT_GATEWAY=squad."
            )
        if not self.settings.squad_api_base_url:
            raise PaymentConfigurationError(
                "SQUAD_API_BASE_URL must be configured when ACTIVE_PAYMENT_GATEWAY=squad."
            )
        if not payload.callback_url:
            raise PaymentConfigurationError(
                "PAYMENT_CALLBACK_URL must be configured when ACTIVE_PAYMENT_GATEWAY=squad."
            )

        body: dict[str, Any] = {
            "email": payload.email,
            "amount": payload.amount,
            "currency": payload.currency,
            "initiate_type": "inline",
            "transaction_ref": payload.reference,
            "customer_name": payload.customer_name,
            "callback_url": payload.callback_url,
            "payment_channels": list(SQUAD_PAYMENT_CHANNELS),
            "metadata": payload.metadata,
        }

        response_data = await self._post_json(
            f"{self.settings.squad_api_base_url.rstrip('/')}/transaction/initiate",
            headers={
                "Authorization": f"Bearer {self.settings.squad_secret_key}",
                "Content-Type": "application/json",
            },
            json_body=body,
        )

        try:
            data = response_data["data"]
            checkout_url = str(data["checkout_url"])
            reference = str(data["transaction_ref"])
        except (KeyError, TypeError) as exc:
            raise PaymentGatewayError("Squad returned an invalid initialization response.") from exc

        return PaymentInitializationResult(
            gateway=self.gateway,
            payment_reference=reference,
            checkout_url=checkout_url,
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
            raise PaymentGatewayError("Could not reach Squad to initialize payment.") from exc

        if response.status_code >= 400:
            raise PaymentGatewayError(self._extract_gateway_message(response, "Squad payment initialization failed."))

        try:
            return response.json()
        except ValueError as exc:
            raise PaymentGatewayError("Squad returned a non-JSON initialization response.") from exc

    def _extract_gateway_message(self, response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        message = payload.get("message")
        return str(message) if message else fallback
