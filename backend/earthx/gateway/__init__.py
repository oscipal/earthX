"""The only way out.

`gateway` decides whether a URL may be fetched, and it is the only module that
fetches (architekturplan.md 6.5, KLAERUNGEN B8). It knows nothing about
datasets: the allowlist and the limits are handed in as a :class:`Policy`.

The GDAL configuration follows in M1-03c.
"""

from earthx.gateway.checks import CheckedUrl, check_url
from earthx.gateway.client import Gateway, GatewayResponse
from earthx.gateway.errors import (
    AddressRejected,
    GatewayError,
    ResponseTooLarge,
    TooManyRedirects,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
    UrlRejected,
    UrlTooLong,
)
from earthx.gateway.policy import ALLOWED_HOSTS_ENV, Policy, host_of, normalize_host, policy_from_env
from earthx.gateway.resolver import CachingResolver, Resolver, resolve_host

__all__ = [
    "ALLOWED_HOSTS_ENV",
    "AddressRejected",
    "CachingResolver",
    "CheckedUrl",
    "Gateway",
    "GatewayError",
    "GatewayResponse",
    "Policy",
    "Resolver",
    "ResponseTooLarge",
    "TooManyRedirects",
    "UpstreamError",
    "UpstreamTimeout",
    "UpstreamUnreachable",
    "UrlRejected",
    "UrlTooLong",
    "check_url",
    "host_of",
    "normalize_host",
    "policy_from_env",
    "resolve_host",
]
