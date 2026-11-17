# Agent instructions

Instructions for coding agents working in this repository.

## Every session

1. **At the start**, read [TRACKER.md](TRACKER.md). Check what is in progress and what is next, and move the task you pick up to "In progress" (`[~]`). If the user asks for something that is not listed, add it first.
2. **While working**, commit in small, incremental steps: one logical change per commit (for example a fix, a feature, docs), not one large commit at the end.
3. **At the end**, update [TRACKER.md](TRACKER.md): set task statuses, add new follow-up tasks, and add a dated entry at the top of the session log with what was done, how it was verified, and anything left unverified or unfinished. Commit the tracker update.

## Commits

- For every commit, stage the changes and then call the `commit-message` skill (the `/commit-message` slash command) to write the message. Do not write commit messages by hand.
- Before any git operation, follow the user's own rules. If they require confirmation before committing or pushing, ask first.
- Never commit `data/`, `site/`, `job_ads.xlsx`, secrets, tokens, the hosting domain, Cloudflare Access IDs, or details of the owner's private infrastructure (server names, DNS setup). This also applies to TRACKER.md. This repository is **public**; deployment details live in the private data repo (see `deploy/`).

## Project map

- `src/`: Python CLI (`python src/jobs.py`): scraping, PDF extraction, deadline detection (`deadline.py`), SQLite store, Excel round-trip, local server, `build-site`.
- `tests/`: Python unit tests (standard library `unittest`).
- `web/`: dashboard page (`index.html`, `app.js`, vendored Chart.js). Runs read-only locally and with notes, tags, the review mark, deadline corrections and the fetch button when hosted.
- `worker/`: Cloudflare Worker for the hosted dashboard (`src/index.js` entry point, `src/api.js` logic, `migrations/` D1 schema, `test/`).
- `deploy/`: templates for the private data repo (wrangler config, GitHub workflow, `.gitignore`).
- `docs/TECHNICAL.md`: how everything works, including hosting setup and day-to-day operations.

## Checks before committing

- Worker: `cd worker && npm test`.
- Python: `.venv/bin/python -m py_compile src/*.py` and `.venv/bin/python -m unittest discover -s tests`.
- Dashboard changes: run `python src/jobs.py serve` and check the page, or build with `python src/jobs.py build-site`.

## Conventions

- No em dashes anywhere (code, comments, docs).
- Do not hard-wrap Markdown; let lines flow.
- Escape every data or user value before inserting it into HTML (`esc()` in `web/app.js`); the page must keep working under the Worker's Content Security Policy (no inline scripts, no third-party resources).
- The Worker must fail closed: without a valid Cloudflare Access token, every request gets 403.
