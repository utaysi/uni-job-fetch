#!/usr/bin/env bash
set -euo pipefail

# Wrapper for systemd timer — keeps hourly folders, cleans up intermediate ones.
# Configure your ntfy topic below:
NTFY_TOPIC="uni-jobs-ruby-XXXX"

cd "$(dirname "$0")"

MINUTE=$(date +%M)
ARGS="--notify $NTFY_TOPIC"

if [[ "$MINUTE" != "00" ]]; then
    ARGS="$ARGS --cleanup"
fi

exec ./fetch-jobs.sh $ARGS
