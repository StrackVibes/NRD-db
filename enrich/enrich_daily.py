#!/usr/bin/env python3
"""Orchestrator for the main daily enrichment pass: initializes each new
domain's hash, then runs DNS -> ASN -> crt.sh in sequence. One source
failing doesn't block the others -- each is wrapped independently.

Usage:
    enrich_daily.py [--date YYYY-MM-DD] [--phase all|dns|asn|crt]
                     [--catchup] [--limit N] [--input FILE] [--dry-run]

--catchup only applies to the dns phase: re-attempt domains still
dns_status=not_attempted for the given date, instead of every domain.
"""
import argparse
import datetime
import logging
import sys

import config
import redis_client
from daily_files import iter_daily_domains
from domain_utils import try_normalize_domain
from sources import asn_enrich, crt_enrich, dns_enrich

log = logging.getLogger("nrd_enrich.enrich_daily")


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _load_domains_from_input(path, limit=None):
    domains = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            token = raw.split()[0]
            domain, err = try_normalize_domain(token)
            if domain is None:
                log.debug("skipping invalid domain in --input: %s (%s)", token, err)
                continue
            domains.append(domain)
            if limit and len(domains) >= limit:
                break
    return domains


def _ip_map_from_redis(domains):
    """Fallback used when the asn phase is invoked standalone (e.g. manual
    verification) without a dns phase having just populated ip_map
    in-memory in this same process."""
    ip_map = {}
    for domain in domains:
        fields = redis_client.hmget_fields(domain, ["dns_a", "dns_aaaa"])
        ips = []
        for key in ("dns_a", "dns_aaaa"):
            if fields.get(key):
                ips.extend(v for v in fields[key].split(",") if v)
        if ips:
            ip_map[domain] = ips
    return ip_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="NRD date to process (default: today UTC)")
    parser.add_argument("--phase", choices=["all", "dns", "asn", "crt"], default="all")
    parser.add_argument("--catchup", action="store_true", help="dns phase only: re-attempt not_attempted domains")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of domains processed")
    parser.add_argument("--input", default=None, help="read domains from this file instead of the daily NRD file")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config.validate()

    date = args.date or _today()

    if args.input:
        domains = _load_domains_from_input(args.input, limit=args.limit)
    else:
        domains = list(iter_daily_domains(date, limit=args.limit))

    log.info("loaded %d domains for date=%s phase=%s catchup=%s dry_run=%s", len(domains), date, args.phase, args.catchup, args.dry_run)

    if args.dry_run:
        for domain in domains[:20]:
            print(domain)
        if len(domains) > 20:
            print(f"... and {len(domains) - 20} more")
        return 0

    if not domains:
        log.warning("no domains to process, exiting")
        return 0

    redis_client.wait_for_redis()

    if args.phase in ("all", "dns", "asn", "crt"):
        for domain in domains:
            redis_client.init_domain(domain, date)

    ip_map = {}
    if args.phase in ("all", "dns"):
        try:
            dns_counters, ip_map = dns_enrich.run(domains, catchup_only=args.catchup, date=date)
            log.info("dns phase: %s", dns_counters)
        except Exception:
            log.exception("dns phase failed")

    if args.phase in ("all", "asn"):
        try:
            if not ip_map:
                ip_map = _ip_map_from_redis(domains)
            asn_counters = asn_enrich.run(ip_map, date=date)
            log.info("asn phase: %s", asn_counters)
        except Exception:
            log.exception("asn phase failed")

    if args.phase in ("all", "crt"):
        try:
            crt_counters = crt_enrich.run(domains, date=date)
            log.info("crt phase: %s", crt_counters)
        except Exception:
            log.exception("crt phase failed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
