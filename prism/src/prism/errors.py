"""
Common error classes for the Prism application.

This module contains provider-agnostic error classes that can be used
across different API providers (Hypixel, Mojang, etc.).
"""


class APIError(ValueError):
    """Exception raised when an API returns an error"""


class APIKeyError(ValueError):
    """Exception raised when an API key is invalid"""


class APIThrottleError(ValueError):
    """Exception raised when we're being throttled by an API"""


class PlayerNotFoundError(ValueError):
    """Exception raised when a player is not found"""
