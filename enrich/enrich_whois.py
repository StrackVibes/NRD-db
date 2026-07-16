#!/usr/bin/env python3
"""Standalone WHOIS/RDAP phase entrypoint. Works a rolling lookback window
across recent daily NRD files (not just today's) since same-day coverage of
the full cohort isn't realistic against free/rate-limited registries -- see
README for the honest partial-coverage caveat.

Usage:
    enrich_whois.py [--date YYYY-MM-DD] [--lookback-days N]
                     [--limit N] [--input FILE] [--dry-run]
"""
import argparse
import datetime
import logging
import sys

import config
import redis_client
from daily_files import iter_lookback_domains
from domain_utils import try_normalize_domain
from sources import whois_enrich

log = logging.getLogger("nrd_enrich.enrich_whois")


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
                continue
            domains.append(domain)
            if limit and len(domains) >= limit:
                break
    return domains


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="end date of the lookback window (default: today UTC)")
    parser.add_argument("--lookback-days", type=int, default=None, help="override config.WHOIS_LOOKBACK_DAYS")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--input", default=None, help="read candidate domains from this file instead of the lookback window")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config.validate()

    date = args.date or _today()
    lookback_days = args.lookback_days or config.WHOIS_LOOKBACK_DAYS

    if args.input:
        domains = _load_domains_from_input(args.input, limit=args.limit)
    else:
        domains = list(iter_lookback_domains(date, lookback_days, limit=args.limit))

    log.info("loaded %d candidate domains (date=%s lookback_days=%d) dry_run=%s", len(domains), date, lookback_days, args.dry_run)

    if args.dry_run:
        for domain in domains[:20]:
            print(domain)
        if len(domains) > 20:
            print(f"... and {len(domains) - 20} more")
        return 0

    if not domains:
        log.warning("no candidate domains, exiting")
        return 0

    redis_client.wait_for_redis()
    counters = whois_enrich.run(domains, date=date)
    log.info("whois phase: %s", counters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
