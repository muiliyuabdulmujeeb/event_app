from __future__ import annotations

from importlib import import_module
import pkgutil

from app.core.config import Settings
from app.core.exceptions import EmailConfigurationError
from app.services.email_providers.base import (
    EmailProvider,
    EmailSendResult,
    get_registered_provider,
    list_registered_providers,
)


_DISCOVERED = False


def _discover_providers() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name == "base":
            continue
        import_module(f"{__name__}.{module_info.name}")
    _DISCOVERED = True


def build_email_provider(settings: Settings, provider_name: str | None = None) -> EmailProvider:
    _discover_providers()
    resolved_provider_name = (provider_name or settings.email_provider).strip().lower()
    provider_cls = get_registered_provider(resolved_provider_name)
    if provider_cls is None:
        supported = ", ".join(sorted(list_registered_providers()))
        raise EmailConfigurationError(
            f"EMAIL_PROVIDER '{provider_name or settings.email_provider}' is not supported. Supported providers: {supported}."
        )
    return provider_cls(settings)


__all__ = ["EmailProvider", "EmailSendResult", "build_email_provider"]
