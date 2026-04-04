#!/usr/bin/env bash
set -euo pipefail

# Aggregate all jobs_* directories into a single jobs_data.json for the web UI
python3 -c "
import json, os, sys, glob

dirs = sorted(glob.glob('jobs_*'))
if not dirs:
    print('No jobs_* directories found.')
    sys.exit(1)

all_jobs = []
for d in dirs:
    jpath = os.path.join(d, '_jobs.json')
    if os.path.exists(jpath):
        with open(jpath) as f:
            jobs = json.load(f)
        for job in jobs:
            job['_dir'] = d
        all_jobs.extend(jobs)

with open('jobs_data.json', 'w') as f:
    json.dump(all_jobs, f, indent=2)

print(f'Aggregated {len(all_jobs)} jobs from {len(dirs)} fetches into jobs_data.json')
"
