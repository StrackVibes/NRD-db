"""WHOIS/RDAP enrichment. Partially free, rate-limited by registries -- this
is the one source where full same-day coverage of ~70k domains is not
realistic or safe. Design goal is honest, gradual, capped coverage: a
global concurrency cap, a per-host minimum interval, a per-host circuit
breaker that stops hitting a registry once it starts erroring/rate-limiting,
and a hard wall-clock time budget. RDAP (structured JSON, IANA bootstrap
routed) is tried first; legacy port-43 WHOIS from a small static TLD table
is the fallback. Referral-following is deliberately NOT implemented (see
domain_utils / README security notes) -- it's a concrete SSRF vector given
this sidecar shares a bridge network with every other container on the
host, and isn't needed to get useful registrar/date data for the common
case.
"""
import datetime
import itertools
import json
import logging
import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

import config
import redis_client
from time_budget import TimeBudget

log = logging.getLogger("nrd_enrich.whois")

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_STATIC_TABLE_PATH = os.path.join(_DATA_DIR, "tld_whois_servers.json")

_LEGACY_FIELD_PATTERNS = [
    (re.compile(r"^\s*Registrar:\s*(.+)$", re.I | re.M), "whois_registrar"),
    (re.compile(r"^\s*Sponsoring Registrar:\s*(.+)$", re.I | re.M), "whois_registrar"),
    (re.compile(r"^\s*Creation Date:\s*(.+)$", re.I | re.M), "whois_created_date"),
    (re.compile(r"^\s*Registered On:\s*(.+)$", re.I | re.M), "whois_created_date"),
    (re.compile(r"^\s*Registry Expiry Date:\s*(.+)$", re.I | re.M), "whois_expires_date"),
    (re.compile(r"^\s*Expiration Date:\s*(.+)$", re.I | re.M), "whois_expires_date"),
]

_bootstrap_cache = {"data": None, "fetched_at": 0.0}
_bootstrap_lock = threading.Lock()


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_static_table():
    with open(_STATIC_TABLE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


class HostThrottle:
    """Per-host minimum request interval + consecutive-failure circuit
    breaker. Process-local, recreated fresh each cron run."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_request = {}
        self._consecutive_failures = {}
        self._tripped = set()

    def wait_turn(self, host):
        with self._lock:
            last = self._last_request.get(host, 0.0)
        wait = config.WHOIS_MIN_INTERVAL_PER_HOST_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        with self._lock:
            self._last_request[host] = time.monotonic()

    def is_tripped(self, host):
        with self._lock:
            return host in self._tripped

    def record_result(self, host, success):
        with self._lock:
            if success:
                self._consecutive_failures[host] = 0
                return
            n = self._consecutive_failures.get(host, 0) + 1
            self._consecutive_failures[host] = n
            if n >= config.WHOIS_HOST_CIRCUIT_BREAKER_THRESHOLD and host not in self._tripped:
                self._tripped.add(host)
                log.warning("whois circuit breaker tripped for host %s after %d consecutive failures", host, n)


def _load_rdap_bootstrap(client):
    with _bootstrap_lock:
        now = time.monotonic()
        if _bootstrap_cache["data"] is not None and now - _bootstrap_cache["fetched_at"] < config.RDAP_BOOTSTRAP_CACHE_SECONDS:
            return _bootstrap_cache["data"]
        tld_map = _bootstrap_cache["data"] or {}
        try:
            resp = client.get(config.RDAP_BOOTSTRAP_URL, timeout=config.WHOIS_CONNECT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            tld_map = {}
            for entry in data.get("services", []):
                try:
                    tlds, urls = entry[0], entry[1]
                except (IndexError, TypeError):
                    continue
                https_urls = [u.rstrip("/") for u in urls if isinstance(u, str) and u.startswith("https://")]
                if not https_urls:
                    continue
                for tld in tlds:
                    tld_map[str(tld).lower()] = https_urls
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("failed to load RDAP bootstrap (using stale/empty cache): %s", exc)
        _bootstrap_cache["data"] = tld_map
        _bootstrap_cache["fetched_at"] = now
        return tld_map


def _extract_vcard_fn(vcard_array):
    if not vcard_array or len(vcard_array) < 2:
        return None
    for item in vcard_array[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == "fn":
            return item[3]
    return None


def _rdap_lookup(client, domain, tld_map, throttle):
    tld = domain.rsplit(".", 1)[-1]
    bases = tld_map.get(tld)
    if not bases:
        return None, "unsupported_tld"
    base = bases[0]
    host = httpx.URL(base).host
    if throttle.is_tripped(host):
        return None, "rate_limited"
    throttle.wait_turn(host)
    url = f"{base}/domain/{domain}"
    try:
        resp = client.get(
            url,
            timeout=httpx.Timeout(config.WHOIS_CONNECT_TIMEOUT_SECONDS, read=config.WHOIS_READ_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        throttle.record_result(host, False)
        return None, "timeout"
    except httpx.HTTPError as exc:
        log.debug("rdap request error for %s: %s", domain, exc)
        throttle.record_result(host, False)
        return None, "error"

    if resp.status_code == 429 or resp.status_code >= 500:
        throttle.record_result(host, False)
        return None, "rate_limited"
    if resp.status_code == 404:
        throttle.record_result(host, True)
        return {"whois_source": f"rdap:{host}"}, "ok_rdap"
    if resp.status_code != 200:
        throttle.record_result(host, False)
        return None, "error"

    throttle.record_result(host, True)
    try:
        data = resp.json()
    except ValueError:
        return {"whois_source": f"rdap:{host}"}, "ok_rdap"

    fields = {"whois_source": f"rdap:{host}"}
    for event in data.get("events", []) or []:
        action = (event.get("eventAction") or "").lower()
        date_ = event.get("eventDate")
        if not date_:
            continue
        if action == "registration":
            fields["whois_created_date"] = date_
        elif action == "expiration":
            fields["whois_expires_date"] = date_
    for entity in data.get("entities", []) or []:
        roles = [r.lower() for r in (entity.get("roles") or [])]
        if "registrar" in roles:
            name = _extract_vcard_fn(entity.get("vcardArray"))
            fields["whois_registrar"] = name or entity.get("handle") or ""
            break
    return fields, "ok_rdap"


def _legacy_lookup(domain, static_table, throttle):
    tld = domain.rsplit(".", 1)[-1]
    host = static_table.get(tld)
    if not host:
        return None, "unsupported_tld"
    if throttle.is_tripped(host):
        return None, "rate_limited"
    throttle.wait_turn(host)

    try:
        sock = socket.create_connection((host, 43), timeout=config.WHOIS_CONNECT_TIMEOUT_SECONDS)
    except OSError as exc:
        log.debug("whois connect failed for %s (%s): %s", domain, host, exc)
        throttle.record_result(host, False)
        return None, "error"

    try:
        sock.settimeout(config.WHOIS_READ_TIMEOUT_SECONDS)
        sock.sendall((domain + "\r\n").encode("ascii"))
        chunks = []
        total = 0
        while True:
            data = sock.recv(4096)
            if not data:
                break
            total += len(data)
            chunks.append(data)
            if total > config.WHOIS_MAX_RESPONSE_BYTES:
                break
    except OSError as exc:
        log.debug("whois read failed for %s (%s): %s", domain, host, exc)
        throttle.record_result(host, False)
        return None, "timeout"
    finally:
        sock.close()

    text = b"".join(chunks).decode("utf-8", errors="replace")
    if not text.strip():
        throttle.record_result(host, False)
        return None, "error"

    throttle.record_result(host, True)
    fields = {"whois_source": f"whois:{host}"}
    for pattern, field in _LEGACY_FIELD_PATTERNS:
        if field in fields:
            continue
        match = pattern.search(text)
        if match:
            fields[field] = match.group(1).strip()
    return fields, "ok_legacy"


def _lookup_domain(client, domain, tld_map, static_table, rdap_throttle, legacy_throttle):
    fields, status = _rdap_lookup(client, domain, tld_map, rdap_throttle)
    if status == "ok_rdap":
        fields["whois_status"] = "ok_rdap"
        return fields
    if status == "rate_limited":
        return {"whois_status": "rate_limited"}

    fields2, status2 = _legacy_lookup(domain, static_table, legacy_throttle)
    if status2 == "ok_legacy":
        fields2["whois_status"] = "ok_legacy"
        return fields2
    if status2 == "rate_limited":
        return {"whois_status": "rate_limited"}
    if status == "unsupported_tld" and status2 == "unsupported_tld":
        return {"whois_status": "unsupported_tld"}
    final = status2 if status2 in ("timeout", "error") else (status if status in ("timeout", "error") else "error")
    return {"whois_status": final}


def run(domains, date=None):
    """domains: iterable of already-normalized domain candidates (typically
    from daily_files.iter_lookback_domains). Skips anything already in a
    terminal whois_status or at the attempts cap."""
    counters = {
        "attempted": 0, "ok": 0, "errors": 0, "rate_limited": 0,
        "unsupported_tld": 0, "budget_exhausted": 0, "skipped_already_done": 0,
        "max_attempts_reached": 0,
    }
    started_at = time.time()
    budget = TimeBudget(config.WHOIS_TIME_BUDGET_SECONDS)

    client = httpx.Client(headers={"User-Agent": "nrd-db-enrich/1 (+https://github.com/strackvibes/NRD-db)"})
    try:
        tld_map = _load_rdap_bootstrap(client)
        static_table = _load_static_table()
        rdap_throttle = HostThrottle()
        legacy_throttle = HostThrottle()

        def _eligible():
            n = 0
            for domain in domains:
                if n >= config.WHOIS_CANDIDATE_LIMIT:
                    return
                existing = redis_client.hmget_fields(domain, ["whois_status", "whois_attempts"])
                status = existing.get("whois_status")
                if status not in (None, "not_attempted"):
                    counters["skipped_already_done"] += 1
                    continue
                attempts = int(existing.get("whois_attempts") or 0)
                if attempts >= config.WHOIS_MAX_ATTEMPTS:
                    counters["max_attempts_reached"] += 1
                    continue
                n += 1
                yield domain

        def _worker(domain):
            redis_client.bump_whois_attempts(domain)
            fields = _lookup_domain(client, domain, tld_map, static_table, rdap_throttle, legacy_throttle)
            fields["whois_checked_at"] = _now_iso()
            redis_client.set_fields(domain, fields)
            return fields.get("whois_status")

        # Submitted in bounded batches (checking the time budget between
        # batches) rather than handing the whole candidate list to the pool
        # at once -- a ThreadPoolExecutor's internal queue has no size
        # limit, so an eager "submit everything, then as_completed()" would
        # let already-queued work keep running long past WHOIS_TIME_BUDGET_
        # SECONDS. Batches are sized to global concurrency so each batch's
        # worst case is bounded by a single request's timeout.
        domains_iter = _eligible()
        with ThreadPoolExecutor(max_workers=config.WHOIS_GLOBAL_CONCURRENCY) as pool:
            while True:
                if budget.expired:
                    for _ in domains_iter:
                        counters["budget_exhausted"] += 1
                    break
                batch = list(itertools.islice(domains_iter, config.WHOIS_GLOBAL_CONCURRENCY))
                if not batch:
                    break
                futures = {pool.submit(_worker, d): d for d in batch}
                for fut in as_completed(futures):
                    counters["attempted"] += 1
                    try:
                        status = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("whois worker error for %s: %s", futures[fut], exc)
                        status = "error"
                    if status in ("ok_rdap", "ok_legacy"):
                        counters["ok"] += 1
                    elif status == "rate_limited":
                        counters["rate_limited"] += 1
                    elif status == "unsupported_tld":
                        counters["unsupported_tld"] += 1
                    else:
                        counters["errors"] += 1
    finally:
        client.close()

    finished_at = time.time()
    if date:
        redis_client.record_run_summary(date, "whois", counters, started_at, finished_at)
    return counters
