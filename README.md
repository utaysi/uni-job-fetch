# Uni Job Fetch

A small tool that collects student assistant (SHK) job ads from the University of Marburg
website, keeps them all in one place, and lets you browse, search, and export them. It checks
the website for you, downloads any new ads as PDFs, and remembers everything it has seen so you
never have to go through the pages by hand.

You mainly do three things with it: **fetch** new ads, look at them in a **dashboard** or in
**Excel**, and (optionally) tidy up any details the tool could not read automatically.

## Setting it up

You only need to do this once.

### 1. Install Python

Install Python 3 (version 3.10 or newer) from
[python.org](https://www.python.org/downloads/windows/). In the installer, **tick the box
"Add python.exe to PATH"** before clicking install.

To check it worked, open **PowerShell** and type:

```powershell
py --version
```

You should see a version number.

### 2. Copy the project onto your PC

Copy the whole project folder (the one containing `jobs.py`) somewhere on your computer, for
example your Desktop. Everything the tool needs is already inside it.

### 3. Install the tool's dependencies

Open PowerShell, go into the project folder, and run:

```powershell
py -m pip install --no-index --find-links wheels -r requirements.txt
```

This installs everything from the included `wheels` folder, so it works without an internet
connection.

## Using it

The easiest way is to just run the tool and pick from the menu:

```powershell
py jobs.py
```

You can also run a single action directly:

```powershell
py jobs.py fetch          # check the website and download any new job ads
py jobs.py serve          # open the dashboard in your web browser
py jobs.py export-excel   # save all the ads into job_ads.xlsx
py jobs.py import-excel   # save your edits from job_ads.xlsx back into the tool
```

### The dashboard

`py jobs.py serve` opens a web page at http://localhost:8080 where you can browse every job ad,
filter by department and status, search across all the text, and click an ad to open its PDF.
The page only works while the command is running, so leave that PowerShell window open while you
use it.

### Fixing details in Excel

`py jobs.py export-excel` creates a file called `job_ads.xlsx` with one row per job ad. If the
tool could not read some details from an ad, that row is flagged in the **Needs Review** column.

To fix one:

1. Find the rows marked **Needs Review = yes**.
2. Open the PDF (the link is in the **PDF** column) and read the missing details.
3. Fill in the empty cells, add anything useful in **Notes**, then change **Needs Review** to `no`.
4. Run `py jobs.py import-excel` to save your changes back into the tool.

Your edits are kept safe and are never overwritten the next time you fetch. Always run
`import-excel` before exporting again so you do not lose any changes.

## More detail

Want to know how it works under the hood, run it fully offline, or have it check for new ads
automatically? See [docs/TECHNICAL.md](docs/TECHNICAL.md).

## Questions?

**Ugur Taysi**
Assistant Staff Council Member
taysiug@students.uni-marburg.de
