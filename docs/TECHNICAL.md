# Technical notes

Background detail for Uni Job Fetch that most users do not need. For everyday use, see the
[README](../README.md).

## Project layout

```
src/      Python modules (run with `py src/jobs.py`)
web/      index.html dashboard
data/     jobs.db, pdfs/, wheels/, backup/ (all generated or vendored)
docs/     these notes
job_ads.xlsx   Excel export, kept at the project root
```

`jobs.py` changes the working directory to the project root (the parent of `src/`)
on startup, so all paths below are relative to the root regardless of where the
command was launched.

## How the store works

All job ads live in a single deduplicated repository:

- `data/jobs.db` - the SQLite database (the single source of truth).
- `data/pdfs/` - every job-ad PDF, stored once, named
  `<first-seen-date>_<original-name>_<count>.pdf`.

Each ad is identified by the content hash of its PDF, so re-running a fetch never creates
duplicates. Ads still found online stay `Online`; ads that disappear from the website are flipped
to `Offline` (nothing is deleted).

Your manual corrections from Excel are stored separately from the parsed values, so future
fetches never overwrite them. Keep `job_ads.xlsx` at the project root next to the `data/`
folder so the PDF links (which point at `data/pdfs/`) keep working.

## Installing dependencies (online vs offline)

The `data/wheels/` folder contains all dependencies for an offline install. From the project
folder:

```powershell
py -m pip install --no-index --find-links data/wheels -r requirements.txt
```

If the machine is online you can instead just run:

```powershell
py -m pip install -r requirements.txt
```

## Export safety

`export-excel` refuses to overwrite an existing `job_ads.xlsx` unless you confirm (in the menu)
or pass `--overwrite`. Always run `import-excel` before re-exporting so you do not lose
un-imported edits.

## Scheduling with Task Scheduler

To check for new listings automatically, create a scheduled task. Run this in an **Administrator**
PowerShell (adjust the path to where you put the project):

```powershell
schtasks /create /tn "UniJobFetch" /sc minute /mo 15 ^
  /tr "py C:\path\to\uni-job-fetch\src\jobs.py fetch"
```

Manage the task:

```powershell
schtasks /run    /tn "UniJobFetch"     # run it now to test
schtasks /query  /tn "UniJobFetch"     # show status
schtasks /delete /tn "UniJobFetch" /f  # remove it
```

The database and `data/pdfs/` folder live under the project root, and `jobs.py` resolves all
paths against that root, so the task's working directory does not matter as long as the full
path to `src\jobs.py` is correct.
