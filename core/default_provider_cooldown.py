"""Default-provider cooldown policy.

The first provider in the resolved route is the route's default provider.
It is still tracked by ProviderRegistry health, but its cooldown is not used
for provider selection. Fallback providers keep the normal cooldown behavior.

The policy is installed from ``core.__init__`` so all users of the core
translation stack get the same behavior without duplicating route logic in
TranslationManager.
"""

from contextvars import ContextVar
from typing import Optional

from .provider_registry import ProviderRegistry
from .translation_router import TranslationRouter


_current_default_provider: ContextVar[Optional[str]] = ContextVar(
    "exilingo_current_default_provider",
    default=None,
)

_original_resolve = TranslationRouter.resolve
_original_is_in_cooldown = ProviderRegistry.is_in_cooldown


def _resolve_with_default_provider(self, context):
    decision = _original_resolve(self, context)
    default_provider = decision.providers[0] if decision.providers else None
    _current_default_provider.set(default_provider)
    return decision


def _is_in_cooldown_with_default_provider(self, provider_id: str) -> bool:
    if provider_id == _current_default_provider.get():
        return False
    return _original_is_in_cooldown(self, provider_id)


TranslationRouter.resolve = _resolve_with_default_provider
ProviderRegistry.is_in_cooldown = _is_in_cooldown_with_default_provider
