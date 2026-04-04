#!/usr/bin/env bash
set -euo pipefail

# View saved job ads across all jobs_* directories

ACTION="list"
FILTER_SOURCE=""
FILTER_DATE=""
SEARCH=""
OPEN=""
LATEST=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            FILTER_SOURCE="$2"
            shift 2
            ;;
        --date)
            FILTER_DATE="$2"
            shift 2
            ;;
        --search)
            SEARCH="$2"
            shift 2
            ;;
        --open)
            OPEN="$2"
            shift 2
            ;;
        --latest)
            LATEST=true
            shift
            ;;
        *)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --source <name>   Filter by source (e.g. 'Main Page', 'Department 04 Psychology')"
            echo "  --date <date>     Filter by deadline date (e.g. '05.04.2026')"
            echo "  --search <term>   Search in job titles"
            echo "  --open <num>      Open the PDF for job #<num> (from list output)"
            echo "  --latest          Show only jobs from the most recent fetch"
            exit 1
            ;;
    esac
done

# Collect all jobs from all jobs_* directories
python3 -c "
import json, os, sys, glob, subprocess

dirs = sorted(glob.glob('jobs_*'))
if not dirs:
    print('No jobs_* directories found.')
    sys.exit(0)

all_jobs = []
for d in dirs:
    jpath = os.path.join(d, '_jobs.json')
    if os.path.exists(jpath):
        with open(jpath) as f:
            jobs = json.load(f)
        for job in jobs:
            job['_dir'] = d
            all_jobs.append(job)

# Apply --latest filter
latest_only = $( [[ "$LATEST" == true ]] && echo "True" || echo "False" )
if latest_only and dirs:
    latest_dir = dirs[-1]
    all_jobs = [j for j in all_jobs if j['_dir'] == latest_dir]

# Apply --source filter
filter_source = '''$FILTER_SOURCE'''
if filter_source:
    all_jobs = [j for j in all_jobs if filter_source.lower() in j.get('source', '').lower()]

# Apply --date filter
filter_date = '''$FILTER_DATE'''
if filter_date:
    all_jobs = [j for j in all_jobs if filter_date in j.get('date', '')]

# Apply --search filter
search = '''$SEARCH'''
if search:
    all_jobs = [j for j in all_jobs if search.lower() in j.get('title', '').lower() or search.lower() in j.get('source', '').lower()]

# Check --open
open_num = '''$OPEN'''
if open_num:
    idx = int(open_num) - 1
    if 0 <= idx < len(all_jobs):
        job = all_jobs[idx]
        d = job['_dir']
        filename = job.get('filename', '')
        filepath = os.path.join(d, filename)
        if os.path.exists(filepath):
            subprocess.run(['xdg-open', filepath])
            print(f'Opened: {filepath}')
        else:
            print(f'PDF not found: {filepath}')
    else:
        print(f'Invalid job number: {open_num} (total: {len(all_jobs)})')
    sys.exit(0)

# Print list
print(f'=== Saved Jobs ({len(all_jobs)} total from {len(dirs)} fetches) ===')
print()

for i, job in enumerate(all_jobs, 1):
    source = job.get('source', 'Unknown')
    title = job['title']
    date = job.get('date', '')
    d = job['_dir']
    
    print(f'  [{i:3d}] [{source}]')
    print(f'         {title}')
    if date:
        print(f'         Deadline: {date}')
    print(f'         Fetch: {d}')
    print()
"
