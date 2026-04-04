#!/usr/bin/env bash
set -euo pipefail

# Generate combined data then serve the dashboard
cd "$(dirname "$0")"

echo "=== Generating jobs data ==="
./generate-data.sh

echo ""
echo "=== Starting dashboard server ==="
echo "Open http://localhost:8080 in your browser"
echo ""

python3 -m http.server 8080
