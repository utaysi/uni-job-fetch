# Task tracker

Shared task list for everyone (people and agents) working on this project. Read it at the start of a session and update it at the end. See [AGENTS.md](AGENTS.md) for the rules.

Status markers: `[ ]` to do, `[~]` in progress, `[x]` done. Put the newest session log entry at the top.

## In progress

- (nothing)

## To do

### Hosted dashboard: one-time setup (owner, needs Cloudflare and GitHub accounts)

Steps are described in detail in [docs/TECHNICAL.md](docs/TECHNICAL.md#one-time-setup).

- [ ] 1. Confirm the domain's nameservers point to Cloudflare.
- [ ] 2. `cd worker && npm ci && npx wrangler login`.
- [ ] 3. Create the D1 database (`npx wrangler d1 create uni-job-board`) and note its ID.
- [ ] 4. Create the private data repo from `data/` with the files from `deploy/`, and push it.
- [ ] 5. Create the Cloudflare API token and add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as data repo secrets.
- [ ] 6. Run the workflow once manually. Confirm GitHub runners can reach uni-marburg.de and the board answers "Forbidden".
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

### Scraper

- [ ] Two subpages now redirect to the university login page and are skipped on every fetch: University Computing Centre (`/de/hrz/aktuelles/nachrichten/2025/shk-hrz-2025-02`) and Center for Synthetic Microbiology (`/en/synmikro/jobs-1`). Find their current job pages and update `SUBPAGES` in `src/scrape.py`, or remove them. (Found 2026-11-16; this was already failing before the hardening.)

### Recurring

- [ ] Renew the fine-grained GitHub token before it expires (1 year after creation) and run `wrangler secret put GITHUB_TOKEN` again.

## Done

- [x] Decide hosting design: Cloudflare Worker with static assets and Access login, D1 for notes and tags, private GitHub data repo, daily GitHub Actions fetch. (2026-11-16)
- [x] Scraper: only `https` links on `uni-marburg.de`, redirects checked, size caps on pages and PDFs, two sources moved to `https`. (2026-11-16)
- [x] `build-site` command; local server serves `/api/jobs.json`, answers `/api/me` with no user, binds to 127.0.0.1 only. (2026-11-16)
- [x] Excel round-trip no longer carries Notes (notes live in the hosted dashboard). (2026-11-16)
- [x] Dashboard: script moved to `web/app.js`, all data escaped, Chart.js vendored, Google Fonts removed, "Last fetched", notes, tags, tag filter, Fetch now button. (2026-11-16)
- [x] Worker: Access token verification on every request, notes/tags/fetch API with limits, security headers, D1 schema, 22 tests. (2026-11-16)
- [x] Deployment templates in `deploy/` and hosting docs in `docs/TECHNICAL.md`. (2026-11-16)

## Session log

### 2026-11-16

- Planned and built the hosted dashboard (see Done). Verified with Worker tests, `wrangler dev` (everything 403 without a valid token), headless browser runs in hosted and local mode, a dry-run deploy, and a local import of the existing notes.
- Not yet verified: anything needing the owner's Cloudflare or GitHub accounts (see To do).
- Added this tracker, AGENTS.md, and CLAUDE.md (imports AGENTS.md so Claude Code loads it).
- Live scraper check after hardening: 73 ads found, same as before; two subpages redirect to a login page (see Scraper task).
