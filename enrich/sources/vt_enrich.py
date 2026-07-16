"""VirusTotal enrichment. Fully optional -- gated on VT_API_KEY. When
absent, this module makes zero network requests; the orchestrator marks
every domain vt_status=no_api_key up front (see redis_client.init_domain)
and this module is effectively a no-op.

When a key is present, enforces a real token-bucket rate limit matched to
VT's public free-tier limits by default (4 req/min, 500/day) so a future
key never gets suspended by over-eager use. Only a small slice of each
day's ~70k-domain cohort can ever be checked on a free tier -- the rest are
left genuinely not_attempted, never marked as an error. Runs as a small
drip (VT_BATCH_PER_RUN per invocation, intended to be cron'd every 15
minutes) rather than one long blocking phase; stops immediately on any 429
without retrying, so a rate-limit response never burns further quota.
"""
import datetime
import logging
import time

import httpx

import config
import redis_client
from daily_files import iter_lookback_domains
from time_budget import TimeBudget

log = logging.getLogger("nrd_enrich.vt")

_API_BASE = "https://www.virustotal.com/api/v3/domains"


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _lookup_one(client, domain):
    url = f"{_API_BASE}/{domain}"
    try:
        resp = client.get(url, headers={"x-apikey": config.VT_API_KEY}, timeout=config.VT_REQUEST_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.HTTPError as exc:
        log.debug("vt request error for %s: %s", domain, exc)
        return None, "error"

    if resp.status_code == 429:
        return None, "rate_limited"
    if resp.status_code == 404:
        # Not yet indexed by VT -- a legitimate, definitive answer for a
        # brand-new domain, not an error.
        return {"vt_malicious": "0", "vt_suspicious": "0", "vt_harmless": "0"}, "ok"
    if resp.status_code != 200:
        return None, "error"

    try:
        data = resp.json()
        stats = data["data"]["attributes"]["last_analysis_stats"]
    except (ValueError, KeyError, TypeError) as exc:
        log.debug("vt response parse error for %s: %s", domain, exc)
        return None, "error"

    fields = {
        "vt_malicious": str(stats.get("malicious", 0)),
        "vt_suspicious": str(stats.get("suspicious", 0)),
        "vt_harmless": str(stats.get("harmless", 0)),
    }
    return fields, "ok"


def _select_candidates(date, limit):
    """Domains that already resolved (dns_status=ok) within the lookback
    window and haven't been VT-checked yet -- a live/parked-but-resolving
    NRD is more actionable to a SOC than one that doesn't resolve at all,
    so it's what the scarce VT quota is spent on first."""
    count = 0
    for domain in iter_lookback_domains(date, config.VT_LOOKBACK_DAYS):
        if count >= limit:
            return
        existing = redis_client.hmget_fields(domain, ["vt_status", "dns_status"])
        if existing.get("vt_status") not in (None, "not_attempted"):
            continue
        if existing.get("dns_status") != "ok":
            continue
        count += 1
        yield domain


def run(date=None):
    date = date or _today()
    counters = {"attempted": 0, "ok": 0, "errors": 0, "rate_limited": 0, "no_api_key": 0}
    started_at = time.time()

    if not config.VT_API_KEY:
        counters["no_api_key"] = 1
        finished_at = time.time()
        redis_client.record_run_summary(date, "vt", counters, started_at, finished_at)
        return counters

    already_used = redis_client.get_vt_daily_count(date)
    remaining_daily = max(0, config.VT_REQ_PER_DAY - already_used)
    batch_limit = min(config.VT_BATCH_PER_RUN, remaining_daily)
    if batch_limit <= 0:
        finished_at = time.time()
        redis_client.record_run_summary(date, "vt", counters, started_at, finished_at)
        return counters

    min_interval = 60.0 / config.VT_REQ_PER_MIN if config.VT_REQ_PER_MIN > 0 else 0.0
    budget = TimeBudget(max(60, int(batch_limit * min_interval * 2) + 30))

    client = httpx.Client()
    try:
        last_request = 0.0
        for domain in _select_candidates(date, batch_limit):
            if budget.expired:
                break
            wait = min_interval - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()

            fields, status = _lookup_one(client, domain)
            counters["attempted"] += 1
            if status == "rate_limited":
                counters["rate_limited"] += 1
                log.warning("VirusTotal returned 429; stopping this drip immediately (no retry, no quota burn)")
                break
            redis_client.incr_vt_daily_count(date)
            if status == "ok":
                fields["vt_status"] = "ok"
                fields["vt_checked_at"] = _now_iso()
                redis_client.set_fields(domain, fields)
                counters["ok"] += 1
            else:
                redis_client.set_fields(domain, {"vt_status": "error", "vt_checked_at": _now_iso()})
                counters["errors"] += 1
    finally:
        client.close()

    finished_at = time.time()
    redis_client.record_run_summary(date, "vt", counters, started_at, finished_at)
    return counters
