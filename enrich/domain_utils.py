"""Single validation/normalization choke point. Every domain string coming
from the NRD feed is attacker/registrant-controlled input. Nothing in this
project may use a domain string for a DNS query, WHOIS/RDAP request, SQL
parameter, URL segment, or Redis key suffix without first passing through
normalize_domain() here. Anything that fails validation is rejected, never
silently passed through.
"""
import re

import idna

_MAX_LENGTH = 253
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class DomainValidationError(ValueError):
    pass


def normalize_domain(raw):
    """Return a normalized, validated, ASCII (punycode) domain string, or
    raise DomainValidationError. Never returns an unvalidated value."""
    if raw is None:
        raise DomainValidationError("empty domain")

    candidate = raw.strip().strip(".").lower()
    if not candidate or len(candidate) > _MAX_LENGTH:
        raise DomainValidationError(f"invalid length: {raw!r}")

    # Reject anything that isn't plausibly a bare hostname before it ever
    # reaches an IDNA/network/SQL/URL call: no whitespace, no path or
    # scheme separators, no shell/SQL metacharacters.
    if any(ch.isspace() for ch in candidate):
        raise DomainValidationError(f"whitespace in domain: {raw!r}")
    if re.search(r"[/\\?#@:;\"'`$&|<>(){}\[\]!*%]", candidate):
        raise DomainValidationError(f"illegal characters in domain: {raw!r}")

    try:
        ascii_domain = idna.encode(candidate, uts46=True).decode("ascii")
    except (idna.IDNAError, UnicodeError) as exc:
        raise DomainValidationError(f"idna encoding failed for {raw!r}: {exc}")

    labels = ascii_domain.split(".")
    if len(labels) < 2:
        raise DomainValidationError(f"not a fully-qualified domain: {raw!r}")
    for label in labels:
        if not _LABEL_RE.match(label):
            raise DomainValidationError(f"invalid label {label!r} in {raw!r}")

    return ascii_domain


def try_normalize_domain(raw):
    """Non-raising variant for hot loops that just want to skip bad rows."""
    try:
        return normalize_domain(raw), None
    except DomainValidationError as exc:
        return None, str(exc)
