# Sidecar for NRD-db's domain enrichment pipeline. Kept separate from the
# main nrd image (which has no Python today and holds the unauthenticated
# Redis WISE depends on) so a bug here can't touch that container's process
# space or data files -- see README's "Enrichment" section.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py redis_client.py domain_utils.py daily_files.py time_budget.py ./
COPY sources/ ./sources/
COPY data/ ./data/
COPY enrich_daily.py enrich_whois.py enrich_vt.py ./

COPY cronjob /etc/cron.d/nrd-enrich-cron
RUN chmod 0644 /etc/cron.d/nrd-enrich-cron

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

CMD ["/usr/local/bin/entrypoint.sh"]
