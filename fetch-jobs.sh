#!/usr/bin/env bash
set -euo pipefail

# Uni Marburg student job fetcher
# Fetches all student assistant job PDFs and searches them for a name.

URL="https://www.uni-marburg.de/de/universitaet/administration/verwaltung/dezernat2/personalabteilung/bewerber/stud-und-wiss-hilfskraftstellen"
SEARCH_NAME="Matthias"
NOTIFY_TOPIC=""
CLEANUP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)
            SEARCH_NAME="$2"
            shift 2
            ;;
        --notify)
            NOTIFY_TOPIC="$2"
            shift 2
            ;;
        --cleanup)
            CLEANUP=true
            shift
            ;;
        *)
            echo "Usage: $0 [--name <search_string>] [--notify <ntfy_topic>] [--cleanup]"
            exit 1
            ;;
    esac
done

# Create output directory with date-time stamp
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
OUTDIR="jobs_${TIMESTAMP}"
mkdir -p "$OUTDIR"

echo "=== Uni Marburg Job Fetcher ==="
echo "Output directory: $OUTDIR"
echo "Search term: $SEARCH_NAME"
echo ""

# Fetch the page HTML
echo "Fetching job listings page..."
PAGE_HTML=$(curl -sL "$URL")

# Parse job listings from the HTML table
# Each row has: <td>Department<br/>Sub-unit</td> <td><a href="...pdf">...</a></td> <td>date</td>
# We extract the PDF href and the department text.

# Extract all table rows containing PDF links
# Use grep + sed to pull out href and department info

# Get all PDF links with their surrounding row context
echo "$PAGE_HTML" | python3 -c "
import sys
import html
from html.parser import HTMLParser
import re
import json

content = sys.stdin.read()

# Find all table rows in the job listing table
# Pattern: look for <tr> blocks that contain .pdf links
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL)

jobs = []
seen_names = {}

for row in rows:
    # Check if this row has a PDF link
    pdf_match = re.search(r'href=[\"\\x27]([^\"\\x27]*\.pdf)[\"\\x27]', row)
    if not pdf_match:
        continue

    pdf_href = pdf_match.group(1)

    # Extract cell contents
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
    if len(cells) < 2:
        continue

    # First cell: department info (may contain <br/> or <br> separating dept and sub-unit)
    dept_cell = cells[0]
    # Strip HTML tags but preserve <br> as separator
    dept_cell = re.sub(r'<br\s*/?>', ' | ', dept_cell)
    dept_cell = re.sub(r'<[^>]+>', '', dept_cell)
    dept_cell = html.unescape(dept_cell).strip()
    # Clean up whitespace
    dept_cell = re.sub(r'\s+', ' ', dept_cell)

    # Last cell: date
    date_cell = cells[-1] if len(cells) >= 3 else ''
    date_cell = re.sub(r'<[^>]+>', '', date_cell).strip()

    # Build a readable title
    title = dept_cell.strip(' |').replace(' | ', ' - ')

    # Handle duplicate names by appending a counter
    if title in seen_names:
        seen_names[title] += 1
        title = f'{title} ({seen_names[title]})'
    else:
        seen_names[title] = 1

    jobs.append({
        'title': title,
        'pdf_href': pdf_href,
        'date': date_cell
    })

print(json.dumps(jobs))
" > "$OUTDIR/_jobs.json"

# Read the jobs and download PDFs
JOB_COUNT=$(python3 -c "import json; jobs=json.load(open('$OUTDIR/_jobs.json')); print(len(jobs))")
echo "Found $JOB_COUNT job listing(s)."
echo ""

if [[ "$JOB_COUNT" -eq 0 ]]; then
    echo "No jobs found. The page structure may have changed."
    exit 1
fi

# Download each PDF
python3 -c "
import json, os, re, subprocess

outdir = '$OUTDIR'
base_url = '$URL'
jobs = json.load(open(os.path.join(outdir, '_jobs.json')))

for i, job in enumerate(jobs, 1):
    title = job['title']
    href = job['pdf_href']
    date = job['date']

    # Resolve relative URL
    if href.startswith('http'):
        pdf_url = href
    elif href.startswith('/'):
        pdf_url = 'https://www.uni-marburg.de' + href
    else:
        pdf_url = base_url.rstrip('/') + '/' + href

    # Sanitize title for filename
    safe_title = re.sub(r'[^\w\s\-()]', '', title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())
    filename = f'{safe_title}.pdf'
    filepath = os.path.join(outdir, filename)

    print(f'  [{i}/{len(jobs)}] {title}')
    print(f'         Deadline: {date}')
    print(f'         -> {filename}')

    result = subprocess.run(
        ['curl', '-sL', '-o', filepath, pdf_url],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f'         ERROR downloading: {result.stderr}')
    else:
        # Verify it's actually a PDF
        with open(filepath, 'rb') as f:
            header = f.read(4)
        if header != b'%PDF':
            print(f'         WARNING: Downloaded file may not be a valid PDF')

print()
"

echo "All PDFs downloaded to: $OUTDIR/"
echo ""

# Search PDFs for the name
echo "=== Searching PDFs for \"$SEARCH_NAME\" ==="
echo ""
MATCHES=$(pdfgrep -ri "$SEARCH_NAME" "$OUTDIR"/ 2>/dev/null || true)

if [[ -n "$MATCHES" ]]; then
    echo "$MATCHES"
    echo ""

    # Send notification if --notify was set
    if [[ -n "$NOTIFY_TOPIC" ]]; then
        echo "Sending ntfy notification to topic: $NOTIFY_TOPIC"
        curl -s \
            -H "Title: Uni Job Match: $SEARCH_NAME" \
            -H "Priority: high" \
            -H "Tags: briefcase" \
            -d "$MATCHES" \
            "https://ntfy.sh/$NOTIFY_TOPIC" > /dev/null
    fi
else
    echo "(No matches found for \"$SEARCH_NAME\")"
fi

echo ""

# Cleanup if requested
if [[ "$CLEANUP" == true ]]; then
    echo "Cleaning up: removing $OUTDIR"
    rm -rf "$OUTDIR"
fi

echo "Done."
