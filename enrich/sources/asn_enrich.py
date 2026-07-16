"""IP2ASN enrichment via Team Cymru's bulk whois service. This only ever
runs against IPs that the DNS phase already resolved for today's cohort
(passed in directly as ip_map, no Redis re-read needed) -- a small fraction
of the day's ~70k domains, since most brand-new domains don't resolve yet.
Uses Cymru's documented begin/verbose/end bulk protocol over a single raw
TCP session per batch: the officially sanctioned bulk-friendly method, as
opposed to thousands of individual per-IP whois queries.
"""
import datetime
import ipaddress
import logging
import socket
import time

import config
import redis_client

log = logging.getLogger("nrd_enrich.asn")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _classify_ip(raw):
    """Returns (ip_str_or_None, status) where status is 'ok' for a normal
    routable IP eligible for lookup, or a terminal status string for
    anything else (invalid, private/loopback/link-local/reserved)."""
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return None, "error"
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
        # A NRD resolving to a private/internal address is itself a signal
        # worth a SOC's attention, not noise to discard.
        return None, "private_ip"
    return str(addr), "ok"


def _query_cymru_batch(ips):
    """ips: list of unique routable IP strings (already validated).
    Returns {ip: {asn, prefix, country, registry, allocated, as_name}}.

    Empirically verified against the live service: Cymru's bulk whois wants
    CRLF line endings, and -- unlike a typical whois server -- treats a
    half-closed write side (shutdown(SHUT_WR), the usual "I'm done sending"
    signal) as an abrupt disconnect and returns nothing at all. Don't call
    shutdown() here; just send 'end\\r\\n' and read until the server closes
    the connection on its own."""
    payload = "begin\r\nverbose\r\n" + "\r\n".join(ips) + "\r\nend\r\n"
    sock = socket.create_connection(
        (config.ASN_CYMRU_HOST, config.ASN_CYMRU_PORT),
        timeout=config.ASN_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        sock.settimeout(config.ASN_SOCKET_TIMEOUT_SECONDS)
        sock.sendall(payload.encode("ascii"))
        chunks = []
        total = 0
        while True:
            data = sock.recv(4096)
            if not data:
                break
            total += len(data)
            if total > config.ASN_MAX_RESPONSE_BYTES:
                raise ValueError(f"cymru response exceeded {config.ASN_MAX_RESPONSE_BYTES} bytes")
            chunks.append(data)
    finally:
        sock.close()

    text = b"".join(chunks).decode("utf-8", errors="replace")
    results = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        asn, ip, prefix, cc, registry, allocated, as_name = [p for p in parts[:7]]
        if asn.upper() == "AS":  # header row
            continue
        results[ip] = {
            "asn": asn,
            "prefix": prefix,
            "country": cc,
            "registry": registry,
            "allocated": allocated,
            "as_name": as_name,
        }
    return results


def run(ip_map, date=None):
    """ip_map: {domain: [ip, ...]} as produced by dns_enrich.run(). Writes
    asn_status/asn_info for every domain in ip_map, plus 'no_ip'/'private_ip'
    handling for domains that don't need a network lookup at all."""
    counters = {"attempted": 0, "ok": 0, "errors": 0, "budget_exhausted": 0, "private_ip": 0}
    started_at = time.time()
    deadline = started_at + config.ASN_TIME_BUDGET_SECONDS

    # Build ip -> [domains] using only validated, routable IPs.
    ip_to_domains = {}
    for domain, ips in ip_map.items():
        routable_found = False
        for raw_ip in ips:
            ip, status = _classify_ip(raw_ip)
            if status == "private_ip":
                redis_client.set_fields(domain, {"asn_status": "private_ip", "asn_checked_at": _now_iso()})
                counters["private_ip"] += 1
                routable_found = True  # handled, don't also mark no_ip below
                break
            if ip:
                ip_to_domains.setdefault(ip, []).append(domain)
                routable_found = True
        if not routable_found:
            redis_client.set_fields(domain, {"asn_status": "error", "asn_checked_at": _now_iso()})

    unique_ips = list(ip_to_domains.keys())
    consecutive_failures = 0

    for start in range(0, len(unique_ips), config.ASN_BATCH_SIZE):
        if time.time() >= deadline:
            remaining = unique_ips[start:]
            counters["budget_exhausted"] += sum(len(ip_to_domains[ip]) for ip in remaining)
            break
        if consecutive_failures >= config.ASN_CIRCUIT_BREAKER_THRESHOLD:
            remaining = unique_ips[start:]
            counters["errors"] += sum(len(ip_to_domains[ip]) for ip in remaining)
            log.warning("asn circuit breaker tripped after %d consecutive batch failures", consecutive_failures)
            break

        batch = unique_ips[start:start + config.ASN_BATCH_SIZE]
        try:
            batch_results = _query_cymru_batch(batch)
            consecutive_failures = 0
        except (OSError, ValueError) as exc:
            log.warning("cymru batch query failed: %s", exc)
            consecutive_failures += 1
            for ip in batch:
                for domain in ip_to_domains[ip]:
                    counters["attempted"] += 1
                    counters["errors"] += 1
                    redis_client.set_fields(domain, {"asn_status": "cymru_error", "asn_checked_at": _now_iso()})
            time.sleep(config.ASN_BATCH_PAUSE_SECONDS)
            continue

        for ip in batch:
            record = batch_results.get(ip)
            for domain in ip_to_domains[ip]:
                counters["attempted"] += 1
                if record:
                    counters["ok"] += 1
                    redis_client.set_fields(domain, {
                        "asn_status": "ok",
                        "asn_info": _format_asn_info(ip, record),
                        "asn_checked_at": _now_iso(),
                    })
                else:
                    counters["errors"] += 1
                    redis_client.set_fields(domain, {"asn_status": "cymru_error", "asn_checked_at": _now_iso()})
        time.sleep(config.ASN_BATCH_PAUSE_SECONDS)

    finished_at = time.time()
    if date:
        redis_client.record_run_summary(date, "asn", counters, started_at, finished_at)
    return counters


def _format_asn_info(ip, record):
    import json
    return json.dumps([{
        "ip": ip,
        "asn": record["asn"],
        "as_name": record["as_name"],
        "country": record["country"],
        "registry": record["registry"],
        "allocated": record["allocated"],
    }])
