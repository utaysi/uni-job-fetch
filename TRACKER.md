# Task tracker

Shared task list for everyone (people and agents) working on this project. Read it at the start of a session and update it at the end. See [AGENTS.md](AGENTS.md) for the rules.

Status markers: `[ ]` to do, `[~]` in progress, `[x]` done. Put the newest session log entry at the top.

## In progress

- Hosted dashboard: setup and live verification done (2026-11-17). Left for a future session: check that the scheduled run (04:17 UTC, first one due 2026-11-18) starts; see the live verification task.

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

- [x] `curl -I` on the board address redirects to the Access login; the `workers.dev` address does not serve the app. Board address checked 2026-11-17: `/`, `/api/jobs.json` and `/api/fetch-status` all answer 302 to the Access login. Owner confirmed in the Worker settings that only the custom domain is listed and workers.dev and preview URLs are disabled.
- [x] An allowlisted email receives a code and sees jobs, PDFs, "Last fetched", notes and tags; a non-allowlisted email gets no code. Confirmed by the owner (2026-11-17).
- [x] With two accounts: authors show correctly, each can only edit their own notes, tags are shared and the tag filter works. Confirmed by the owner (2026-11-17).
- [x] Fetch now counts down 3, 2, 1, 0, refuses a fourth, and stays disabled while a run is in progress. Owner checked (2026-11-17): every click started a run that passed, the counter reached 0/3 and the button stayed disabled. The server-side refusal of a fourth (429) is covered by the Worker tests.
- [~] The daily scheduled run did not start on 2026-11-17: the data repo has no `schedule` run at all, although the workflow is active and the cron is on `main`. GitHub warns that scheduled runs at the start of an hour can be dropped under load. The cron moved from `0 5 * * *` to `17 4 * * *` (an hour earlier, off the full hour), committed and pushed in both repos on 2026-11-17 (still no scheduled runs at 14:34 that day, as expected). To check in a future session: a "Scheduled fetch" run appears from 2026-11-18 on (`gh run list -R <data repo> --event schedule`). If not, look at GitHub's schedule docs and the repo's Actions settings.
- [x] Browser devtools show no requests to third-party hosts. Confirmed by the owner (2026-11-17).
- [x] Firefox console on the board showed two errors (2026-11-17): a CSP block of an inline script from `index.js:9263:27`, and "Content at <board> may not load or link to file:///". The served page has no inline script, no `index.js` and no `file:` link. The owner confirmed both disappear in a private window (extensions off), so they come from a browser extension. The CSP block is the policy working.
- [x] Devtools show "Source map error: request failed with status 404" for `chart.umd.js.map`, because the vendored `web/vendor/chart-4.4.7.umd.js` ends with a `sourceMappingURL` comment and the map file is not vendored. Harmless (only devtools ask for it); left as is by the owner's decision (2026-11-17).
- [x] Check the Cloudflare menu names in the setup docs against the real dashboard and correct them if needed. Step 7, step 8 and "Adding or removing council members" in `docs/TECHNICAL.md` rewritten from what the owner found during setup (2026-11-17).

### Dashboard

- [x] Show "First seen" under the deadline in each card, sort the list by first seen (newest first) by default, add sort options in the sidebar, and add a "No tags" filter. (2026-11-17)
- [ ] Check the new date column, sort options, "No tags" filter and note badges on the hosted dashboard with real tags. Deployed 2026-11-17 (code `e53ed65`, badges in `10d1022`); not yet looked at while logged in.
- [x] Deadlines with German month names (`07. Juli 2026`) and free text (`mind. 2 Wochen`) are read; see the deadline detection task below. (2026-11-17)
- [x] The deadline day itself counts as open and shows "Today"; "Expired" starts the day after. (2026-11-17)
- [x] Notes are easy to spot: a note icon with the number of notes next to the title replaces the small "1 note" text. (2026-11-17)
- [x] Deadline detection: analyzed all 39 ads (of 116) whose deadline was missing or unreadable and moved detection into `src/deadline.py` with unit tests. Every ad now gets a date, a period after posting (shown as an estimate), "No deadline" (rolling or not stated) or "Unknown" (scanned PDF). Every fetch re-checks all stored ads. (2026-11-17)
- [x] Needs review mark: anyone on the council can set or clear it in the opened ad (D1 table `review_flags`, `PUT /api/jobs/<hash>/review`); it overrides the parser's flag and shows who changed it last. (2026-11-17)
- [x] Check on the live board: the review mark (set and clear) and a few deadlines (the `elo-hilfskraft_26_11_2` ad says 25 Nov 2026, the physics "Dauerausschreibung" ads "No deadline"). Confirmed by the owner (2026-11-17). Note badges moved to the check above.
- [x] Deadline corrections: in the opened ad, anyone on the council can set another date or "No deadline", or go back with "Use detected" (D1 table `deadline_overrides`, `PUT`/`DELETE /api/jobs/<hash>/deadline`). The card shows a pencil next to "Deadline"; the tooltip says who set it and what was detected. (2026-11-17, deployed.)
- [x] On the live board: set a date on one ad, change it to "No deadline", then "Use detected". Confirmed by the owner (2026-11-17).
- [x] Departments filter: all departments start selected; clicking one while all are selected shows only that one, further clicks add or remove departments (removing the last one selects all), and an "All" row at the top selects all again. (2026-11-17)
- [x] Tab icon: a purple briefcase with a smiling face (`web/favicon.svg`, plus `favicon-32.png` and `apple-touch-icon.png`) instead of the browser's empty placeholder. (2026-11-17)
- [x] Show that the board fetches automatically every 24 hours: "Auto-fetch every 24 h" under the Fetch now counter, with a tooltip; shown on the hosted board only. (2026-11-17)
- [ ] On the live board: the Departments "All" row and single-select, the tab icon (also in Safari if anyone uses it), and the auto-fetch note.
- [x] Sidebar order: Departments, Tags, Sort by, Status, Deadline range (with "Clear filters" now at the bottom). (2026-11-17)
- [ ] One ad (`ausschreibung-praktikumsstelle`, a poster) is a scanned image with no text layer, so it shows "Unknown". It gives no deadline (checked by eye). Optional: OCR scanned PDFs with Tesseract (needs `tesseract-ocr` and `tesseract-ocr-deu` installed in the workflow, and the German language pack locally).
- [ ] Job-ID extraction picks up wrong text on several ads, for example `in`, `bitte ausfüllen`, `in einer PDF-Datei an` and IDs with `Umfang: 11h/Monat` appended. Analyze like the deadlines. (Found 2026-11-17.)

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
- [x] Second audit of the public code repo after the 2026-11-17 agent commits: nothing private found. Added `tools/leak-check.sh` and a "Public repo: nothing private, ever" section in AGENTS.md that requires it before every commit and push. (2026-11-17)
- [x] Commit `leak-patterns.txt` (extra private strings for the leak check) in the private data repo, so it survives a fresh checkout. (2026-11-17)
- [ ] Optional: install `tools/leak-check.sh` as a local `pre-push` hook (`.git/hooks/pre-push`), so a push is blocked even if an agent forgets the check. Hooks are not part of the repo, so this is per machine.

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
- [x] Workflow: a run that waited in the queue checked out stale data, so its data push failed and it did not deploy. The data checkout now uses the branch. (2026-11-17)

## Session log

### 2026-11-17 (second security audit, leak check)

- Audited the public code repo again after the agent commits since the 2026-11-16 audit (`2a6429b` to `cb92d66`, 19 commits, two of them not pushed yet) plus the working tree. Searched all 44 commits, every commit message and the working tree for the real board domain, D1 database ID, Access team domain and AUD tag (read from `data/wrangler.toml`), the private server name and DNS details (taken from the pre-rewrite backup bundle), the test account email from `data/annotations.sql`, and local paths; then for generic patterns: tokens, private keys, JWTs, 32-character hex IDs, UUIDs, IP addresses, email addresses. Read every doc, deploy and tracker change since the last audit by hand, and the comments in the new code.
- Result: nothing private in any public commit. Docs and the tracker use placeholders (`<board>`, `<data repo>`, `board.example.org`); the only hex values are pinned action SHAs; the only emails are placeholders and the owner's student email in README.md (public on purpose). The new icons carry no metadata. The one binary hit (in `docs/images/dashboard.png`, unchanged since June) is 3 random bytes of image data. The new Worker endpoints (review mark, deadline corrections) sit behind the unchanged Access check, use the origin check and parameterized SQL, and show council emails only to logged-in members, like notes. GitHub: code repo public with no releases, Actions runs, issues, pull requests or forks, and only `master`; data repo private. The data repo's history holds no stored secrets (only `secrets.*` references).
- Low, already public before this session, left as is: the example name for the private data repo in `docs/TECHNICAL.md` is the real repo's name (a private repo name gives no access), and the ntfy topic placeholder in early history (April 2026) contains the local user name.
- Added `tools/leak-check.sh`: checks unpushed commits, their messages and all uncommitted and untracked changes (or the whole history with `--all`) against the real values in `data/wrangler.toml`, extra private strings in `data/leak-patterns.txt`, and generic patterns. It masks private values as `<private>` in its output and refuses to run (exit 2) without `data/`. Created `data/leak-patterns.txt` locally in the data repo with the strings that are not in `wrangler.toml`.
- AGENTS.md: new section "Public repo: nothing private, ever" (what never to commit, placeholders, no raw `curl`/`gh` output in the tracker, run the check before every commit and push, what to do if something leaked), plus pointers under Commits, the project map and the checks.
- Verified: the check passes on the current state; `--all` reports only the README student email; in a scratch clone it caught planted leaks (the domain in upper case, a pasted Access redirect with team domain and AUD, a token, a home path, the server name in a commit message, the database ID in an uncommitted change, an untracked file) and exited 2 without `data/`.
- At the owner's request: committed the script, the AGENTS.md rule and this tracker update in the code repo and pushed `master`; committed `leak-patterns.txt` in the data repo (after a fast-forward pull of one data commit) and pushed it. The leak check passed before each commit. The parallel session's commits up to `d1bd759` were already on GitHub; `--all` afterwards still reports only the README student email, so they are clean too.
- Not done: the optional pre-push hook.

### 2026-11-17 (departments filter, tab icon, auto-fetch note)

- Owner confirmed on the live board: deadline corrections (date, "No deadline", "Use detected"), setting and clearing the review mark, `elo-hilfskraft_26_11_2` showing 25 Nov 2026, and the physics "Dauerausschreibung" ads showing "No deadline". Those tasks are marked done; the note badges check moved to the open date column check.
- Departments filter: an "All" row (total count, multicolor dot) at the top. With all selected, only "All" is highlighted; clicking a department shows only that one, further clicks add or remove departments, removing the last one selects all again, and picking every department one by one also ends at "All". The panel header shows "N of M" while narrowed. Rows work with Enter and Space. On reload, new departments join only an all-selected filter.
- Tab icon: purple briefcase with a smiling face in the page's colors, as SVG with a 32px PNG fallback and a 180px apple-touch icon; `build-site` copies all three.
- "Auto-fetch every 24 h" note with a refresh icon under the "N/3 left today" counter; the tooltip says it runs early in the morning (Berlin time) and does not count toward the limit. It shows on the hosted board even without the GitHub token (then without button and counter); the local dashboard shows neither.
- Also committed the earlier session's uncommitted `docs/TECHNICAL.md` rewrite of setup steps 7 and 8 (real Cloudflare and GitHub menu names), as its own docs commit.
- Verified: headless Chromium against a mock of the hosted API (Worker CSP added to the page) in three modes (hosted with fetch, hosted without token, local): every Departments click sequence above, keyboard, "Clear filters", card counts match the API data for each selection, the three icons answer 200 with the right types, the fetch controls show or hide as described, no horizontal scroll at 375px and 800px, no page errors or CSP violations. Icons checked by eye at 16, 32 and 180px. Real `jobs.py serve` serves the icons; `build-site` output contains them. Worker tests (28), Python tests (35) and `py_compile` pass.
- Pushed `master` (`08eacbe`) and deployed with a manual run of the data repo workflow, at the owner's request. The run passed in 5m43s: it checked out `08eacbe`, uploaded 6 changed files including the three icons, and the fetch found 74 ads still online and 0 newly offline. Afterwards `/`, `/favicon.svg`, `/app.js` and `/api/jobs.json` all answer 302 to the Access login.
- Not verified: the new features on the live board while logged in, and the icon in Safari.
- Later, at the owner's request: reordered the sidebar to Departments, Tags, Sort by, Status, Deadline range. Checked in headless Chromium (hosted and local: panel order, "Clear filters", no sideways scroll at 375px, no errors). Committed and pushed; not deployed, so it goes live with the next run (daily or Fetch now).

### 2026-11-17 (deadline corrections, deploys)

- Built deadline corrections for the hosted dashboard: migration `0003_deadline_overrides.sql` (kind `date` with a deadline, or `none`), `PUT /api/jobs/<hash>/deadline` (real dates from 2000 to 2100 only, origin check, daily write cap) and `DELETE` to go back to the detected deadline, corrections included in `/api/annotations`. The page uses a correction everywhere the deadline is used (card, countdown, deadline sort, range filter, timeline) and shows a Deadline section in the opened ad with the detected value, a date field, "No deadline" and "Use detected".
- Verified: Worker tests 28 pass (3 new: set, change, reset; validation including 30 February and years outside 2000 to 2100; origin check and write cap); Python tests and `py_compile` pass; browser tests against the mock API: set a date on a "No deadline" ad, the card shows the pencil and countdown, the deadline sort places it among upcoming dates, "No deadline" and "Use detected" work, a dated ad starts with its detected date, no sideways scroll at 375px; the earlier browser tests still pass; real `jobs.py serve` under the Worker CSP shows no errors.
- Deploys, at the owner's request: pushed the deadline, notes badge and review commits (`10d1022`). My manual run failed at "Save data": it had queued behind a "Fetch now" run and checked out the data commit from when it was started, so its push was rejected and it did not deploy (migration 0002 was applied before that). The owner's next "Fetch now" run deployed `10d1022` (re-check updated 23 deadlines). Fixed the workflow: the data checkout now uses the branch (`ref: ${{ github.ref }}`) in `deploy/update.yml` and the data repo copy.
- Committed the other session's cron change (04:17 UTC) together with the fix in both repos, at the owner's request; the two workflow copies are identical. Pushed both repos (code `8bb2253`) and deployed with a manual run: all steps passed, data checked out by branch, migration 0003 applied, 3 files uploaded. The board still answers 302 to the Access login.
- Not verified: the new features on the live board while logged in.

### 2026-11-17 (deadlines, notes badge, review mark)

- Deadline analysis: 39 of 116 ads had an empty or unreadable deadline. Causes: German month names in the box (5 ads); "laufend" or "jederzeit" in the box (3); "mind. 2 Wochen" or "2 Wochen" in the box while the text gives the real date (2) or only the period (1); the box reader taking the wrong line (1, the date was beside the label); an empty box with the date only in the application sentence ("bis 15.09.2026", without "zum") (1); physics standing vacancies whose box labels have no text layer ("Dauerausschreibung") (4); "jederzeit", "immer wieder ... gesucht", "in den kommenden Wochen" or "fortlaufend" in the text (4 more, overlapping); no deadline in the ad at all (18, mostly external internships; checked each for missed dates: only seminar dates, letter dates and work periods); one scanned PDF without text.
- Also found: one ad had a wrong stored date. The old fallback regex took "befristet bis zum 31.05.2027" (contract end) instead of "bis zum 25.11.2026". The new detection skips contract periods and date ranges.
- Built `src/deadline.py` (kinds: date, relative, rolling, none, unknown, text for manual corrections), used by the extractor, by a re-check of every stored ad at each fetch (re-reads each PDF's box: 0.5 s for 116 PDFs) and by the dashboard data (`deadline_kind`, `deadline_iso`, `deadline_days`). 35 unit tests in `tests/test_deadline.py`.
- Dashboard: deadline line shows the date, "~date" for an estimate, "No deadline" or "Unknown", with a tooltip quoting the ad; the deadline day shows "Today"; the deadline sort, range filter and timeline use the detected date. Note icon with count next to the title. Review section in the opened ad (hosted only) with a removable "Needs review" chip or a "Mark for review" button and who changed it last.
- Worker: migration `0002_review_flags.sql`, `PUT /api/jobs/<hash>/review` (boolean, origin check, daily write cap), flags included in `/api/annotations`. Tests now load all migrations; 25 pass.
- Verified: full re-extraction of all 116 PDFs changes no previously correct date (only the wrong one above); the re-check on a copy of `jobs.db` updates 23 ads and a second run changes none; browser tests (Playwright, mock API on the re-checked copy) for badges, every deadline kind, "Today" with the clock set to 25 Nov 2026, the deadline sort, setting and clearing the review mark, local read-only mode, no sideways scroll at 375px; real `jobs.py serve` under the Worker CSP shows no errors. The local `data/jobs.db` was not changed.
- Not verified: the live board (not deployed yet); the migration on the real D1 database.

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
- Live verification, confirmed by the owner: only the custom domain (workers.dev and previews disabled), notes, tags, a non-allowlisted email gets no code, two-account ownership and shared tags, and no third-party requests in devtools. Two Firefox console errors (inline script CSP block from `index.js`, `file:///` link) traced to something outside the page: the served HTML and scripts contain neither (see the live verification task).
- Owner confirmed the Fetch now limit (0/3, button disabled) and that the console errors are gone in a private window (an extension). One more devtools message: a 404 for Chart.js's source map (harmless, optional task added).
- Docs: rewrote setup steps 7 and 8 and the council members line in `docs/TECHNICAL.md` with the real Cloudflare and GitHub menu names, and how to read the team domain and AUD tag from the login redirect.
- The cron change was committed and pushed in both repos (in the parallel dashboard session).
- Owner checked the parallel session's newest features on the live board: review mark, deadlines and deadline corrections. Source map 404 closed as not worth fixing.
- Not verified: the new schedule (first run due 2026-11-18; owner checks in a future session).

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
