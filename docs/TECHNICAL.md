# Technical notes

Background detail for Uni Job Fetch that most users do not need. For everyday use, see the
[README](../README.md).

## How the store works

All job ads live in a single deduplicated repository:

- `jobs.db` - the SQLite database (the single source of truth).
- `pdfs/` - every job-ad PDF, stored once, named
  `<first-seen-date>_<original-name>_<count>.pdf`.

Each ad is identified by the content hash of its PDF, so re-running a fetch never creates
duplicates. Ads still found online stay `Online`; ads that disappear from the website are flipped
to `Offline` (nothing is deleted).

Your manual corrections from Excel are stored separately from the parsed values, so future
fetches never overwrite them. Keep `job_ads.xlsx` and the `pdfs/` folder together so the PDF
links keep working.

## Installing dependencies (online vs offline)

The `wheels/` folder contains all dependencies for an offline install. From the project folder:

```powershell
py -m pip install --no-index --find-links wheels -r requirements.txt
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
  /tr "py C:\path\to\uni-job-fetch\jobs.py fetch"
```

Manage the task:

```powershell
schtasks /run    /tn "UniJobFetch"     # run it now to test
schtasks /query  /tn "UniJobFetch"     # show status
schtasks /delete /tn "UniJobFetch" /f  # remove it
```

The database and `pdfs/` folder live next to `jobs.py`, and all paths are relative to the script,
so the task's working directory does not matter as long as the full path to `jobs.py` is correct.
