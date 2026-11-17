# Technical notes

Background detail for Uni Job Fetch that most users do not need. For everyday use, see the
[README](../README.md).

## Project layout

```
src/      Python modules (run with `py src/jobs.py`)
web/      dashboard page (index.html, app.js, vendored Chart.js)
data/     jobs.db, pdfs/, wheels/, backup/ (all generated or vendored; for hosting, a private git repo)
tests/    Python unit tests (deadline detection)
worker/   Cloudflare Worker for the hosted dashboard (login check, notes/tags/review/deadline API, fetch button)
deploy/   templates for the private data repo (wrangler config, workflow, .gitignore)
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

## How deadlines are read

`src/deadline.py` decides each ad's application deadline. It starts with the value under "Bewerbungsfrist" in the ad's labelled box and checks it against the ad's full text:

- **Date**: a date in the box, after a label in the text ("Bewerbungsfrist: 25. August 2025"), or in the application sentence ("senden Sie bitte bis zum 25.11.2026"). Numeric dates, German and English month names (also abbreviated) and dates without a year are understood. A date in the text wins over "2 Wochen" in the box. Contract periods ("befristet bis zum ...") and date ranges are not taken for the deadline.
- **Period after posting** ("mind. 2 Wochen" with no date anywhere): the dashboard shows an estimate, that many days after the ad was first seen, marked with `~`.
- **No deadline**: either the ad says applications are taken any time ("laufend", "jederzeit", "Dauerausschreibung", "in den kommenden Wochen", "immer wieder ... gesucht"), or it gives no deadline at all. Hover over "No deadline" on the dashboard to see which.
- **Unknown**: the PDF is a scanned image without text, so nothing can be read. Open the PDF to check.

Every fetch re-reads the box of every stored PDF and runs the detection again, so improvements reach older ads too (this takes well under a second). A deadline corrected in Excel is kept as you wrote it. On the hosted dashboard, a deadline corrected by a council member takes the place of both. The tests in `tests/test_deadline.py` cover each kind of ad that was misread before; run them with `.venv/bin/python -m unittest discover -s tests`.

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

`requirements.txt` pins exact versions that match the offline wheels. The hosted workflow installs from `requirements.lock` instead, which also pins every indirect dependency and checks each download against a stored hash. After changing a version in `requirements.txt`, regenerate the lock file with `uv pip compile requirements.txt --universal --generate-hashes -o requirements.lock`.

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

## Hosting the dashboard online

The dashboard can be hosted at an address like `board.example.org`, so that staff council members can open it from anywhere after logging in. Nothing runs on your own server: GitHub runs the daily fetch, and Cloudflare serves the page and handles the login. Both are used within their free plans.

The hosted version adds features the local dashboard does not have:

- **Notes** on each ad, signed with the author's name and time. Everyone can add notes; only the author can edit or delete their own. Ads with notes show a note icon with the number of notes next to the title.
- **Deadline corrections**: in the opened ad, anyone can set the deadline to another date or to "No deadline", and go back to the detected one with "Use detected". A corrected deadline shows a pencil next to "Deadline" on the card, and its tooltip says who set it and what was detected.
- **Needs review** mark: anyone can set it on an ad or remove it, from the opened ad. This overrides the mark the parser (or the Excel round-trip) set, and the ad shows who changed it last.
- **Tags** on each ad: type a new one or pick an existing one, then filter the list by tag, or pick "No tags" to see only ads nobody has tagged yet. Selected tag filters combine with "or". A tag disappears once it is removed from every ad.
- **Last fetched**: when the job list was last updated.
- **Fetch now**: starts an extra fetch. All council members share 3 per day, which reset at midnight Berlin time.

Clicking an ad on the hosted dashboard opens its deadline, review mark, tags and notes. The PDF button opens the ad itself.

### What lives where

| Place | Contents |
| --- | --- |
| Public code repo (this one) | Code only: scraper, dashboard, Worker, database schema, deployment templates. No data, secrets, domain or login settings. |
| Private data repo | `jobs.db`, `pdfs/`, a daily `annotations.sql` backup of notes, tags, review marks and deadline corrections, `wrangler.toml` (domain and login settings), and the workflow that fetches and deploys. |
| GitHub Actions | Runs the workflow on temporary machines: once a day, and when someone presses Fetch now. |
| Cloudflare | Serves the dashboard and PDFs, enforces the login (Cloudflare Access), runs the Worker, and stores notes, tags, review marks and deadline corrections (D1 database). |

### How it is secured

- **Login before anything else.** Cloudflare Access asks for an email address, sends a one-time code, and only lets in addresses on your allowlist. The Access policy is attached to the Worker itself, so it covers every address the Worker has.
- **Second check in the Worker.** The Worker verifies Cloudflare's signed login token on every request, including the page, the data and each PDF. Without a valid token it answers 403. This also holds if Access were ever switched off or misconfigured, and until Access is set up at all.
- **No other addresses.** The `*.workers.dev` address and preview URLs are disabled.
- **Safe writes.** Changes must come from the dashboard itself (Origin check) as JSON, and all database queries use bound parameters. Notes are limited to 2,000 characters and tags to 30. Each person can make up to 300 changes a day.
- **No script injection.** Everything from the ads or from users is escaped before it is shown, and a strict Content Security Policy only allows the dashboard's own scripts. The page loads nothing from other websites.
- **Narrow fetcher.** The scraper only downloads `https` links on `uni-marburg.de`, checks every redirect before following it, caps every download (5 MB per page, 25 MB per PDF), and runs on a temporary GitHub machine.
- **Small secrets.** The Fetch now button uses a GitHub token that can only start and view workflow runs in the data repo. It cannot read or change code or data.
- **Secrets only where needed.** In the daily workflow, the Cloudflare token is passed only to the three `wrangler` steps, not to the steps that install packages or read downloaded PDFs. Python packages are installed from `requirements.lock` with pinned hashes, so a newly published (possibly malicious) package version never runs next to the secrets.

### One-time setup

You need a Cloudflare account that manages your domain, a GitHub account, and Node.js 22 or newer. Commands run from the project root unless noted.

1. **Check that your domain is on Cloudflare.** In the Cloudflare dashboard the domain should show as Active. Alternatively, `dig NS example.org +short` should list `*.ns.cloudflare.com` servers. A Worker custom domain only works on a domain whose nameservers point to Cloudflare.

2. **Install the Worker tools and log in to Cloudflare.**

   ```bash
   cd worker
   npm ci
   npx wrangler login
   ```

3. **Create the notes and tags database.** Still in `worker/`, run `npx wrangler d1 create uni-job-board` and note the `database_id` it prints.

4. **Create the private data repo.** On GitHub, create a new **private** repository, for example `uni-job-board-data`, with no README. Then turn your local `data/` folder into that repo:

   ```bash
   cd data
   git init -b main
   cp ../deploy/data.gitignore .gitignore
   cp ../deploy/wrangler.example.toml wrangler.toml
   mkdir -p .github/workflows
   cp ../deploy/update.yml .github/workflows/update.yml
   ```

   Edit `wrangler.toml`: set your domain (for example `board.example.org`), the `database_id` from step 3, and `GITHUB_REPO` (for example `yourname/uni-job-board-data`). Leave `TEAM_DOMAIN` and `POLICY_AUD` for step 7. Then commit and push:

   ```bash
   git add .gitignore wrangler.toml .github jobs.db pdfs
   git commit -m "Initial data"
   git remote add origin git@github.com:yourname/uni-job-board-data.git
   git push -u origin main
   ```

5. **Let GitHub deploy to Cloudflare.**
   - In Cloudflare, go to My Profile > API Tokens > Create Token and start from the **Edit Cloudflare Workers** template.
   - Add the permission **Account > D1 > Edit**.
   - Limit the account resources to your account and the zone resources to your domain.
   - In the data repo on GitHub, go to Settings > Secrets and variables > Actions and add two secrets: `CLOUDFLARE_API_TOKEN` (the token) and `CLOUDFLARE_ACCOUNT_ID` (shown on the Cloudflare dashboard overview).

6. **Run the workflow once.** In the data repo, open Actions > Update board > Run workflow. This fetches ads, commits the data, and deploys the Worker. Opening the board address now shows **Forbidden**. That is expected: the Worker refuses everyone until the login is set up.

7. **Turn on the login.** Menu names below are from the Cloudflare dashboard as of November 2026; Cloudflare renames things now and then.
   - **Set up Zero Trust (first time only).** Open **Zero Trust** in the Cloudflare dashboard, choose a team name (it becomes your team domain, `<your-team>.cloudflareaccess.com`) and pick the **Free** plan.
   - **Check the login method.** Under **Integrations > Identity providers**, make sure **One-time PIN** is available.
   - **Create the policy first.** Under **Access controls > Policies**, create a reusable policy, for example "Council members", with Action **Allow** and an Include rule **Emails** listing each council member's address. Never use "Everyone" or an email domain rule, or anyone with such an address could get in. Create it here first, because the Worker's Access dialog only offers existing policies.
   - **Attach it to the Worker.** Open **Workers & Pages > uni-job-board** and its **Access** tab. Enable Cloudflare Access for **all traffic (production and preview URLs)**, not "previews only", and select the policy.
   - **Read the team domain and AUD tag.** Every address on the board now redirects to the login, and the redirect carries both values:

     ```bash
     curl -sI https://board.example.org | grep -i '^location'
     ```

     The host of that address is your team domain, and the value after `kid=` is the AUD tag. Put them into `TEAM_DOMAIN` and `POLICY_AUD` in `data/wrangler.toml`.
   - Commit, push, and run the workflow again. The board now asks for an email and shows the dashboard after the code is entered.

8. **Enable the Fetch now button.**
   - On GitHub, open your profile picture > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
   - Resource owner: your account. Repository access: **Only select repositories** > the data repo. Permissions: **Actions: Read and write**, nothing else (GitHub adds **Metadata: Read-only** by itself). Expiration: 1 year (set a reminder to renew it).
   - Then, from `worker/`, run the command below and paste the token when asked. Do not put the token on the command line or in a file.

   ```bash
   npx wrangler secret put GITHUB_TOKEN -c ../data/wrangler.toml
   npx wrangler secret list -c ../data/wrangler.toml   # should list GITHUB_TOKEN
   ```

   The button appears after the next page load. Without the token the dashboard works, but the button stays hidden.

9. **Bring over existing notes (optional).** Older versions kept notes in `jobs.db`. To copy them into the hosted dashboard under your name (so you can edit them there), replace the email and run:

   ```bash
   sqlite3 data/jobs.db "SELECT 'INSERT INTO notes (job_hash, author, text, created_at) VALUES (' || quote(hash) || ', ''you@example.org'', ' || quote(notes) || ', ' || quote(strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) || ');' FROM jobs WHERE coalesce(notes, '') <> '';" > notes.sql
   cd worker && npx wrangler d1 execute DB --remote --file ../notes.sql -c ../data/wrangler.toml && rm ../notes.sql
   ```

   Use the same email you log in with, in lowercase.

10. **Link it from your website**, for example a `/board` page or menu link pointing to `https://board.example.org`.

### Day to day

- **Adding or removing council members:** in Zero Trust, open **Access controls > Policies**, edit the policy (for example "Council members") and change its email list. It takes effect immediately; nothing needs redeploying.
- **Correcting parsed fields with Excel:** `data/` is now a git repo, so pull first, then use the CLI as usual, then push:

  ```bash
  cd data && git pull && cd ..
  python src/jobs.py export-excel --overwrite
  # edit job_ads.xlsx
  python src/jobs.py import-excel
  cd data && git add jobs.db && git commit -m "Excel corrections" && git push
  ```

  If the push is rejected because the daily run committed in between, run `git fetch && git reset --hard origin/main` in `data/`, run `import-excel` again with the same file, then commit and push. Your corrections are in the Excel file, so nothing is lost.
- **Restoring notes and tags:** Cloudflare keeps 7 days of history (`npx wrangler d1 time-travel restore DB --timestamp=<ISO time> -c ../data/wrangler.toml` from `worker/`). For older states, every daily run saves `annotations.sql` in the data repo, so its git history holds a snapshot of each day.
- **Renewing the GitHub token:** create a new fine-grained token as in step 8 and run `wrangler secret put GITHUB_TOKEN` again.
- **If a scheduled run fails** (for example the university site is down), GitHub emails you. The next run tries again; data is only committed and deployed after a successful fetch.

### Testing the Worker

`cd worker && npm test` runs the API tests (notes, tags, permissions, limits, login token checks) against an in-memory database. They need no Cloudflare account.
