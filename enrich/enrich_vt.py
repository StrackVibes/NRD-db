#!/usr/bin/env python3
"""Standalone VirusTotal drip entrypoint, intended to be cron'd every 15
minutes. Instant no-op if VT_API_KEY is unset. See sources/vt_enrich.py for
the rate-limiting design.

Usage:
    enrich_vt.py [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import datetime
import logging
import sys

import config
import redis_client
from sources import vt_enrich

log = logging.getLogger("nrd_enrich.enrich_vt")


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true", help="report config/quota state, make no requests")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config.validate()

    date = args.date or _today()

    if args.dry_run:
        if not config.VT_API_KEY:
            print("VT_API_KEY not set -- vt phase is a permanent no-op until one is configured")
            return 0
        redis_client.wait_for_redis()
        used = redis_client.get_vt_daily_count(date)
        print(f"VT_API_KEY set; daily quota used so far for {date}: {used}/{config.VT_REQ_PER_DAY}")
        return 0

    redis_client.wait_for_redis()
    counters = vt_enrich.run(date=date)
    log.info("vt phase: %s", counters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
