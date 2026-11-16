# Task tracker

Shared task list for everyone (people and agents) working on this project. Read it at the start of a session and update it at the end. See [AGENTS.md](AGENTS.md) for the rules.

Status markers: `[ ]` to do, `[~]` in progress, `[x]` done. Put the newest session log entry at the top.

## In progress

- Hosted dashboard one-time setup: steps 1 to 4 done, step 5 half done (see below).

## To do

### Hosted dashboard: one-time setup (owner, needs Cloudflare and GitHub accounts)

Steps are described in detail in [docs/TECHNICAL.md](docs/TECHNICAL.md#one-time-setup).

- [x] 1. Confirm the domain's nameservers point to Cloudflare.
- [x] 2. `cd worker && npm ci && npx wrangler login`.
- [x] 3. Create the D1 database (`npx wrangler d1 create uni-job-board`) and note its ID. Created with `--jurisdiction eu` so notes and tags stay in the EU.
- [x] 4. Create the private data repo from `data/` with the files from `deploy/`, and push it. `wrangler.toml` filled in (domain, database ID, `GITHUB_REPO`); `TEAM_DOMAIN` and `POLICY_AUD` wait for step 7.
- [~] 5. Create the Cloudflare API token and add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as data repo secrets. `CLOUDFLARE_ACCOUNT_ID` is set. Still to do: create the token (Edit Cloudflare Workers template plus Account > D1 > Edit) and add it as `CLOUDFLARE_API_TOKEN` in the GitHub web UI.
- [ ] 6. Before running: push this code repo (`master` is ahead of `origin/master`; the workflow checks out the code from GitHub). The owner wants to be asked right before the push. Then run the workflow once manually. Confirm GitHub runners can reach uni-marburg.de and the board answers "Forbidden".
- [ ] 7. Enable Cloudflare Access on the Worker (one-time PIN, email allowlist), then set `TEAM_DOMAIN` and `POLICY_AUD` and redeploy.
- [ ] 8. Create the fine-grained GitHub token (data repo only, Actions read and write) and `wrangler secret put GITHUB_TOKEN`.
- [ ] 9. Import the 3 existing notes from `jobs.db` into D1.
- [ ] 10. Add a `/board` link on the personal website.

### Hosted dashboard: live verification (after setup)

- [ ] `curl -I https://board.<domain>` redirects to the Access login; the `workers.dev` address does not serve the app.
- [ ] An allowlisted email receives a code and sees jobs, PDFs, "Last fetched", notes and tags; a non-allowlisted email gets no code.
- [ ] With two accounts: authors show correctly, each can only edit their own notes, tags are shared and the tag filter works.
- [ ] Fetch now counts down 3, 2, 1, 0, refuses a fourth, and stays disabled while a run is in progress.
- [ ] Browser devtools show no requests to third-party hosts.
- [ ] Check the Cloudflare menu names in the setup docs against the real dashboard and correct them if needed.

### Docs

- [ ] `docs/TECHNICAL.md` step 3: use `npx wrangler d1 create uni-job-board --jurisdiction eu` (what was actually run) and explain why. Also mention that npm 12 blocks the `esbuild` and `workerd` install scripts during `npm ci`, and that this is harmless (tests and bundling work without them).

### Scraper

- [ ] The main page (`MAIN_URL` in `src/scrape.py`) now redirects to `/de/universitaet/profil/universitaetskultur/karriere/stellenangebote/stud-und-wiss-hilfskraftstellen`, which contains no PDF links, so the main page yields 0 ads (subpages still work). Find where the central ads moved and update `MAIN_URL` and `discover_main_page`. (Found 2026-11-16 during the security fixes; same result with the old fetch code, so not caused by them.)
- [ ] Two subpages now redirect to the university login page and are skipped on every fetch: University Computing Centre (`/de/hrz/aktuelles/nachrichten/2025/shk-hrz-2025-02`) and Center for Synthetic Microbiology (`/en/synmikro/jobs-1`). Find their current job pages and update `SUBPAGES` in `src/scrape.py`, or remove them. (Found 2026-11-16; this was already failing before the hardening.)

### Security hardening (from the 2026-11-16 audit, none blocking)

- [x] Scope `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `deploy/update.yml` (and the data repo copy) to the three `wrangler` steps only, instead of job-level `env`, so `pip install`, `npm ci` install scripts and the PDF scraper never see them. Pinned `requirements.txt` to the tested versions and added `requirements.lock` (all dependencies, with hashes) for the workflow.
- [x] Add `.dev.vars*`, `.env*` and `wrangler.toml` to the code repo `.gitignore`, so local Worker secrets or a copied deploy config cannot be committed by accident.
- [x] Decide on the commit author email: the owner keeps the personal Gmail address visible, no rewrite of authors. (2026-11-16)
- [x] Trim private infrastructure details from this tracker (private server name, DNS setup) and add a rule against them to AGENTS.md.
- [x] In `src/scrape.py`, reject off-domain redirects before following them.
- [ ] Optional, bigger: run the fetch and build in a separate job without secrets and deploy from a second job, so not even a hostile PDF exploiting PyMuPDF could read the Cloudflare token from runner memory. Needs care: the deploy job must not trust code or config produced by the fetch job.

### Recurring

- [ ] Renew the fine-grained GitHub token before it expires (1 year after creation) and run `wrangler secret put GITHUB_TOKEN` again.
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

### 2026-11-16 (security audit before pushing the code repo)

- Audited the public code repo (working tree and full history, all 21 commits) and the private data repo before the owner pushes `master`. Findings are listed under "Security hardening".
- Verified: no hosting domain, D1 database ID, account ID, Access IDs, tokens, keys or private data in any public commit; only placeholders and `example.org` values. `data/`, `site/`, `job_ads.xlsx`, `docs/personal/`, `.wrangler/` are ignored and were never committed. Data repo is private, code repo public (checked with `gh`). Screenshots in `docs/images/` show only public job ad data and carry no metadata. `jobs_data.json` in old history holds only public ad titles and links.
- Verified code: Worker fails closed (403 without an RS256 Access JWT matching issuer and AUD), Origin check on every write, parameterized SQL, note ownership enforced server-side, `no-store` caching, CSP on HTML. Dashboard escapes all data and loads nothing third-party. Vendored Chart.js is byte-identical to npm `chart.js@4.4.7`. Lockfile resolves only from registry.npmjs.org. Pinned action SHAs match their release tags. Worker tests pass (22), `py_compile` passes.
- Already public before this session and unchanged: author name, role and student email in the README; the personal Gmail address as commit author email (owner decided to keep it).
- Fixed afterwards, with the owner's go-ahead: redirect targets are checked before following (`src/scrape.py`); Cloudflare secrets only on the three `wrangler` steps; `requirements.txt` pinned to the tested versions and `requirements.lock` with hashes used by the workflow (same change copied into the data repo workflow and committed there); `.gitignore` covers `.env*`, `.dev.vars*`, `wrangler.toml`; private infrastructure details removed from this tracker and a rule added to AGENTS.md.
- History cleanup: the not yet pushed commits were rewritten with `git filter-repo` so the old tracker text (private server name, DNS setup) no longer appears in any commit. Commits already on GitHub and author emails were left untouched, so a normal push still works. A backup bundle of the repo from before the rewrite sits next to the repo folder.
- Verified: redirect guard refuses off-domain, look-alike and plain `http` targets and follows university ones; live fetch of a subpage still works; the hash-locked install works on Python 3.12 and every wheel in `data/wheels/` matches a hash in the lock; workflow YAML parses with secrets only on the three steps; Worker tests pass (22); `py_compile` passes.
- Not verified: the changed workflow on a real GitHub runner (first run is setup step 6).
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
