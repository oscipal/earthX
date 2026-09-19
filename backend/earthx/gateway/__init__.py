"""The only way out.

`gateway` decides whether a URL may be fetched, and it is the only module that
fetches (architekturplan.md 6.5, KLAERUNGEN B8). It knows nothing about
datasets: the allowlist and the limits are handed in as a :class:`Policy`.

This first part carries the rules that work without a network. The HTTP client
and the GDAL configuration follow in M1-03b and M1-03c.
"""

from earthx.gateway.checks import CheckedUrl, check_url
from earthx.gateway.errors import AddressRejected, GatewayError, UrlRejected, UrlTooLong
from earthx.gateway.policy import ALLOWED_HOSTS_ENV, Policy, normalize_host, policy_from_env

__all__ = [
    "ALLOWED_HOSTS_ENV",
    "AddressRejected",
    "CheckedUrl",
    "GatewayError",
    "Policy",
    "UrlRejected",
    "UrlTooLong",
    "check_url",
    "normalize_host",
    "policy_from_env",
]
