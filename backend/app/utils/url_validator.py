"""
Repository URL Validation for SSRF Prevention

This module provides URL validation for repository ingestion endpoints
to prevent Server-Side Request Forgery (SSRF) attacks.

Features:
- Domain allowlisting (github.com, gitlab.com, etc.)
- IP range blocking (private IPs, metadata endpoints)
- Hostname resolution and IP validation
- Protocol validation (HTTPS only for production)

Related files:
- app/config/settings.py: Configuration for allowed domains and blocked ranges
- app/modules/resources/logic/repo_ingestion.py: Repository ingestion service
"""

import logging
import ipaddress
from typing import Tuple

from ..config.settings import get_settings

logger = logging.getLogger(__name__)


# Default allowed domains for repository URLs
DEFAULT_ALLOWED_DOMAINS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "sourceforge.net",
    "codeberg.org",
    "sr.ht",
]

# Default blocked IP ranges (private and reserved)
DEFAULT_BLOCKED_IP_RANGES = [
    # Loopback
    "127.0.0.0/8",
    "::1/128",
    # Private networks (RFC 1918)
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    # Link-local
    "169.254.0.0/16",
    "fe80::/10",
    # Docker/Kubernetes
    "172.17.0.0/16",  # Docker bridge
    "10.244.0.0/16",  # Kubernetes pods
    "10.96.0.0/12",  # Kubernetes services
    # Cloud metadata endpoints
    "169.254.169.254/32",  # AWS, GCP, Azure
    "metadata.google.internal",  # GCP
    # Multicast
    "224.0.0.0/4",
    "ff00::/8",
]


def validate_repository_url(url: str) -> Tuple[bool, str]:
    """
    Validate a repository URL for SSRF prevention.

    This function validates that:
    1. The URL uses HTTPS (required for production)
    2. The domain is in the allowed list
    3. The resolved IP address is not in a blocked range

    Args:
        url: The repository URL to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str)

    Examples:
        >>> validate_repository_url("https://github.com/user/repo")
        (True, "")

        >>> validate_repository_url("http://github.com/user/repo")  # HTTP not allowed
        (False, "Repository URL must use HTTPS")

        >>> validate_repository_url("https://evil.com/user/repo")  # Not in allowed list
        (False, "Domain 'evil.com' is not in the allowed list")

        >>> validate_repository_url("https://github.com/user/repo")  # Resolves to private IP
        (False, "Resolved IP address is in a blocked range")
    """
    settings = get_settings()

    # Check for empty URL
    if not url or not url.strip():
        return False, "Repository URL cannot be empty"

    # Check for proper URL format
    if not url.startswith(("https://", "http://")):
        return False, "Repository URL must start with http:// or https://"

    # In production, require HTTPS
    if settings.ENV == "prod":
        if url.startswith("http://"):
            return False, "Repository URL must use HTTPS in production"

    # Parse the URL to get hostname
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    hostname = parsed.hostname
    if not hostname:
        return False, "Could not parse hostname from URL"

    # Get allowed domains from settings or use defaults
    allowed_domains = getattr(settings, "ALLOWED_REPOSITORY_DOMAINS", None)
    if not allowed_domains:
        allowed_domains = DEFAULT_ALLOWED_DOMAINS

    # Check if domain is allowed (exact match or suffix match)
    hostname_lower = hostname.lower()
    is_allowed = False
    for allowed_domain in allowed_domains:
        # Exact match
        if hostname_lower == allowed_domain.lower():
            is_allowed = True
            break
        # Suffix match (e.g., github.com matches *.github.com)
        if hostname_lower.endswith("." + allowed_domain.lower()):
            is_allowed = True
            break

    if not is_allowed:
        return False, f"Domain '{hostname}' is not in the allowed list"

    # Get blocked IP ranges from settings or use defaults
    blocked_ip_ranges = getattr(settings, "BLOCKED_IP_RANGES", None)
    if not blocked_ip_ranges:
        blocked_ip_ranges = DEFAULT_BLOCKED_IP_RANGES

    # Resolve hostname to IP address and check against blocked ranges
    try:
        import socket

        # Use getaddrinfo for both IPv4 and IPv6
        addr_info = socket.getaddrinfo(hostname, None)

        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_address = sockaddr[
                0
            ]  # (host, port) for IPv4, (host, port, flowinfo, scopeid) for IPv6

            # Check if IP is in a blocked range
            for blocked_range in blocked_ip_ranges:
                try:
                    network = ipaddress.ip_network(blocked_range, strict=False)
                    ip = ipaddress.ip_address(ip_address)
                    if ip in network:
                        logger.warning(
                            f"SSRF prevention: Blocked repository URL '{url}' - "
                            f"resolved IP {ip_address} is in blocked range {blocked_range}"
                        )
                        return False, (
                            f"Resolved IP address '{ip_address}' is in a blocked range. "
                            "This may indicate a private network or metadata endpoint."
                        )
                except ValueError:
                    # Invalid IP range format, skip
                    continue

    except socket.gaierror as e:
        logger.warning(f"Could not resolve hostname '{hostname}': {e}")
        return False, f"Could not resolve hostname '{hostname}': {e}"
    except Exception as e:
        logger.error(f"Error validating repository URL '{url}': {e}")
        return False, f"Error validating repository URL: {e}"

    # All checks passed
    logger.info(f"Repository URL validated: {url}")
    return True, ""


def is_url_allowed(url: str) -> bool:
    """
    Quick check if a URL is allowed (returns True/False without error message).

    Args:
        url: The repository URL to check

    Returns:
        True if the URL is valid and allowed, False otherwise
    """
    is_valid, _ = validate_repository_url(url)
    return is_valid


def get_allowed_domains() -> list[str]:
    """
    Get the list of allowed domains for repository URLs.

    Returns:
        List of allowed domain strings
    """
    settings = get_settings()
    allowed_domains = getattr(settings, "ALLOWED_REPOSITORY_DOMAINS", None)
    if not allowed_domains:
        allowed_domains = DEFAULT_ALLOWED_DOMAINS
    return allowed_domains


def get_blocked_ip_ranges() -> list[str]:
    """
    Get the list of blocked IP ranges for SSRF prevention.

    Returns:
        List of blocked IP range strings (CIDR notation)
    """
    settings = get_settings()
    blocked_ip_ranges = getattr(settings, "BLOCKED_IP_RANGES", None)
    if not blocked_ip_ranges:
        blocked_ip_ranges = DEFAULT_BLOCKED_IP_RANGES
    return blocked_ip_ranges
