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
    HostResting,
    ResponseTooLarge,
    RobotsDisallowed,
    TooManyRedirects,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnreachable,
    UrlRejected,
    UrlTooLong,
)
from earthx.gateway.pacer import OVERVIEW_HOST_INTERVAL_ENV, HostPacer, overview_interval_from_env
from earthx.gateway.policy import (
    ALLOWED_HOSTS_ENV,
    DEFAULT_USER_AGENT,
    USER_AGENT_ENV,
    Policy,
    UrlParts,
    host_of,
    inspect_url,
    normalize_host,
    policy_from_env,
    user_agent_from_env,
)
from earthx.gateway.resolver import CachingResolver, Resolver, resolve_host
from earthx.gateway.robots import RobotsRules
from earthx.gateway.slots import ReadSlots

__all__ = [
    "ALLOWED_HOSTS_ENV",
    "DEFAULT_USER_AGENT",
    "OVERVIEW_HOST_INTERVAL_ENV",
    "USER_AGENT_ENV",
    "AddressRejected",
    "CachingResolver",
    "CheckedUrl",
    "Gateway",
    "GatewayError",
    "GatewayResponse",
    "HostPacer",
    "HostResting",
    "Policy",
    "ReadSlots",
    "Resolver",
    "ResponseTooLarge",
    "RobotsDisallowed",
    "RobotsRules",
    "TooManyRedirects",
    "UpstreamError",
    "UpstreamTimeout",
    "UpstreamUnreachable",
    "UrlParts",
    "UrlRejected",
    "UrlTooLong",
    "check_url",
    "host_of",
    "inspect_url",
    "normalize_host",
    "overview_interval_from_env",
    "policy_from_env",
    "resolve_host",
    "user_agent_from_env",
]
