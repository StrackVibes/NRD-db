"""DNS record enrichment. Fully free/self-hosted, bulk-safe: bounded
concurrency against a fixed set of public recursive resolvers (not the
LAN's own resolver, so results reflect general internet visibility rather
than local ad-block/DNS-filtering policy).
"""
import asyncio
import datetime
import logging
import time

import dns.asyncresolver
import dns.exception
import dns.resolver

import config
import redis_client
from time_budget import TimeBudget

log = logging.getLogger("nrd_enrich.dns")

_RECORD_TYPES = ("A", "AAAA", "NS", "MX")
_MAX_VALUES_STORED = 20


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_resolver():
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = config.DNS_RESOLVERS
    resolver.timeout = config.DNS_TIMEOUT_SECONDS
    resolver.lifetime = config.DNS_LIFETIME_SECONDS
    return resolver


async def _resolve_one(resolver, domain, sem):
    async with sem:
        fields = {"dns_checked_at": _now_iso()}
        got_any = False
        domain_exists = None
        last_error = None

        for rtype in _RECORD_TYPES:
            try:
                answer = await resolver.resolve(domain, rtype, raise_on_no_answer=False)
                domain_exists = True
                if answer.rrset is not None:
                    values = [r.to_text().rstrip(".") for r in answer.rrset][:_MAX_VALUES_STORED]
                    fields[f"dns_{rtype.lower()}"] = ",".join(values)
                    got_any = True
            except dns.resolver.NXDOMAIN:
                domain_exists = False
                break  # domain doesn't exist at all; other record types can't help
            except dns.resolver.NoNameservers:
                last_error = "error"
            except dns.exception.Timeout:
                last_error = "timeout"
            except Exception as exc:  # noqa: BLE001 - never let one bad answer kill the batch
                log.debug("dns lookup error for %s/%s: %s", domain, rtype, exc)
                last_error = "error"

        if got_any or domain_exists is True:
            status = "ok"
        elif domain_exists is False:
            status = "nxdomain"
        else:
            status = last_error or "error"

        fields["dns_status"] = status
        return domain, fields


async def _drain(tasks, counters, ip_map):
    for coro in asyncio.as_completed(tasks):
        domain, fields = await coro
        counters["attempted"] = counters.get("attempted", 0) + 1
        if fields.get("dns_status") in ("ok", "nxdomain"):
            counters["ok"] = counters.get("ok", 0) + 1
        else:
            counters["errors"] = counters.get("errors", 0) + 1
        redis_client.set_fields(domain, fields)

        ips = []
        for key in ("dns_a", "dns_aaaa"):
            if fields.get(key):
                ips.extend(v for v in fields[key].split(",") if v)
        if ips:
            ip_map[domain] = ips


async def _run_async(domains, budget, counters, ip_map):
    resolver = _make_resolver()
    sem = asyncio.Semaphore(config.DNS_CONCURRENCY)
    chunk = []
    for domain in domains:
        if budget.expired:
            counters["budget_exhausted"] = counters.get("budget_exhausted", 0) + 1
            continue
        chunk.append(asyncio.create_task(_resolve_one(resolver, domain, sem)))
        if len(chunk) >= config.DNS_CONCURRENCY * 20:
            await _drain(chunk, counters, ip_map)
            chunk = []
    if chunk:
        await _drain(chunk, counters, ip_map)


def run(domains, catchup_only=False, date=None):
    """domains: iterable of already-normalized domain strings.
    If catchup_only, skip anything not currently dns_status=not_attempted.
    Returns (counters, ip_map) where ip_map is {domain: [ip, ...]} for every
    domain that resolved -- fed directly into asn_enrich.run() by the
    orchestrator so the ASN phase never has to re-read Redis to find IPs."""
    counters = {"attempted": 0, "ok": 0, "errors": 0, "budget_exhausted": 0, "skipped_already_done": 0}
    budget = TimeBudget(config.DNS_TIME_BUDGET_SECONDS)
    ip_map = {}
    started_at = time.time()

    def _filtered():
        for domain in domains:
            if catchup_only:
                status = redis_client.get_status(domain, "dns")
                if status not in (None, "not_attempted"):
                    counters["skipped_already_done"] += 1
                    continue
            yield domain

    asyncio.run(_run_async(_filtered(), budget, counters, ip_map))

    finished_at = time.time()
    if date:
        redis_client.record_run_summary(date, "dns", counters, started_at, finished_at)
    return counters, ip_map
