#!/bin/bash
set -e

# cron strips the container's environment from job invocations by default,
# which would silently break every env-var-driven tunable in config.py
# (including VT_API_KEY). Dump the environment this container actually
# started with into a shell-sourceable, safely-quoted file once at boot,
# and have every cron line source it before running.
python3 - <<'PYEOF' > /app/.container.env
import os
import shlex

for key, value in os.environ.items():
    print(f"export {key}={shlex.quote(value)}")
PYEOF
chmod 600 /app/.container.env

touch /var/log/enrich-daily.log /var/log/enrich-whois.log /var/log/enrich-vt.log

crontab /etc/cron.d/nrd-enrich-cron
cron

tail -f /var/log/enrich-daily.log /var/log/enrich-whois.log /var/log/enrich-vt.log
