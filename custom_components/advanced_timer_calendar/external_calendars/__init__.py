"""External calendar providers package."""
from __future__ import annotations
from .microsoft import MicrosoftCalendarProvider
from .google import GoogleCalendarProvider
from .apple import AppleCalendarProvider

PROVIDERS = {
    "microsoft": MicrosoftCalendarProvider,
    "google": GoogleCalendarProvider,
    "apple": AppleCalendarProvider,
}


def get_provider(provider_type: str):
    """Return the provider class for the given provider type."""
    return PROVIDERS.get(provider_type)
