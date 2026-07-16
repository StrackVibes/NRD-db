"""Reads the daily NRD files nrd.sh already writes to /opt/nrd/daily/. This
module is read-only with respect to that directory -- nrd.sh remains the
sole writer (the sidecar mounts it read-only in compose). Confirmed on-disk
format: one 'domain date ' pair per line, no header, e.g.
'twtpub.com 2026-07-15 '.
"""
import datetime
import logging
import os

import config
from domain_utils import try_normalize_domain

log = logging.getLogger("nrd_enrich.daily_files")


def daily_file_path(date, daily_dir=None):
    return os.path.join(daily_dir or config.DAILY_DIR, f"{date}-nrd.txt")


def iter_daily_domains(date, daily_dir=None, limit=None, stats=None):
    """Yield normalized, deduped domains from a single day's file. Malformed
    rows are counted (via `stats`, if given) and skipped -- never raised."""
    path = daily_file_path(date, daily_dir)
    if not os.path.isfile(path):
        log.warning("daily file not found: %s", path)
        return
    seen = set()
    yielded = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            first_token = raw.split()[0]
            domain, err = try_normalize_domain(first_token)
            if domain is None:
                if stats is not None:
                    stats["invalid_domain"] = stats.get("invalid_domain", 0) + 1
                continue
            if domain in seen:
                continue
            seen.add(domain)
            yield domain
            yielded += 1
            if limit and yielded >= limit:
                return


def iter_lookback_domains(end_date, lookback_days, daily_dir=None, limit=None, stats=None):
    """Yield normalized, deduped domains across [end_date - lookback_days+1,
    end_date]. Used by the WHOIS phase, which can't realistically finish a
    whole day's cohort in one run and instead works a rolling window."""
    end = datetime.date.fromisoformat(end_date)
    seen = set()
    yielded = 0
    for offset in range(lookback_days):
        day = (end - datetime.timedelta(days=offset)).isoformat()
        for domain in iter_daily_domains(day, daily_dir=daily_dir, stats=stats):
            if domain in seen:
                continue
            seen.add(domain)
            yield domain
            yielded += 1
            if limit and yielded >= limit:
                return
