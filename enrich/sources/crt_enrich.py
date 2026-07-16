"""Certificate Transparency enrichment via crt.sh's public Postgres mirror
(read-only 'guest' access, no credential needed). All queries are
parameterized -- the raw domain string is only ever bound as a query
parameter, never string-formatted into SQL, so SQL injection is
structurally impossible regardless of feed content.

Empirically verified against the live service while building this: a
LIMIT-only query typically returns in ~1-2s, including for the "no
certificate found" case that the vast majority of brand-new NRDs will hit.
Adding `ORDER BY` -- even on the cheap integer `id` column, not just a
decoded certificate field -- made PostgreSQL materialize and sort the
*entire* match set before applying LIMIT: a single high-cert-volume domain
(google.com) took over 120s and was killed rather than complete. Do not add
ORDER BY to this query.
"""
import datetime
import itertools
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed

import psycopg2

import config
import redis_client
from time_budget import TimeBudget

log = logging.getLogger("nrd_enrich.crt")

_QUERY = """
    SELECT c.id, x509_notBefore(c.certificate), x509_issuerName(c.certificate)
    FROM certificate c
    WHERE plainto_tsquery('certwatch', %s) @@ identities(c.certificate)
    LIMIT 5
"""


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _connect():
    """Deliberately does NOT issue `SET statement_timeout`. crt.sh's public
    endpoint is fronted by a connection pooler (confirmed: it rejects
    libpq's `options` startup parameter with "unsupported startup
    parameter"), and empirically, issuing `SET statement_timeout = ...` as
    a runtime statement against it hangs forever -- reproduced repeatedly
    while building this, with and without a bind parameter, even though a
    bare connect and a bare query each reliably complete in ~1-2s. Bounding
    is done client-side instead: connect_timeout here, plus a per-batch
    as_completed() timeout in run() as a second line of defense."""
    conn = psycopg2.connect(
        host=config.CRT_PG_HOST,
        port=config.CRT_PG_PORT,
        dbname=config.CRT_PG_DB,
        user=config.CRT_PG_USER,
        connect_timeout=int(config.CRT_CONNECT_TIMEOUT_SECONDS) or 1,
    )
    conn.autocommit = True
    return conn


def _lookup_one(domain):
    """Opens its own short-lived connection per lookup: crt.sh is a shared
    community resource, and with a strict concurrency cap of a handful of
    workers, short-lived connections are friendlier than holding a pool
    open against it."""
    conn = None
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(_QUERY, (domain,))
            rows = cur.fetchall()
        return rows, None
    except psycopg2.Error as exc:
        return None, exc
    finally:
        if conn is not None:
            conn.close()


def _record_result(domain, rows):
    if not rows:
        redis_client.set_fields(domain, {
            "crt_status": "ok_none_found",
            "crt_cert_count": "0",
            "crt_checked_at": _now_iso(),
        })
        return
    not_befores = [r[1].isoformat() for r in rows if r[1] is not None]
    issuers = [r[2] for r in rows if r[2]]
    redis_client.set_fields(domain, {
        "crt_status": "ok_found",
        "crt_cert_count": str(len(rows)),
        "crt_first_seen_not_before": min(not_befores) if not_befores else "",
        "crt_latest_issuer": issuers[0] if issuers else "",
        "crt_checked_at": _now_iso(),
    })


def run(domains, date=None):
    counters = {"attempted": 0, "ok": 0, "errors": 0, "budget_exhausted": 0, "skipped_already_done": 0}
    started_at = time.time()
    budget = TimeBudget(config.CRT_TIME_BUDGET_SECONDS)
    consecutive_failures = 0

    def _eligible():
        for domain in domains:
            status = redis_client.get_status(domain, "crt")
            if status not in (None, "not_attempted"):
                counters["skipped_already_done"] += 1
                continue
            yield domain

    domains_iter = _eligible()
    with ThreadPoolExecutor(max_workers=config.CRT_MAX_CONCURRENCY) as pool:
        while True:
            if budget.expired:
                for _ in domains_iter:
                    counters["budget_exhausted"] += 1
                break
            if consecutive_failures >= config.CRT_CIRCUIT_BREAKER_THRESHOLD:
                for _ in domains_iter:
                    counters["errors"] += 1
                log.warning("crt.sh circuit breaker tripped after %d consecutive errors", consecutive_failures)
                break

            batch = list(itertools.islice(domains_iter, config.CRT_MAX_CONCURRENCY))
            if not batch:
                break

            futures = {pool.submit(_lookup_one, d): d for d in batch}
            # Second line of defense beyond connect_timeout: bound the
            # whole batch's wait, since psycopg2's sync driver gives no
            # clean way to abort a single in-flight query early.
            batch_timeout = config.CRT_CONNECT_TIMEOUT_SECONDS + config.CRT_STATEMENT_TIMEOUT_SECONDS + 10
            try:
                for fut in as_completed(futures, timeout=batch_timeout):
                    domain = futures.pop(fut)
                    counters["attempted"] += 1
                    rows, err = fut.result()
                    if err is not None:
                        consecutive_failures += 1
                        counters["errors"] += 1
                        log.debug("crt.sh query error for %s: %s", domain, err)
                        redis_client.set_fields(domain, {"crt_status": "db_error", "crt_checked_at": _now_iso()})
                        continue
                    consecutive_failures = 0
                    _record_result(domain, rows)
                    counters["ok"] += 1
            except FutureTimeoutError:
                stuck = list(futures.values())
                consecutive_failures += len(stuck)
                counters["errors"] += len(stuck)
                for domain in stuck:
                    log.warning("crt.sh query for %s exceeded %.0fs batch timeout; giving up on it", domain, batch_timeout)
                    redis_client.set_fields(domain, {"crt_status": "db_error", "crt_checked_at": _now_iso()})

    finished_at = time.time()
    if date:
        redis_client.record_run_summary(date, "crt", counters, started_at, finished_at)
    return counters
