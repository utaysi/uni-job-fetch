#!/usr/bin/env bash
set -euo pipefail

# Uni Marburg student job fetcher
# Fetches all student assistant job PDFs from the main page and all department subpages,
# then searches them for a name.

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

# Fetch all pages and extract jobs in one Python call
python3 -c "
import sys, os, re, json, html, subprocess, urllib.request

outdir = '$OUTDIR'
main_url = '$URL'

# Subpages to also fetch, with their display names
SUBPAGES = [
    ('https://www.uni-marburg.de/de/fb01/fachbereich/karriere/stellenausschreibungen', 'Department 01 Law'),
    ('https://www.uni-marburg.de/de/fb02/studium/karriere/career-center/ausschreibungen-fb02', 'Department 02 Economics'),
    ('https://www.uni-marburg.de/de/fb03/fachbereich/kontakt/stellenangebote', 'Department 03 Social Sciences and Philosophy'),
    ('https://www.uni-marburg.de/de/fb04/fachbereich/personen/stellenangebote', 'Department 04 Psychology'),
    ('https://www.uni-marburg.de/de/fb05/stellenausschreibungen', 'Department 05 Protestant Theology'),
    ('https://www.uni-marburg.de/de/fb06/ausschreibungen-stud-mitarbeiter-innen', 'Department 06 History and Cultural Studies'),
    ('https://www.uni-marburg.de/de/fb09/stellenausschreibungen', 'Department 09 German Studies and Art History'),
    ('https://www.uni-marburg.de/de/fb10/fachbereich/stellenausschreibungen', 'Department 10 Foreign Language Philologies'),
    ('https://www.uni-marburg.de/de/fb12/fachbereich/dekanat/wirtschaftsverwaltung/ausschreibungen-fuer-hilfskraefte', 'Department 12 Mathematics and Computer Science'),
    ('https://www.uni-marburg.de/de/fb13/fachbereich/dekanat/wpv/ausschreibungen-des-fb-physik', 'Department 13 Physics'),
    ('https://www.uni-marburg.de/de/fb15/fachbereich/dekanat-verwaltung/aktuelle-stellenausschreibungen', 'Department 15 Chemistry'),
    ('https://www.uni-marburg.de/de/fb16/bewerbung', 'Department 16 Pharmacy'),
    ('https://www.uni-marburg.de/de/fb17/fachbereich/personen/stellenangebote', 'Department 17 Biology'),
    ('https://www.uni-marburg.de/de/fb19/fachbereich/stellenangebote', 'Department 19 Geography'),
    ('https://www.uni-marburg.de/de/fb21/fachbereich/personen/stellenausschreibungen', 'Department 21 Educational Sciences'),
    ('https://www.uni-marburg.de/de/cnms/centrum/stellenangebote', 'Center for Near and Middle Eastern Studies (CNMS)'),
    ('https://www.uni-marburg.de/de/ub/ueber-uns/karriere-und-ausbildung/studentische-hilfskraftstellen', 'University Library'),
    ('https://www.uni-marburg.de/de/hrz/aktuelles/nachrichten/2025/shk-hrz-2025-02', 'University Computing Centre'),
    ('http://www.uni-marburg.de/grk1782/offenestellen', 'Research Training Group Functionalization of Semiconductors'),
    ('https://www.uni-marburg.de/en/synmikro/jobs-1', 'Center for Synthetic Microbiology'),
    ('https://www.uni-marburg.de/de/fotomarburg/ueberuns/stellenangebote', 'Image archive Photo Marburg'),
    ('https://www.uni-marburg.de/de/genderzukunft/zentrum/stellen', 'Center for Gender Studies and Feminist Futures Research'),
    ('http://www.uni-marburg.de/botgart/aktuelles/news/', 'Botanical garden'),
    ('https://www.uni-marburg.de/de/zfl/stellenausschreibungen', 'Center for Teacher Education'),
    ('https://www.uni-marburg.de/de/konfliktforschung/zentrum/profil/stellenauschreibungen', 'Center for Conflict Research'),
    ('https://www.uni-marburg.de/de/icwc/zentrum/stellenausschreibungen', 'International Centre for the Study of War Crimes Trials (ICWC)'),
    ('https://www.uni-marburg.de/en/microcosm-earth/about-us/join-us', 'Future Center Microcosm Earth'),
    ('https://www.uni-marburg.de/de/mcdci/zentrum/stellenangebote', 'Marburg Center for Digital Culture and Infrastructure (MCDCI)'),
    ('https://www.uni-marburg.de/de/mcaw/aktuelles/nachrichten/eine-stelle-als-studentische-hilfskraft-zu-besetzen-20-std-monat-nachwuchsgruppe_september', 'Marburg Center for the Ancient World (MCAW)'),
]

def fetch_page(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  WARNING: Could not fetch {url}: {e}', file=sys.stderr)
        return None

def extract_main_page_jobs(content):
    jobs = []
    seen_names = {}
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL)
    for row in rows:
        pdf_match = re.search(r'href=[\"\\x27]([^\"\\x27]*\.pdf)[\"\\x27]', row)
        if not pdf_match:
            continue
        pdf_href = pdf_match.group(1)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 2:
            continue
        dept_cell = cells[0]
        dept_cell = re.sub(r'<br\s*/?>', ' | ', dept_cell)
        dept_cell = re.sub(r'<[^>]+>', '', dept_cell)
        dept_cell = html.unescape(dept_cell).strip()
        dept_cell = re.sub(r'\s+', ' ', dept_cell)
        date_cell = cells[-1] if len(cells) >= 3 else ''
        date_cell = re.sub(r'<[^>]+>', '', date_cell).strip()
        title = dept_cell.strip(' |').replace(' | ', ' - ')
        if title in seen_names:
            seen_names[title] += 1
            title = f'{title} ({seen_names[title]})'
        else:
            seen_names[title] = 1
        jobs.append({
            'title': title,
            'pdf_href': pdf_href,
            'date': date_cell,
            'source': 'Main Page'
        })
    return jobs

def extract_subpage_jobs(content, source_name, page_url):
    jobs = []
    seen_names = {}
    # Find all PDF links in the page
    for pdf_href in re.findall(r'href=[\"\\x27]([^\"\\x27]*\.pdf)[\"\\x27]', content):
        # Try to find a title/label near the link
        # Look for the anchor text
        anchor_pattern = re.escape(pdf_href).replace(r'\.', r'[.]') 
        anchor_match = re.search(r'href=[\"\\x27]' + anchor_pattern + r'[\"\\x27][^>]*>([^<]*)', content)
        link_text = ''
        if anchor_match:
            link_text = html.unescape(anchor_match.group(1).strip())
            link_text = re.sub(r'\s+', ' ', link_text)
        
        # Try to find a date near the link (look in surrounding context)
        date_str = ''
        if anchor_match:
            start = anchor_match.start()
            context = content[max(0, start-500):min(len(content), start+500)]
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', context)
            if date_match:
                date_str = date_match.group(1)
        
        # Use link text as title, or fall back to filename
        if link_text:
            title = link_text
        else:
            title = os.path.basename(pdf_href).replace('.pdf', '').replace('_', ' ')
        
        if title in seen_names:
            seen_names[title] += 1
            title = f'{title} ({seen_names[title]})'
        else:
            seen_names[title] = 1
        
        jobs.append({
            'title': title,
            'pdf_href': pdf_href,
            'date': date_str,
            'source': source_name
        })
    return jobs

all_jobs = []

# Fetch main page
print('Fetching Main Page...', file=sys.stderr)
main_html = fetch_page(main_url)
if main_html:
    main_jobs = extract_main_page_jobs(main_html)
    all_jobs.extend(main_jobs)
    print(f'  Found {len(main_jobs)} job(s) on Main Page', file=sys.stderr)

# Fetch each subpage
for subpage_url, source_name in SUBPAGES:
    print(f'Fetching {source_name}...', file=sys.stderr)
    subpage_html = fetch_page(subpage_url)
    if subpage_html:
        sub_jobs = extract_subpage_jobs(subpage_html, source_name, subpage_url)
        all_jobs.extend(sub_jobs)
        print(f'  Found {len(sub_jobs)} job(s)', file=sys.stderr)

# Write all jobs to JSON
with open(os.path.join(outdir, '_jobs.json'), 'w') as f:
    json.dump(all_jobs, f, indent=2)

# Print summary to stdout
print(f'Total jobs found: {len(all_jobs)}')
" 2>&1 | tee "$OUTDIR/_fetch.log"

# Read the jobs count
JOB_COUNT=$(python3 -c "import json; jobs=json.load(open('$OUTDIR/_jobs.json')); print(len(jobs))")
echo ""
echo "Found $JOB_COUNT job listing(s) total."
echo ""

if [[ "$JOB_COUNT" -eq 0 ]]; then
    echo "No jobs found. The page structure may have changed."
    exit 1
fi

# Download each PDF
python3 -c "
import json, os, re, subprocess

outdir = '$OUTDIR'
jobs = json.load(open(os.path.join(outdir, '_jobs.json')))

for i, job in enumerate(jobs, 1):
    title = job['title']
    href = job['pdf_href']
    date = job.get('date', '')
    source = job.get('source', 'Unknown')

    # Resolve relative URL
    if href.startswith('http'):
        pdf_url = href
    elif href.startswith('/'):
        pdf_url = 'https://www.uni-marburg.de' + href
    else:
        pdf_url = href

    # Sanitize title for filename - include source to avoid collisions
    safe_source = re.sub(r'[^\w\s\-()]', '', source)
    safe_source = re.sub(r'\s+', '_', safe_source.strip())
    safe_title = re.sub(r'[^\w\s\-()]', '', title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())
    filename = f'{safe_source}__{safe_title}.pdf'
    filepath = os.path.join(outdir, filename)

    print(f'  [{i}/{len(jobs)}] [{source}] {title}')
    if date:
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
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'rb') as f:
                header = f.read(4)
            if header != b'%PDF':
                print(f'         WARNING: Downloaded file may not be a valid PDF')
        else:
            print(f'         WARNING: Downloaded file is empty or missing')

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
