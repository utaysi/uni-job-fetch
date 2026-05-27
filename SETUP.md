> Author: 
**Ugur Taysi**  
Assistant Staff Council Member  
taysiug@students.uni-marburg.de

# Windows Setup

## 1. Install Python

Install Python 3 from [python.org](https://www.python.org/downloads/windows/) (or the
Microsoft Store). During the installer, tick **"Add python.exe to PATH"**. This also installs
the `py` launcher.

Verify:

```powershell
py --version
```

## 2. Install dependencies

From the project folder:

```powershell
py -m pip install -r requirements.txt
```

## 3. Usage

All features live in `jobs.py`:

```powershell
# Scrape every page, download the PDFs, and search them for a name
py jobs.py fetch --name Matthias

# Same, plus a phone push notification on a match
py jobs.py fetch --name Matthias --notify YOUR_TOPIC

# List everything fetched so far (filter / open individual PDFs)
py jobs.py view
py jobs.py view --latest --source Psychology
py jobs.py view --search Chemistry
py jobs.py view --open 3            # opens PDF #3 in your default viewer

# Rebuild jobs_data.json for the dashboard
py jobs.py generate-data

# Build data and serve the dashboard at http://localhost:8080
py jobs.py serve
```

## 4. Notifications (ntfy)

Pick any topic name and pass it with `--notify`. Install the
[ntfy app](https://ntfy.sh) on your phone and subscribe to the same topic to receive a push
whenever your name is found in a listing.

## 5. Scheduling with Task Scheduler

To check for new listings automatically, create a scheduled task. Run this in an
**Administrator** PowerShell (adjust the path to where you cloned the project and your topic):

```powershell
schtasks /create /tn "UniJobFetch" /sc minute /mo 15 ^
  /tr "py C:\path\to\uni-job-fetch\jobs.py fetch --notify YOUR_TOPIC --keep-hourly"
```

`--keep-hourly` keeps the top-of-hour fetch folder and cleans up the in-between runs, so you
get notified every 15 minutes without accumulating dozens of folders per hour.

Manage the task:

```powershell
schtasks /run    /tn "UniJobFetch"     # run it now to test
schtasks /query  /tn "UniJobFetch"     # show status
schtasks /delete /tn "UniJobFetch" /f  # remove it
```

Each fetch is saved as a timestamped folder inside a `jobs/` directory next to `jobs.py`, and
`jobs_data.json` is written alongside `jobs.py`. These paths are relative to the script, so the
task's working directory doesn't matter as long as the full path to `jobs.py` is in the command.
