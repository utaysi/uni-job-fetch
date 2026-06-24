> Author:
**Ugur Taysi**
Assistant Staff Council Member
taysiug@students.uni-marburg.de

# Windows Setup

## 1. Install Python

Install Python 3 (3.10 or newer) from [python.org](https://www.python.org/downloads/windows/)
(or the Microsoft Store). During the installer, tick **"Add python.exe to PATH"**. This also
installs the `py` launcher.

Verify:

```powershell
py --version
```

## 2. Install dependencies

The `wheels/` folder contains all dependencies for an offline install. From the project folder:

```powershell
py -m pip install --no-index --find-links wheels -r requirements.txt
```

If the machine is online you can instead just run:

```powershell
py -m pip install -r requirements.txt
```

## 3. How it works

All job ads live in a single deduplicated repository:

- `jobs.db` - the SQLite database (the single source of truth).
- `pdfs/` - every job-ad PDF, stored once, named
  `<first-seen-date>_<original-name>_<count>.pdf`.

Each ad is identified by the content hash of its PDF, so re-running a fetch never creates
duplicates. Ads still found online stay `Online`; ads that disappear from the website are flipped
to `Offline` (nothing is deleted).

## 4. Usage

Run with no arguments for an interactive menu:

```powershell
py jobs.py
```

Or use a subcommand directly (handy for scheduling):

```powershell
py jobs.py fetch          # scrape pages, download new ads, update statuses
py jobs.py export-excel   # write job_ads.xlsx from the database
py jobs.py import-excel   # fold edited job_ads.xlsx corrections back into the database
py jobs.py serve          # serve the dashboard at http://localhost:8080
```

## 5. The Excel workflow

`export-excel` writes `job_ads.xlsx` with one row per ad and a column per field. Ads where the
parser could not fill every field are flagged in the **Needs Review** column (and highlighted).

To correct an ad:

1. Filter the sheet by **Needs Review = yes**.
2. Open the linked PDF (the **PDF** column) and read the missing values.
3. Fix the cells, optionally add a note in **Notes**, and set **Needs Review** to `no`.
4. Run `py jobs.py import-excel` to save your corrections back into the database.

Your corrections are stored separately from the parsed values, so future fetches never overwrite
them. Keep `job_ads.xlsx` and the `pdfs/` folder together so the PDF links keep working.

> Note: `export-excel` refuses to overwrite an existing `job_ads.xlsx` unless you confirm (in the
> menu) or pass `--overwrite`. Always run `import-excel` before re-exporting so you do not lose
> un-imported edits.

## 6. The dashboard

`py jobs.py serve` starts a local web dashboard at http://localhost:8080 that reads the database
live. It only works while the server is running. Filter by department and status (Online / Offline
/ Needs Review), search across all fields, and click an ad to open its PDF.

## 7. Scheduling with Task Scheduler

To check for new listings automatically, create a scheduled task. Run this in an **Administrator**
PowerShell (adjust the path to where you cloned the project):

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
