# Task tracker

Shared task list for everyone (people and agents) working on this project. Read it at the start of a session and update it at the end. See [AGENTS.md](AGENTS.md) for the rules.

Status markers: `[ ]` to do, `[~]` in progress, `[x]` done. Put the newest session log entry at the top.

## In progress

- Hosted dashboard live verification (setup steps 1 to 10 finished on 2026-11-17).
- Daily run moved to 04:17 UTC; the data repo copy still needs to be committed and pushed, then check on 2026-11-18 that the scheduled run starts.

## To do

### Hosted dashboard: one-time setup (owner, needs Cloudflare and GitHub accounts)

Steps are described in detail in [docs/TECHNICAL.md](docs/TECHNICAL.md#one-time-setup).

- [x] 1. Confirm the domain's nameservers point to Cloudflare.
- [x] 2. `cd worker && npm ci && npx wrangler login`.
- [x] 3. Create the D1 database (`npx wrangler d1 create uni-job-board`) and note its ID. Created with `--jurisdiction eu` so notes and tags stay in the EU.
- [x] 4. Create the private data repo from `data/` with the files from `deploy/`, and push it. `wrangler.toml` filled in (domain, database ID, `GITHUB_REPO`); `TEAM_DOMAIN` and `POLICY_AUD` wait for step 7.
- [x] 5. Cloudflare API token created (Workers Scripts Write, Account Settings Read, D1 Write, Workers Routes Write on the one zone only; expires after 1 year) and both secrets set in the data repo. (2026-11-16)
- [x] 6. Code repo and data repo pushed, first workflow run passed (2026-11-16): runners reach uni-marburg.de (74 ad links, 42 new, 30 still online, 42 newly offline, 2 subpages skipped), migration applied, data committed, Worker deployed to its custom domain. Every path answers 403, including API writes and a forged token, with the security headers present. The board hostname was changed before this first deploy (private config only).
- [x] 7. Zero Trust set up (Free plan); reusable Allow policy "Council members" with an email list attached to the Worker for all traffic (production and preview URLs, not "previews only"); `TEAM_DOMAIN` and `POLICY_AUD` set in the private config and redeployed (2026-11-16). Every path now redirects to the Access login. The AUD can be read from the `kid` parameter of that redirect. Menu names differ from docs/TECHNICAL.md: the Worker has its own Access tab, email-list policies must be created first under Access controls > Policies (the Worker dialog only offers pre-configured ones), and login methods are under Integrations > Identity providers. Owner login tested (2026-11-17): the code arrives, the dashboard and PDFs load, and a PDF link opened in a private window without login goes to the Access login.
- [x] 8. Fine-grained GitHub token (data repo only, Actions read and write) created and stored with `wrangler secret put GITHUB_TOKEN`; `wrangler secret list` shows it (2026-11-17). Fetch now started a "Dashboard fetch" run that passed in 5.5 minutes: 77 ad links, 3 new, 71 still online, 1 newly offline, 3 PDFs answered 403 (see Scraper). The owner confirmed the dashboard after the run: counter, "Last fetched" and the new ads.
- [x] 9. Skipped (2026-11-17): the 3 notes in `jobs.db` were test entries.
- [x] 10. Plain link to the board added on the personal website and works (2026-11-17). The short `/board` redirect address was skipped.

### Hosted dashboard: live verification (after setup)

- [~] `curl -I` on the board address redirects to the Access login; the `workers.dev` address does not serve the app. Board address checked 2026-11-17: `/`, `/api/jobs.json` and `/api/fetch-status` all answer 302 to the Access login. `workers.dev` still to check.
- [~] An allowlisted email receives a code and sees jobs, PDFs, "Last fetched", notes and tags; a non-allowlisted email gets no code. Jobs and PDFs confirmed by the owner (2026-11-17); "Last fetched", notes, tags and the non-allowlisted email still to check.
- [ ] With two accounts: authors show correctly, each can only edit their own notes, tags are shared and the tag filter works.
- [~] Fetch now counts down 3, 2, 1, 0, refuses a fourth, and stays disabled while a run is in progress. One click checked (2026-11-17): the run started on GitHub and passed, and the counter showed 2/3. The limit and the disabled state during a run are still to check.
- [~] The daily scheduled run did not start on 2026-11-17: the data repo has no `schedule` run at all, although the workflow is active and the cron is on `main`. GitHub warns that scheduled runs at the start of an hour can be dropped under load. Moved the cron from `0 5 * * *` to `17 4 * * *` (an hour earlier, off the full hour) in `deploy/update.yml` and the data repo copy (2026-11-17). Still to do: commit and push the data repo copy, then check on 2026-11-18 after about 06:30 Berlin time that a "Scheduled fetch" run appears (`gh run list -R <data repo> --event schedule`).
- [ ] Browser devtools show no requests to third-party hosts.
- [ ] Check the Cloudflare menu names in the setup docs against the real dashboard and correct them if needed.

### Dashboard

- [x] Show "First seen" under the deadline in each card, sort the list by first seen (newest first) by default, add sort options in the sidebar, and add a "No tags" filter. (2026-11-17)
- [ ] Check the new date column, sort options and "No tags" filter on the hosted dashboard with real tags. Deployed 2026-11-17 (code `e53ed65`); not yet looked at while logged in.
- [ ] 12 of 89 deadlines are not read as dates, so they show as plain text, get no countdown and sort last under "Deadline soonest": German month names (`07. Juli 2026`, `30. Juni 2026`) and free text (`mind. 2 Wochen`). The parser leaves `application_deadline_iso` empty for them too. Teach the parser (and `parseDate` in `web/app.js`) German month names, or send the ISO date to the page. (Found 2026-11-17.)
- [ ] On the deadline day itself the card already says "Expired", because the deadline counts from midnight at the start of that day. Decide whether the deadline day should still count as open (`deadlineStatus` and the deadline sort in `web/app.js`). (Found 2026-11-17.)

### Docs

- [ ] `docs/TECHNICAL.md` step 3: use `npx wrangler d1 create uni-job-board --jurisdiction eu` (what was actually run) and explain why. Also mention that npm 12 blocks the `esbuild` and `workerd` install scripts during `npm ci`, and that this is harmless (tests and bundling work without them).

### Scraper

- [ ] The main page (`MAIN_URL` in `src/scrape.py`) now redirects to `/de/universitaet/profil/universitaetskultur/karriere/stellenangebote/stud-und-wiss-hilfskraftstellen`, which contains no PDF links, so the main page yields 0 ads (subpages still work). Find where the central ads moved and update `MAIN_URL` and `discover_main_page`. (Found 2026-11-16 during the security fixes; same result with the old fetch code, so not caused by them.)
- [ ] Two subpages are skipped on every fetch (on 2026-11-16 they redirected to the university login page, on 2026-11-17 they answered 403): University Computing Centre (`/de/hrz/aktuelles/nachrichten/2025/shk-hrz-2025-02`) and Center for Synthetic Microbiology (`/en/synmikro/jobs-1`). Find their current job pages and update `SUBPAGES` in `src/scrape.py`, or remove them. (Found 2026-11-16; this was already failing before the hardening.)
- [ ] Three PDF links answer 403 on every fetch and count as errors: `fb13-shk-ag-witte-2021.pdf`, `fb13-shk-analyse-messdaten-ag-halbleiter-2026.pdf` (a newer `-1` version downloads fine) and `mediziner-praktikum-ws2223-zwei-stellen-neum.pdf`. Probably removed or protected files that are still linked. Decide whether 403 on a PDF should be a quiet skip instead of an error. (Found 2026-11-17.)

### Security hardening (from the 2026-11-16 audit, none blocking)

- [x] Scope `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `deploy/update.yml` (and the data repo copy) to the three `wrangler` steps only, instead of job-level `env`, so `pip install`, `npm ci` install scripts and the PDF scraper never see them. Pinned `requirements.txt` to the tested versions and added `requirements.lock` (all dependencies, with hashes) for the workflow.
- [x] Add `.dev.vars*`, `.env*` and `wrangler.toml` to the code repo `.gitignore`, so local Worker secrets or a copied deploy config cannot be committed by accident.
- [x] Decide on the commit author email: the owner keeps the personal Gmail address visible, no rewrite of authors. (2026-11-16)
- [x] Trim private infrastructure details from this tracker (private server name, DNS setup) and add a rule against them to AGENTS.md.
- [x] In `src/scrape.py`, reject off-domain redirects before following them.
- [ ] Optional, bigger: run the fetch and build in a separate job without secrets and deploy from a second job, so not even a hostile PDF exploiting PyMuPDF could read the Cloudflare token from runner memory. Needs care: the deploy job must not trust code or config produced by the fetch job.

### Recurring

- [ ] Renew the fine-grained GitHub token before it expires (1 year after creation) and run `wrangler secret put GITHUB_TOKEN` again.
- [ ] Renew the Cloudflare API token before it expires (1 year after creation, if created with an expiry) and update the `CLOUDFLARE_API_TOKEN` secret in the data repo. When it expires, the daily runs fail at the database migrations step and GitHub emails you.
- [ ] Every few months, update the pinned Python packages (PyMuPDF especially, since it parses downloaded PDFs): bump `requirements.txt`, regenerate `requirements.lock` (command in `docs/TECHNICAL.md`), and refresh `data/wheels/`.

## Done

- [x] Decide hosting design: Cloudflare Worker with static assets and Access login, D1 for notes and tags, private GitHub data repo, daily GitHub Actions fetch. (2026-11-16)
- [x] Scraper: only `https` links on `uni-marburg.de`, redirects checked, size caps on pages and PDFs, two sources moved to `https`. (2026-11-16)
- [x] `build-site` command; local server serves `/api/jobs.json`, answers `/api/me` with no user, binds to 127.0.0.1 only. (2026-11-16)
- [x] Excel round-trip no longer carries Notes (notes live in the hosted dashboard). (2026-11-16)
- [x] Dashboard: script moved to `web/app.js`, all data escaped, Chart.js vendored, Google Fonts removed, "Last fetched", notes, tags, tag filter, Fetch now button. (2026-11-16)
- [x] Worker: Access token verification on every request, notes/tags/fetch API with limits, security headers, D1 schema, 22 tests. (2026-11-16)
- [x] Deployment templates in `deploy/` and hosting docs in `docs/TECHNICAL.md`. (2026-11-16)

## Session log

### 2026-11-17 (dashboard: first seen, sorting, "No tags")

- Answered: every ad already has `first_seen` (time of the fetch that first found it, Berlin time) and `last_seen` in `jobs.db`, and both were already in `jobs.json`; the page just did not show `first_seen`. The server already sent ads newest first, but the page did not sort explicitly.
- Each card's date column now has two lines: "Deadline" (date and days left) and "First seen" (date; full time on hover). Column widths are fixed so dates line up from card to card; on phones the dates move to their own row under the title.
- New "Sort by" panel above Tags (both local and hosted): Newest first (default), Oldest first, Deadline soonest (upcoming soonest first, then expired, then no readable date), Title A-Z, Department A-Z. "Clear filters" keeps the chosen sort.
- New "No tags" chip in the Tags panel (hosted only) with a count; combines with tag chips by "or". After adding a tag to an ad under a tag filter, the card now stays on screen so more tags can be added; the list updates on the next filter or sort change (before, the whole list re-rendered right away).
- Fixed: on phones the page scrolled sideways by 177px (long department names and, after a window resize, the charts kept their grid columns from shrinking).
- README and `docs/TECHNICAL.md` updated.
- Verified with headless Chromium (Playwright) against a mock of the hosted API built on the local `jobs.db` (116 ads): every sort order checked over all cards; "No tags" shows 113 of 116, "No tags" plus a tag shows the union, tagging under "No tags" keeps the card and focus, the card leaves on the next sort change, "Clear filters" resets it; no horizontal overflow at 375px and 800px; no page errors. Also loaded the real `jobs.py serve` with the Worker's CSP added: 73 cards, no errors or CSP violations. Worker tests pass (22), `py_compile` passes.
- Committed in three steps (layout fix, first seen and sorting, "No tags") and pushed `master` (fast-forward, `e53ed65`) at the owner's request. Deployed by starting the data repo workflow by hand ("Manual run"): all steps passed, it checked out `e53ed65`, uploaded 3 changed files (page, script, job list), and committed the refreshed data. Fetch: 77 ad links, 0 new, 74 still online, 0 newly offline, the same 3 PDFs answered 403. The board, `/app.js` and `/api/jobs.json` still answer 302 to the Access login.
- Left alone: the other session's cron change in `deploy/update.yml` and in the data repo copy (both still uncommitted). The data repo on GitHub is now one data commit ahead of the local copy, so pull before pushing the workflow change there.
- Not verified: the new features on the live board while logged in (see the Dashboard task).

### 2026-11-17

- Owner confirmed the step 7 login works: the code arrives, the dashboard and PDFs load, and a PDF link opened in a private window without login goes to the Access login.
- Checked from outside with `curl`: the page, `/api/jobs.json` and `/api/fetch-status` all answer 302 to the Access login.
- Wrote detailed instructions for steps 8 to 10 and the live verification for the owner (in chat). Noted that the 3 notes in `jobs.db` look like test entries, so step 9 may be skipped.
- Step 8 done by the owner: `wrangler secret list` shows `GITHUB_TOKEN`, and Fetch now started a "Dashboard fetch" run. Watched it with `gh run watch`: it passed (all steps including migrations, backup, data commit and deploy). Fetch result: 77 ad links, 3 new, 71 still online, 1 newly offline; main page still 0 ads; two subpages and three PDFs answered 403.
- Found: no scheduled run on 2026-11-17 (`gh run list --event schedule` is empty). Added a task to check tomorrow and move the cron off the full hour if needed.
- Owner confirmed the dashboard after the fetch (counter 2/3, "Last fetched", new ads) and pulled the data repo. Step 9 skipped (test notes). Step 10: plain link on the personal website works; `/board` redirect skipped.
- At the owner's request, moved the daily run to `17 4 * * *` (an hour earlier, and off the full hour) in both workflow copies; checked that both files are identical and the YAML parses.
- Not verified: `workers.dev` address, the new schedule (needs the data repo push and tomorrow's run), the rest of the live verification.

### 2026-11-16 (hosting setup, part 2)

- Setup steps 5 to 7 done with the owner (details under the setup tasks): Cloudflare API token and data repo secrets, code and data repos pushed, first workflow run passed and deployed, Cloudflare Access turned on and the Worker redeployed with `TEAM_DOMAIN` and `POLICY_AUD`.
- Verified: every path answered 403 before Access, including API writes and a forged token, with the security headers present; after Access, every path redirects to the login.
- Found: Cloudflare menu names differ from `docs/TECHNICAL.md` (see step 7). Added a recurring task to renew the Cloudflare API token.

### 2026-11-16 (security audit before pushing the code repo)

- Audited the public code repo (working tree and full history, all 21 commits) and the private data repo before the owner pushes `master`. Findings are listed under "Security hardening".
- Verified: no hosting domain, D1 database ID, account ID, Access IDs, tokens, keys or private data in any public commit; only placeholders and `example.org` values. `data/`, `site/`, `job_ads.xlsx`, `docs/personal/`, `.wrangler/` are ignored and were never committed. Data repo is private, code repo public (checked with `gh`). Screenshots in `docs/images/` show only public job ad data and carry no metadata. `jobs_data.json` in old history holds only public ad titles and links.
- Verified code: Worker fails closed (403 without an RS256 Access JWT matching issuer and AUD), Origin check on every write, parameterized SQL, note ownership enforced server-side, `no-store` caching, CSP on HTML. Dashboard escapes all data and loads nothing third-party. Vendored Chart.js is byte-identical to npm `chart.js@4.4.7`. Lockfile resolves only from registry.npmjs.org. Pinned action SHAs match their release tags. Worker tests pass (22), `py_compile` passes.
- Already public before this session and unchanged: author name, role and student email in the README; the personal Gmail address as commit author email (owner decided to keep it).
- Fixed afterwards, with the owner's go-ahead: redirect targets are checked before following (`src/scrape.py`); Cloudflare secrets only on the three `wrangler` steps; `requirements.txt` pinned to the tested versions and `requirements.lock` with hashes used by the workflow (same change copied into the data repo workflow and committed there); `.gitignore` covers `.env*`, `.dev.vars*`, `wrangler.toml`; private infrastructure details removed from this tracker and a rule added to AGENTS.md.
- History cleanup: the not yet pushed commits were rewritten with `git filter-repo` so the old tracker text (private server name, DNS setup) no longer appears in any commit. Commits already on GitHub and author emails were left untouched, so a normal push still works. A backup bundle of the repo from before the rewrite sits next to the repo folder.
- Verified: redirect guard refuses off-domain, look-alike and plain `http` targets and follows university ones; live fetch of a subpage still works; the hash-locked install works on Python 3.12 and every wheel in `data/wheels/` matches a hash in the lock; workflow YAML parses with secrets only on the three steps; Worker tests pass (22); `py_compile` passes.
- Not verified: the changed workflow on a real GitHub runner (first run is setup step 6).
- Pushed the code repo (fast-forward, no force) and then the data repo, at the owner's request. A fresh clone from GitHub shows no private paths and none of the sensitive strings in any commit; the data repo is still private and its workflow matches `deploy/update.yml`.
- Found while testing: the main page moved and now yields 0 ads (see Scraper). Not caused by these changes.

### 2026-11-16 (hosting setup, part 1)

- Walked through the one-time setup with the owner. Step 1: nameservers are Cloudflare (checked with `dig`). Step 2: `npm ci`, owner ran `wrangler login`, verified with `wrangler whoami`. Step 3: D1 database created with `--jurisdiction eu`. Step 4: private data repo created on GitHub, initial commit pushed (`backup/`, `wheels/`, `.wrangler/` left out), `wrangler.toml` filled in. Step 5: `CLOUDFLARE_ACCOUNT_ID` secret set; API token not yet created.
- Verified: Worker tests pass (22) after `npm ci`; esbuild works despite npm 12 blocking its install script; `wrangler deploy --dry-run` with the filled-in config succeeds (after `build-site`); the data repo is private; the unpushed code commits contain no domain, database ID or account ID.
- Noted: the Worker custom domain creates its own DNS record on first deploy, which takes priority over any existing wildcard record.
- Not done: code repo push (owner chose to wait until step 6), steps 5 (token) to 10, docs update for the EU jurisdiction flag.

### 2026-11-16

- Planned and built the hosted dashboard (see Done). Verified with Worker tests, `wrangler dev` (everything 403 without a valid token), headless browser runs in hosted and local mode, a dry-run deploy, and a local import of the existing notes.
- Not yet verified: anything needing the owner's Cloudflare or GitHub accounts (see To do).
- Added this tracker, AGENTS.md, and CLAUDE.md (imports AGENTS.md so Claude Code loads it).
- Live scraper check after hardening: 73 ads found, same as before; two subpages redirect to a login page (see Scraper task).
