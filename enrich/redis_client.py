"""Thin redis-py wrapper. The one and only place in this project that talks
to Redis for enrichment data. Hard guardrail: every key this module builds
is prefixed with 'nrd:enrich:' -- it is structurally impossible for a bug
here to touch the flat '<domain> -> registration date' keys that WISE
already depends on, since those keys never carry that prefix.
"""
import json
import logging
import time

import redis

import config
from domain_utils import normalize_domain

log = logging.getLogger("nrd_enrich.redis_client")

_PREFIX = "nrd:enrich:"

_SOURCES = ("dns", "asn", "whois", "crt", "vt")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD,
            socket_timeout=config.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=config.REDIS_SOCKET_TIMEOUT,
            decode_responses=True,
            health_check_interval=30,
        )
    return _client


def _guard(key):
    if not key.startswith(_PREFIX):
        # Defensive: this should be unreachable given the helpers below
        # only ever build keys via enrich_key()/runs_key()/vt_counter_key().
        raise ValueError(f"refusing to touch non-enrichment key: {key!r}")
    return key


def enrich_key(domain):
    return _guard(f"{_PREFIX}{normalize_domain(domain)}")


def runs_key(date, source):
    if source not in _SOURCES:
        raise ValueError(f"unknown source {source!r}")
    return _guard(f"{_PREFIX}runs:{date}:{source}")


def vt_counter_key(date):
    return _guard(f"{_PREFIX}vt:daily_count:{date}")


def init_domain(domain, nrd_date):
    """Idempotent: HSETNX every field so re-running a phase never clobbers
    in-progress or completed work on an earlier field."""
    key = enrich_key(domain)
    client = get_client()
    defaults = {
        "schema_version": "1",
        "nrd_date": nrd_date,
        "dns_status": "not_attempted",
        "asn_status": "not_attempted",
        "whois_status": "not_attempted",
        "whois_attempts": "0",
        "reverse_whois_status": "no_provider_configured",
        "crt_status": "not_attempted",
        "vt_status": "not_attempted",
    }
    pipe = client.pipeline(transaction=True)
    for field, value in defaults.items():
        pipe.hsetnx(key, field, value)
    pipe.execute()
    # Only set an expiry if the key doesn't already have one (first init).
    if client.ttl(key) < 0:
        client.expire(key, config.ENRICH_TTL_DAYS * 86400)


def set_fields(domain, fields):
    """Write a dict of hash fields for one domain. Values are coerced to
    str since redis-py hash fields are strings; None values are skipped."""
    key = enrich_key(domain)
    clean = {k: v for k, v in fields.items() if v is not None}
    if not clean:
        return
    get_client().hset(key, mapping={k: str(v) for k, v in clean.items()})


def get_hash(domain):
    return get_client().hgetall(enrich_key(domain))


def hmget_fields(domain, fields):
    """Fetch a handful of fields without pulling the whole hash. Returns a
    dict with only the fields that had a value set."""
    key = enrich_key(domain)
    values = get_client().hmget(key, fields)
    return {f: v for f, v in zip(fields, values) if v is not None}


def get_status(domain, source):
    if source not in _SOURCES:
        raise ValueError(f"unknown source {source!r}")
    return get_client().hget(enrich_key(domain), f"{source}_status")


def bump_whois_attempts(domain):
    key = enrich_key(domain)
    return get_client().hincrby(key, "whois_attempts", 1)


def record_run_summary(date, source, counters, started_at, finished_at):
    key = runs_key(date, source)
    payload = dict(counters)
    payload["started_at"] = started_at
    payload["finished_at"] = finished_at
    payload["duration_seconds"] = round(finished_at - started_at, 2)
    client = get_client()
    client.hset(key, mapping={k: str(v) for k, v in payload.items()})
    client.expire(key, config.RUN_SUMMARY_TTL_DAYS * 86400)
    log.info("run summary %s/%s: %s", date, source, json.dumps(payload, default=str))


def incr_vt_daily_count(date, by=1):
    key = vt_counter_key(date)
    client = get_client()
    new_value = client.incrby(key, by)
    if new_value == by:
        client.expire(key, config.VT_COUNTER_TTL_DAYS * 86400)
    return new_value


def get_vt_daily_count(date):
    raw = get_client().get(vt_counter_key(date))
    return int(raw) if raw is not None else 0


def wait_for_redis(max_wait_seconds=60):
    """Small connect-retry helper for startup ordering against the nrd
    container (compose depends_on doesn't guarantee redis is *ready*, only
    that the container has started)."""
    deadline = time.monotonic() + max_wait_seconds
    last_exc = None
    while time.monotonic() < deadline:
        try:
            get_client().ping()
            return
        except redis.exceptions.RedisError as exc:
            last_exc = exc
            time.sleep(2)
    raise RuntimeError(f"redis not reachable after {max_wait_seconds}s: {last_exc}")
