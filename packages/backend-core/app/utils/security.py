"""Security utilities for data protection and privacy compliance."""

from __future__ import annotations

import hashlib
from typing import Optional
from app.core.config import settings


def hash_ip_address(ip_address: str) -> str:
    """
    Hash an IP address for privacy-compliant storage.

    Uses SHA-256 with a salt to create a one-way hash of IP addresses,
    preventing reconstruction while allowing for rate limiting and abuse detection.

    Args:
        ip_address: Raw IP address string (IPv4 or IPv6)

    Returns:
        Hexadecimal hash string (first 16 characters for storage efficiency)

    Note:
        Requires IP_SALT environment variable to be set for production use.
        Uses empty salt in development (less secure but functional).
    """
    if not ip_address:
        return ""

    # Use configured salt or empty string for development
    salt = settings.ip_salt or ""

    # Create salted hash
    salted_value = f"{ip_address}{salt}".encode('utf-8')
    hash_obj = hashlib.sha256(salted_value)

    # Return first 16 characters (64 bits) - sufficient for uniqueness
    # while being compact for database storage
    return hash_obj.hexdigest()[:16]


def hash_ip_if_present(ip_address: Optional[str]) -> Optional[str]:
    """
    Hash an IP address if present, otherwise return None.

    Convenience wrapper for hash_ip_address that handles None values.

    Args:
        ip_address: Raw IP address string or None

    Returns:
        Hashed IP address or None if input was None
    """
    if ip_address is None:
        return None
    return hash_ip_address(ip_address)
