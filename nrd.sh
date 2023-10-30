#!/usr/bin/env bash

# Define functions for colored output
function echo.Red() {
  echo -e "\\033[31m$*\\033[m"
}

function echo.Green() {
  echo -e "\\033[32m$*\\033[m"
}

function echo.Cyan() {
  echo -e "\\033[36m$*\\033[m"
}

# Function for displaying error messages
function error() {
    echo.Red >&2 "$@"
    exit 1
}

# Check if required commands are available
required_commands=("mkdir" "wc" "base64" "curl" "cat" "zcat" "mktemp" "date" "tr" "realpath" "dirname")

for cmd in "${required_commands[@]}"; do
    if ! command -v "$cmd" > /dev/null 2>&1; then
        error "Command '$cmd' not found!"
    fi
done

# Set script options
set -e

# Define variables
DIR="/opt/nrd"
DAY_RANGE="${DAY_RANGE:-1}"
DAILY_DIR="/tmp/${DAILY_DIR:-daily}"
TEMP_FILE="$(mktemp -p "$DIR" --suffix=nrd)"
PAID_WHOISDS_USERNAME="${PAID_WHOISDS_USERNAME:-}"
PAID_WHOISDS_PASSWORD="${PAID_WHOISDS_PASSWORD:-}"
BASE_URL_FREE="https://whoisds.com/whois-database/newly-registered-domains"
BASE_URL_PAID="https://whoisds.com/your-download/direct-download_file/${PAID_WHOISDS_USERNAME}/${PAID_WHOISDS_PASSWORD}"

# Move to the script directory
cd "$DIR"

# Display a message about the script
echo.Green "You are using StrackVibes's nrd-list-downloader to download NRD(Newly Registered Domain) list ..."
echo.Cyan "NRD list of the last $DAY_RANGE days will be downloaded."

# Function for inserting lines into the temporary file
function insert_into_temp_file() {
    echo "$*" >> "$TEMP_FILE"
}

# Function for downloading NRD data
function download() {
    local TYPE="${1:-free}"
    local TARGET_FILE="/opt/nrd/daily/$(date +'%Y-%m-%d')-nrd.txt"
    local DOWNLOAD_DIR="${DAILY_DIR}/${TYPE}"
    mkdir -p "$DOWNLOAD_DIR"

    echo
    echo.Cyan "Downloading $TYPE NRD list ..."

    if [ "$TYPE" = "free" ] && [ "$DAY_RANGE" -gt 10 ]; then
        echo.Red "Warning! Free NRD list before more than 10 days might be removed from WhoisDS.com already, the download may fail."
    fi

    if [ "$TYPE" = "paid" ] && [ "$DAY_RANGE" -gt 30 ]; then
        echo.Red "Warning! Paid NRD list before more than 30 days might be removed from WhoisDS.com already, the download may fail."
    fi

    for i in $(seq "$DAY_RANGE" -1 1); do
        local DATE FILE URL
        DATE="$(date -u --date "$i days ago" '+%Y-%m-%d')"
        FILE="${DOWNLOAD_DIR}/${DATE}"

        if [ -s "$FILE" ] && [ "$(grep -vc '^$' "$FILE")" -ge 1 ]; then
            echo.Cyan "$FILE existed with $(grep -vc '^$' "$FILE") domains, skipping the download and decompress process ..."
        else
            printf "Download and decompress %s data ... " "$DATE"
            if [ "$TYPE" = "paid" ]; then
                URL="${BASE_URL_PAID}/${DATE}.zip/ddu"
            else
                URL="${BASE_URL_FREE}/$(echo "${DATE}.zip" | base64 | sed 's/.$//')/nrd"
            fi
            curl -sSLo- "$URL" | zcat | tr -d '\015' >> "$FILE"
            echo "" >> "$FILE"
            echo.Cyan "$(grep -vc '^$' "$FILE") domains found."
        fi

        awk -F ' ' 'FNR>1 { if(!$0){$0="NA"}; printf("%s '$DATE' \n",$0)}' "$FILE" >> "$TEMP_FILE"
        awk -F ' ' 'FNR>1 { if(!$0){$0="NA"}; printf("SET %s '$DATE' \n",$0)}' "$FILE" | redis-cli
    done

    chmod +r "$TEMP_FILE"
    mv "$TEMP_FILE" "$TARGET_FILE"

    #while IFS= read -r line; do
    #echo '$line' | redis-cli

    echo.Green "NRD list for the last $DAY_RANGE days saved to $TARGET_FILE, $(grep -cvE '^(#|$)' "$TARGET_FILE") domains found."
    echo
}

download free

if [ -n "$PAID_WHOISDS_USERNAME" ] && [ -n "$PAID_WHOISDS_PASSWORD" ]; then
    echo.Green "WhoisDS paid account found! Will try to download paid premium NRD package with it."
    download paid
fi
