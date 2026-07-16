"""Single source of truth for every env-var-driven tunable. Fails fast on
malformed values so a typo in docker-compose surfaces at container start,
not three hours into a WHOIS run."""
import os
import sys


class ConfigError(Exception):
    pass


def _str_env(name, default):
    return os.environ.get(name, default)


def _int_env(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a valid integer")


def _float_env(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a valid float")


def _list_env(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Redis -------------------------------------------------------------
REDIS_HOST = _str_env("REDIS_HOST", "nrd")
REDIS_PORT = _int_env("REDIS_PORT", 6379)
REDIS_DB = _int_env("REDIS_DB", 0)
REDIS_PASSWORD = _str_env("REDIS_PASSWORD", None) or None
REDIS_SOCKET_TIMEOUT = _float_env("REDIS_SOCKET_TIMEOUT", 10.0)

ENRICH_TTL_DAYS = _int_env("ENRICH_TTL_DAYS", 180)
RUN_SUMMARY_TTL_DAYS = _int_env("RUN_SUMMARY_TTL_DAYS", 30)
VT_COUNTER_TTL_DAYS = _int_env("VT_COUNTER_TTL_DAYS", 2)

# --- Input ---------------------------------------------------------------
DAILY_DIR = _str_env("DAILY_DIR", "/opt/nrd/daily")

# --- DNS -------------------------------------------------------------
DNS_CONCURRENCY = _int_env("DNS_CONCURRENCY", 100)
DNS_TIMEOUT_SECONDS = _float_env("DNS_TIMEOUT_SECONDS", 2.0)
DNS_LIFETIME_SECONDS = _float_env("DNS_LIFETIME_SECONDS", 4.0)
DNS_RESOLVERS = _list_env("DNS_RESOLVERS", ["1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4"])
DNS_TIME_BUDGET_SECONDS = _int_env("DNS_TIME_BUDGET_SECONDS", 2700)

# --- ASN (Team Cymru bulk whois) --------------------------------------
ASN_CYMRU_HOST = _str_env("ASN_CYMRU_HOST", "whois.cymru.com")
ASN_CYMRU_PORT = _int_env("ASN_CYMRU_PORT", 43)
ASN_BATCH_SIZE = _int_env("ASN_BATCH_SIZE", 500)
ASN_BATCH_PAUSE_SECONDS = _float_env("ASN_BATCH_PAUSE_SECONDS", 1.0)
ASN_TIME_BUDGET_SECONDS = _int_env("ASN_TIME_BUDGET_SECONDS", 600)
ASN_CIRCUIT_BREAKER_THRESHOLD = _int_env("ASN_CIRCUIT_BREAKER_THRESHOLD", 2)
ASN_MAX_RESPONSE_BYTES = _int_env("ASN_MAX_RESPONSE_BYTES", 65536)
ASN_SOCKET_TIMEOUT_SECONDS = _float_env("ASN_SOCKET_TIMEOUT_SECONDS", 10.0)

# --- WHOIS / RDAP -------------------------------------------------------
WHOIS_GLOBAL_CONCURRENCY = _int_env("WHOIS_GLOBAL_CONCURRENCY", 10)
WHOIS_MIN_INTERVAL_PER_HOST_SECONDS = _float_env("WHOIS_MIN_INTERVAL_PER_HOST_SECONDS", 2.0)
WHOIS_HOST_CIRCUIT_BREAKER_THRESHOLD = _int_env("WHOIS_HOST_CIRCUIT_BREAKER_THRESHOLD", 3)
WHOIS_MAX_ATTEMPTS = _int_env("WHOIS_MAX_ATTEMPTS", 3)
WHOIS_TIME_BUDGET_SECONDS = _int_env("WHOIS_TIME_BUDGET_SECONDS", 1800)
WHOIS_LOOKBACK_DAYS = _int_env("WHOIS_LOOKBACK_DAYS", 3)
WHOIS_CANDIDATE_LIMIT = _int_env("WHOIS_CANDIDATE_LIMIT", 20000)
WHOIS_CONNECT_TIMEOUT_SECONDS = _float_env("WHOIS_CONNECT_TIMEOUT_SECONDS", 5.0)
WHOIS_READ_TIMEOUT_SECONDS = _float_env("WHOIS_READ_TIMEOUT_SECONDS", 8.0)
WHOIS_MAX_RESPONSE_BYTES = _int_env("WHOIS_MAX_RESPONSE_BYTES", 65536)
RDAP_BOOTSTRAP_URL = _str_env(
    "RDAP_BOOTSTRAP_URL", "https://data.iana.org/rdap/dns.json"
)
RDAP_BOOTSTRAP_CACHE_SECONDS = _int_env("RDAP_BOOTSTRAP_CACHE_SECONDS", 86400)

# --- Reverse WHOIS (stub only, no free source exists) -------------------
REVERSE_WHOIS_PROVIDER = _str_env("REVERSE_WHOIS_PROVIDER", None) or None
REVERSE_WHOIS_API_KEY = _str_env("REVERSE_WHOIS_API_KEY", None) or None

# --- crt.sh (Certificate Transparency, public Postgres mirror) ----------
CRT_PG_HOST = _str_env("CRT_PG_HOST", "crt.sh")
CRT_PG_PORT = _int_env("CRT_PG_PORT", 5432)
CRT_PG_DB = _str_env("CRT_PG_DB", "certwatch")
CRT_PG_USER = _str_env("CRT_PG_USER", "guest")
CRT_MAX_CONCURRENCY = _int_env("CRT_MAX_CONCURRENCY", 3)
CRT_STATEMENT_TIMEOUT_SECONDS = _float_env("CRT_STATEMENT_TIMEOUT_SECONDS", 5.0)
CRT_CONNECT_TIMEOUT_SECONDS = _float_env("CRT_CONNECT_TIMEOUT_SECONDS", 5.0)
CRT_TIME_BUDGET_SECONDS = _int_env("CRT_TIME_BUDGET_SECONDS", 1800)
CRT_CIRCUIT_BREAKER_THRESHOLD = _int_env("CRT_CIRCUIT_BREAKER_THRESHOLD", 2)

# --- VirusTotal -----------------------------------------------------------
VT_API_KEY = _str_env("VT_API_KEY", None) or None
VT_REQ_PER_MIN = _int_env("VT_REQ_PER_MIN", 4)
VT_REQ_PER_DAY = _int_env("VT_REQ_PER_DAY", 500)
VT_BATCH_PER_RUN = _int_env("VT_BATCH_PER_RUN", 40)
VT_LOOKBACK_DAYS = _int_env("VT_LOOKBACK_DAYS", 7)
VT_REQUEST_TIMEOUT_SECONDS = _float_env("VT_REQUEST_TIMEOUT_SECONDS", 15.0)

LOG_LEVEL = _str_env("LOG_LEVEL", "INFO")


def validate():
    """Fail fast at container start rather than mid-run."""
    problems = []
    if DNS_CONCURRENCY < 1:
        problems.append("DNS_CONCURRENCY must be >= 1")
    if WHOIS_GLOBAL_CONCURRENCY < 1:
        problems.append("WHOIS_GLOBAL_CONCURRENCY must be >= 1")
    if VT_REQ_PER_MIN < 0 or VT_REQ_PER_DAY < 0:
        problems.append("VT_REQ_PER_MIN / VT_REQ_PER_DAY must be >= 0")
    if not DNS_RESOLVERS:
        problems.append("DNS_RESOLVERS must not be empty")
    if problems:
        raise ConfigError("; ".join(problems))


if __name__ == "__main__":
    try:
        validate()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(1)
    print("config OK")
