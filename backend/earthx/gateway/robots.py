"""``robots.txt`` after RFC 9309: read the rules, answer whether a path may be fetched.

Pure parsing, no network: the client fetches the file and asks :class:`RobotsRules`
(M5-18 §3.3). The group for our own product token wins over ``*``; within the
group the longest matching rule decides, ``Allow`` on a tie; ``*`` and ``$`` work
in paths. ``Crawl-delay`` is not part of RFC 9309, but is read as a courtesy
(M5-18 F5).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from urllib.parse import quote

# RFC 9309 §2.5: a crawler must parse at least the first 500 KiB.
MAX_ROBOTS_BYTES = 500 * 1024
ROBOTS_PATH = "/robots.txt"

_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
# Everything printable in ASCII stays as written; the rest is percent-encoded (RFC 9309 §2.2.2).
_SAFE = "".join(chr(code) for code in range(33, 127) if chr(code) != "%")


def _normalize(text: str) -> str:
    encoded = quote(text, safe=_SAFE + "%")
    return _PERCENT.sub(lambda match: match.group(0).upper(), encoded)


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]

    @classmethod
    def build(cls, allow: bool, raw: str) -> _Rule:
        pattern = _normalize(raw)
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*")) + ("$" if anchored else "")
        return cls(allow=allow, pattern=pattern, regex=re.compile(regex))


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None


@dataclass(frozen=True)
class RobotsRules:
    """The rules that apply to one product token on one host."""

    rules: tuple[_Rule, ...] = ()
    crawl_delay: float | None = None

    @classmethod
    def allow_all(cls) -> RobotsRules:
        return cls()

    @classmethod
    def parse(cls, content: bytes, product: str) -> RobotsRules:
        """The rules for ``product`` (case-insensitive), else for ``*``, else none."""
        text = content[:MAX_ROBOTS_BYTES].decode("utf-8", errors="replace")
        groups: list[_Group] = []
        current: _Group | None = None
        in_agents = False
        for line in text.splitlines():
            key, sep, value = line.split("#", 1)[0].partition(":")
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not in_agents:
                    current = _Group()
                    groups.append(current)
                current.agents.append(value.lower())
                in_agents = True
                continue
            in_agents = False
            if current is None:
                continue
            if key in {"allow", "disallow"} and value:
                current.rules.append(_Rule.build(key == "allow", value))
            elif key == "crawl-delay":
                current.crawl_delay = _delay(value, current.crawl_delay)

        token = product.lower()
        chosen = [group for group in groups if token in group.agents]
        if not chosen:
            chosen = [group for group in groups if "*" in group.agents]
        delays = [group.crawl_delay for group in chosen if group.crawl_delay is not None]
        return cls(
            rules=tuple(rule for group in chosen for rule in group.rules),
            crawl_delay=max(delays) if delays else None,
        )

    def allows(self, path_and_query: str) -> bool:
        """Whether a path (with its query) may be fetched. ``/robots.txt`` always may."""
        target = _normalize(path_and_query or "/")
        if target == ROBOTS_PATH:
            return True
        best: _Rule | None = None
        for rule in self.rules:
            if not rule.regex.match(target):
                continue
            if best is None or len(rule.pattern) > len(best.pattern):
                best = rule
            elif len(rule.pattern) == len(best.pattern) and rule.allow:
                best = rule
        return best is None or best.allow


def _delay(value: str, previous: float | None) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return previous
    if math.isnan(seconds) or seconds < 0:
        return previous
    return seconds if previous is None else max(previous, seconds)
