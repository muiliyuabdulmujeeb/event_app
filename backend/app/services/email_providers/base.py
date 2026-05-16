from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.schemas.email import EmailMessage


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    external_id: str | None = None


class EmailProvider(Protocol):
    provider_name: str

    def __init__(self, settings: Settings) -> None: ...

    async def send(self, message: EmailMessage) -> EmailSendResult: ...


_PROVIDER_REGISTRY: dict[str, type[EmailProvider]] = {}


def register_email_provider(*names: str):
    def decorator(provider_cls: type[EmailProvider]) -> type[EmailProvider]:
        for name in names:
            _PROVIDER_REGISTRY[name.lower()] = provider_cls
        provider_cls.provider_name = names[0].lower()
        return provider_cls

    return decorator


def get_registered_provider(provider_name: str) -> type[EmailProvider] | None:
    return _PROVIDER_REGISTRY.get(provider_name.lower())


def list_registered_providers() -> dict[str, type[EmailProvider]]:
    return dict(_PROVIDER_REGISTRY)

