#!/bin/bash

# Start the Redis server in the background
redis-server &

# Start the cron service
cron

# Tail the cron log file to keep the container running
tail -f /var/log/cron.log
