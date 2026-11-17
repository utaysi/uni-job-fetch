# Agent instructions

Instructions for coding agents working in this repository.

## Every session

1. **At the start**, read [TRACKER.md](TRACKER.md). Check what is in progress and what is next, and move the task you pick up to "In progress" (`[~]`). If the user asks for something that is not listed, add it first.
2. **While working**, commit in small, incremental steps: one logical change per commit (for example a fix, a feature, docs), not one large commit at the end.
3. **At the end**, update [TRACKER.md](TRACKER.md): set task statuses, add new follow-up tasks, and add a dated entry at the top of the session log with what was done, how it was verified, and anything left unverified or unfinished. Commit the tracker update.

## Commits

- For every commit, stage the changes and then call the `commit-message` skill (the `/commit-message` slash command) to write the message. Do not write commit messages by hand.
- Before any git operation, follow the user's own rules. If they require confirmation before committing or pushing, ask first.
- Run the leak check (next section) before every commit and every push.

## Public repo: nothing private, ever

This repository is **public**. Everything in it is public: files, commit messages, TRACKER.md and its session log. Deployment details live in the private data repo, checked out at `data/` (templates in `deploy/`).

- **Never commit** `data/`, `site/`, `job_ads.xlsx`, or any of these, in any file or commit message:
  - secrets and tokens of any kind;
  - the real deployment values: the board's domain, the D1 database ID, the Cloudflare account ID, the Access team domain and the AUD tag;
  - details of the owner's private infrastructure: server names, DNS setup;
  - council members' email addresses or names, and the content of notes, tags or anything else from D1 or `data/annotations.sql`;
  - absolute paths from the owner's machine (home folder, synced drive folders).
- **Use placeholders** instead: `<board>`, `<data repo>`, `board.example.org`, `alice@example.org`. This matters most when recording verification in TRACKER.md: describe the result ("302 to the Access login") instead of pasting raw output. A `curl -I` redirect contains the team domain and the AUD tag; `gh` output and run URLs contain the data repo's address.
- **Run `tools/leak-check.sh`** before every commit (after staging) and before every push. It checks the unpushed commits, their messages and all uncommitted changes against the real values in `data/wrangler.toml`, the extra private strings in `data/leak-patterns.txt`, and generic patterns (tokens, private keys, local paths, email addresses that are not placeholders). It prints private values as `<private>`; do not copy them out of the files it reads. Exit 0 means nothing was found. Exit 1: fix every finding before going on, or ask the owner if it is a false positive. Exit 2 (for example no `data/` checkout): the check did not run, so say so and do not report the changes as checked.
- `tools/leak-check.sh --all` checks the whole history. Its only expected finding is the owner's student email in README.md, which is public on purpose. The commit author email is also public, by the owner's decision.
- **If something leaked:** in commits that are not pushed yet, fix it before pushing (amend or rewrite those commits, with the owner's go-ahead). If it is already on GitHub, stop and tell the owner right away; never force-push on your own. A leaked secret must be rotated, not just removed.
- When a new kind of private value appears (a new server, a new account), ask the owner to add it to `data/leak-patterns.txt` in the private data repo, never to the check script or anywhere else in this repo.

## Project map

- `src/`: Python CLI (`python src/jobs.py`): scraping, PDF extraction, deadline detection (`deadline.py`), SQLite store, Excel round-trip, local server, `build-site`.
- `tests/`: Python unit tests (standard library `unittest`).
- `web/`: dashboard page (`index.html`, `app.js`, vendored Chart.js). Runs read-only locally and with notes, tags, the review mark, deadline corrections and the fetch button when hosted.
- `worker/`: Cloudflare Worker for the hosted dashboard (`src/index.js` entry point, `src/api.js` logic, `migrations/` D1 schema, `test/`).
- `deploy/`: templates for the private data repo (wrangler config, GitHub workflow, `.gitignore`).
- `tools/leak-check.sh`: checks that nothing private is about to be committed or pushed (see above).
- `docs/TECHNICAL.md`: how everything works, including hosting setup and day-to-day operations.

## Checks before committing

- Leak check: `tools/leak-check.sh` (also before every push).
- Worker: `cd worker && npm test`.
- Python: `.venv/bin/python -m py_compile src/*.py` and `.venv/bin/python -m unittest discover -s tests`.
- Dashboard changes: run `python src/jobs.py serve` and check the page, or build with `python src/jobs.py build-site`.

## Conventions

- No em dashes anywhere (code, comments, docs).
- Do not hard-wrap Markdown; let lines flow.
- Escape every data or user value before inserting it into HTML (`esc()` in `web/app.js`); the page must keep working under the Worker's Content Security Policy (no inline scripts, no third-party resources).
- The Worker must fail closed: without a valid Cloudflare Access token, every request gets 403.
