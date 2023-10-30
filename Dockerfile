# Use the official Redis base image
FROM redis:latest

# Copy NRD scripts to the image
COPY nrd.sh /usr/local/bin/nrd.sh
RUN mkdir -p /opt/nrd/daily

# Make the scripts executable
RUN chmod +x /usr/local/bin/nrd.sh

# Install cron and create a cron job to run the scripts daily
RUN apt-get update && apt-get install -y cron curl
COPY cronjob /etc/cron.d/nrd-cron
RUN chmod 0644 /etc/cron.d/nrd-cron

# Start Redis and the cron service
CMD ["redis-server"]
RUN crontab /etc/cron.d/nrd-cron
EXPOSE 6379
