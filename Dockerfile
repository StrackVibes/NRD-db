# Use the official Redis base image
FROM redis:latest

# Install cron, curl, and other dependencies
RUN apt-get update && apt-get install -y cron curl

# Copy NRD scripts to the image
COPY nrd.sh /usr/local/bin/nrd.sh
RUN mkdir -p /opt/nrd/daily

# Make the NRD script executable
RUN chmod +x /usr/local/bin/nrd.sh

# Copy cron job configuration
COPY cronjob /etc/cron.d/nrd-cron
RUN chmod 0644 /etc/cron.d/nrd-cron

# Apply cron job and make sure it's executable
RUN crontab /etc/cron.d/nrd-cron

# Make sure the log file exists, and run both Redis and cron in the same container
RUN touch /var/log/cron.log

# Expose Redis port
EXPOSE 6379

# Use a script to run both Redis and cron
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set the entry point to start Redis and cron
CMD ["/usr/local/bin/entrypoint.sh"]

