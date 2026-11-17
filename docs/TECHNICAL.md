# Technical notes

Background detail for Uni Job Fetch that most users do not need. For everyday use, see the
[README](../README.md).

## Project layout

```
src/      Python modules (run with `py src/jobs.py`)
web/      dashboard page (index.html, app.js, vendored Chart.js)
data/     jobs.db, pdfs/, wheels/, backup/ (all generated or vendored; for hosting, a private git repo)
worker/   Cloudflare Worker for the hosted dashboard (login check, notes/tags API, fetch button)
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

- **Notes** on each ad, signed with the author's name and time. Everyone can add notes; only the author can edit or delete their own.
- **Tags** on each ad: type a new one or pick an existing one, then filter the list by tag, or pick "No tags" to see only ads nobody has tagged yet. Selected tag filters combine with "or". A tag disappears once it is removed from every ad.
- **Last fetched**: when the job list was last updated.
- **Fetch now**: starts an extra fetch. All council members share 3 per day, which reset at midnight Berlin time.

Clicking an ad on the hosted dashboard opens its notes and tags. The PDF button opens the ad itself.

### What lives where

| Place | Contents |
| --- | --- |
| Public code repo (this one) | Code only: scraper, dashboard, Worker, database schema, deployment templates. No data, secrets, domain or login settings. |
| Private data repo | `jobs.db`, `pdfs/`, a daily `annotations.sql` backup of notes and tags, `wrangler.toml` (domain and login settings), and the workflow that fetches and deploys. |
| GitHub Actions | Runs the workflow on temporary machines: once a day, and when someone presses Fetch now. |
| Cloudflare | Serves the dashboard and PDFs, enforces the login (Cloudflare Access), runs the Worker, and stores notes and tags (D1 database). |

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

7. **Turn on the login.**
   - In Cloudflare, open Workers & Pages > uni-job-board and enable **Cloudflare Access** for this Worker, covering production and previews.
   - Set the login method to **One-time PIN**.
   - Add an **Allow** policy whose Include rule is **Emails**, listing each council member's address. Never use "Everyone" or an email domain rule, or anyone with such an address could get in.
   - Copy the application's **AUD tag** and your **team domain** (`<your-team>.cloudflareaccess.com`, found in Zero Trust settings) into `TEAM_DOMAIN` and `POLICY_AUD` in `data/wrangler.toml`.
   - Commit, push, and run the workflow again. The board now asks for an email and shows the dashboard after the code is entered.

8. **Enable the Fetch now button.**
   - On GitHub, go to Settings > Developer settings > Fine-grained tokens > Generate new token.
   - Repository access: **Only select repositories** > the data repo. Permissions: **Actions: Read and write**, nothing else. Expiration: 1 year (set a reminder to renew it).
   - Then, from `worker/`:

   ```bash
   npx wrangler secret put GITHUB_TOKEN -c ../data/wrangler.toml
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

- **Adding or removing council members:** edit the email list in the Access policy. It takes effect immediately; nothing needs redeploying.
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
