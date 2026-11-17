// Logic for the hosted dashboard Worker: Access token checks, the notes/tags/review/deadline/fetch API,
// and security headers. The entry point is index.js; see there for configuration.

import { createRemoteJWKSet, jwtVerify } from 'jose';

export const NOTE_MAX = 2000;
export const TAG_MAX = 30;
export const WRITE_CAP = 300;
export const FETCH_COOLDOWN_MS = 3 * 60 * 1000;
const MAX_BODY_BYTES = 8192;

const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ');

// ---------- Authentication ----------

const jwksByIssuer = new Map();

export function teamIssuer(teamDomain) {
  const d = String(teamDomain).trim().replace(/\/+$/, '');
  return d.startsWith('https://') ? d : `https://${d}`;
}

export async function verifyAccessToken(token, { issuer, audience, jwks }) {
  const { payload } = await jwtVerify(token, jwks, { issuer, audience, algorithms: ['RS256'] });
  if (typeof payload.email !== 'string' || !payload.email) return null;
  return payload.email.toLowerCase();
}

export async function authenticate(request, env) {
  // Fail closed: without full configuration nobody gets in.
  if (!env.TEAM_DOMAIN || !env.POLICY_AUD) return null;
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token) return null;
  const issuer = teamIssuer(env.TEAM_DOMAIN);
  let jwks = jwksByIssuer.get(issuer);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
    jwksByIssuer.set(issuer, jwks);
  }
  try {
    return await verifyAccessToken(token, { issuer, audience: env.POLICY_AUD, jwks });
  } catch {
    return null;
  }
}

// ---------- Helpers ----------

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

export function fail(status, message) {
  return json({ error: message }, status);
}

export function secure(response) {
  const res = new Response(response.body, response);
  const h = res.headers;
  h.set('X-Content-Type-Options', 'nosniff');
  h.set('Referrer-Policy', 'no-referrer');
  h.set('X-Frame-Options', 'DENY');
  h.set('Cache-Control', 'private, no-store');
  if ((h.get('Content-Type') || '').includes('text/html')) h.set('Content-Security-Policy', CSP);
  return res;
}

const berlinDateFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit',
});

/** Calendar day in Berlin as YYYY-MM-DD; daily limits reset at Berlin midnight. */
export function berlinDay(date) {
  return berlinDateFormat.format(date);
}

export function cleanNote(value) {
  if (typeof value !== 'string') return null;
  const text = value.replace(/\r\n?/g, '\n').trim();
  if (!text || text.length > NOTE_MAX) return null;
  return text;
}

export function cleanTag(value) {
  if (typeof value !== 'string') return null;
  const name = value.replace(/\s+/g, ' ').trim();
  if (!name || name.length > TAG_MAX || /[\p{Cc}\p{Cf}]/u.test(name)) return null;
  return name;
}

async function readJson(request) {
  if (!(request.headers.get('Content-Type') || '').toLowerCase().startsWith('application/json')) {
    return fail(415, 'Expected a JSON request.');
  }
  const declared = Number(request.headers.get('Content-Length') || 0);
  if (declared > MAX_BODY_BYTES) return fail(413, 'Request too large.');
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) return fail(413, 'Request too large.');
  try {
    const body = JSON.parse(raw);
    if (body && typeof body === 'object' && !Array.isArray(body)) return body;
  } catch {
    // fall through
  }
  return fail(400, 'Invalid JSON body.');
}

/** Counts one change for this user today; false once the daily cap is exceeded. */
async function countWrite({ env, email, now }) {
  const row = await env.DB.prepare(
    `INSERT INTO write_counts (email, day, n) VALUES (?1, ?2, 1)
     ON CONFLICT (email, day) DO UPDATE SET n = n + 1
     RETURNING n`,
  ).bind(email, berlinDay(now)).first();
  return row.n <= WRITE_CAP;
}

const writeLimitReached = () =>
  fail(429, `Daily limit of ${WRITE_CAP} changes per person reached. It resets at midnight (Berlin time).`);

// ---------- Notes and tags ----------

const NOTE_COLUMNS = 'id, job_hash, author, text, created_at, updated_at';

async function getMe({ email }) {
  return json({ email });
}

const REVIEW_COLUMNS = 'job_hash, needs_review, set_by, set_at';
const DEADLINE_COLUMNS = 'job_hash, kind, deadline, set_by, set_at';

async function getAnnotations({ env }) {
  const [notes, tags, jobTags, reviewFlags, deadlines] = await env.DB.batch([
    env.DB.prepare(`SELECT ${NOTE_COLUMNS} FROM notes ORDER BY created_at, id`),
    env.DB.prepare('SELECT id, name FROM tags ORDER BY name_key'),
    env.DB.prepare('SELECT job_hash, tag_id FROM job_tags'),
    env.DB.prepare(`SELECT ${REVIEW_COLUMNS} FROM review_flags`),
    env.DB.prepare(`SELECT ${DEADLINE_COLUMNS} FROM deadline_overrides`),
  ]);
  return json({
    notes: notes.results, tags: tags.results, job_tags: jobTags.results, review_flags: reviewFlags.results,
    deadlines: deadlines.results,
  });
}

async function addNote(ctx) {
  const { env, email, now, params: [hash], body } = ctx;
  const text = cleanNote(body.text);
  if (!text) return fail(400, `A note must be 1 to ${NOTE_MAX} characters.`);
  if (!(await countWrite(ctx))) return writeLimitReached();
  const note = await env.DB.prepare(
    `INSERT INTO notes (job_hash, author, text, created_at) VALUES (?, ?, ?, ?)
     RETURNING ${NOTE_COLUMNS}`,
  ).bind(hash, email, text, now.toISOString()).first();
  return json({ note }, 201);
}

async function ownNote({ env, email, params: [id] }) {
  const note = await env.DB.prepare('SELECT author FROM notes WHERE id = ?').bind(Number(id)).first();
  if (!note) return fail(404, 'This note no longer exists.');
  if (note.author !== email) return fail(403, 'You can only change your own notes.');
  return null;
}

async function editNote(ctx) {
  const { env, email, now, params: [id], body } = ctx;
  const text = cleanNote(body.text);
  if (!text) return fail(400, `A note must be 1 to ${NOTE_MAX} characters.`);
  const denied = await ownNote(ctx);
  if (denied) return denied;
  if (!(await countWrite(ctx))) return writeLimitReached();
  const note = await env.DB.prepare(
    `UPDATE notes SET text = ?, updated_at = ? WHERE id = ? AND author = ?
     RETURNING ${NOTE_COLUMNS}`,
  ).bind(text, now.toISOString(), Number(id), email).first();
  if (!note) return fail(404, 'This note no longer exists.');
  return json({ note });
}

async function deleteNote(ctx) {
  const { env, email, params: [id] } = ctx;
  const denied = await ownNote(ctx);
  if (denied) return denied;
  if (!(await countWrite(ctx))) return writeLimitReached();
  await env.DB.prepare('DELETE FROM notes WHERE id = ? AND author = ?').bind(Number(id), email).run();
  return json({ ok: true });
}

async function addTag(ctx) {
  const { env, email, now, params: [hash], body } = ctx;
  const name = cleanTag(body.name);
  if (!name) return fail(400, `A tag must be 1 to ${TAG_MAX} characters.`);
  if (!(await countWrite(ctx))) return writeLimitReached();
  const key = name.toLowerCase();
  const at = now.toISOString();
  // One transaction: create the tag if it is new (matched case-insensitively), then attach it.
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO tags (name, name_key, created_by, created_at) VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT (name_key) DO NOTHING`,
    ).bind(name, key, email, at),
    env.DB.prepare(
      `INSERT INTO job_tags (job_hash, tag_id, added_by, added_at)
       SELECT ?1, id, ?2, ?3 FROM tags WHERE name_key = ?4
       ON CONFLICT (job_hash, tag_id) DO NOTHING`,
    ).bind(hash, email, at, key),
  ]);
  const tag = await env.DB.prepare('SELECT id, name FROM tags WHERE name_key = ?').bind(key).first();
  return json({ tag }, 201);
}

async function removeTag(ctx) {
  const { env, params: [hash, tagId] } = ctx;
  if (!(await countWrite(ctx))) return writeLimitReached();
  // One transaction: detach, then delete the tag itself once no ad uses it.
  await env.DB.batch([
    env.DB.prepare('DELETE FROM job_tags WHERE job_hash = ? AND tag_id = ?').bind(hash, Number(tagId)),
    env.DB.prepare(
      'DELETE FROM tags WHERE id = ?1 AND NOT EXISTS (SELECT 1 FROM job_tags WHERE tag_id = ?1)',
    ).bind(Number(tagId)),
  ]);
  return json({ ok: true });
}

// ---------- Needs review mark ----------

/** Sets or clears the mark for one ad; anyone on the council may change it. */
async function setReview(ctx) {
  const { env, email, now, params: [hash], body } = ctx;
  if (typeof body.needs_review !== 'boolean') return fail(400, 'needs_review must be true or false.');
  if (!(await countWrite(ctx))) return writeLimitReached();
  const review = await env.DB.prepare(
    `INSERT INTO review_flags (job_hash, needs_review, set_by, set_at) VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT (job_hash) DO UPDATE SET needs_review = ?2, set_by = ?3, set_at = ?4
     RETURNING ${REVIEW_COLUMNS}`,
  ).bind(hash, body.needs_review ? 1 : 0, email, now.toISOString()).first();
  return json({ review });
}

// ---------- Deadline corrections ----------

/** {kind: 'none'} or {kind: 'date', date: 'YYYY-MM-DD'} (a real date, 2000 to 2100); null otherwise. */
export function cleanDeadline(body) {
  if (body.kind === 'none') return { kind: 'none', deadline: null };
  if (body.kind !== 'date' || typeof body.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(body.date)) return null;
  const d = new Date(`${body.date}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== body.date) return null;
  const year = d.getUTCFullYear();
  if (year < 2000 || year > 2100) return null;
  return { kind: 'date', deadline: body.date };
}

/** Replaces the detected deadline of one ad; anyone on the council may change it. */
async function setDeadline(ctx) {
  const { env, email, now, params: [hash], body } = ctx;
  const value = cleanDeadline(body);
  if (!value) return fail(400, 'Choose a valid date (years 2000 to 2100) or "No deadline".');
  if (!(await countWrite(ctx))) return writeLimitReached();
  const deadline = await env.DB.prepare(
    `INSERT INTO deadline_overrides (job_hash, kind, deadline, set_by, set_at) VALUES (?1, ?2, ?3, ?4, ?5)
     ON CONFLICT (job_hash) DO UPDATE SET kind = ?2, deadline = ?3, set_by = ?4, set_at = ?5
     RETURNING ${DEADLINE_COLUMNS}`,
  ).bind(hash, value.kind, value.deadline, email, now.toISOString()).first();
  return json({ deadline });
}

/** Goes back to the deadline detected from the ad. */
async function resetDeadline(ctx) {
  const { env, params: [hash] } = ctx;
  if (!(await countWrite(ctx))) return writeLimitReached();
  await env.DB.prepare('DELETE FROM deadline_overrides WHERE job_hash = ?').bind(hash).run();
  return json({ ok: true });
}

// ---------- Fetch button ----------

function fetchConfig(env) {
  if (!env.GITHUB_TOKEN || !/^[\w.-]+\/[\w.-]+$/.test(env.GITHUB_REPO || '')) return null;
  return {
    repo: env.GITHUB_REPO,
    workflow: env.GITHUB_WORKFLOW || 'update.yml',
    ref: env.GITHUB_REF || 'main',
    limit: Number(env.FETCH_LIMIT) || 3,
    token: env.GITHUB_TOKEN,
  };
}

function github(cfg, path, init = {}) {
  const url = `https://api.github.com/repos/${cfg.repo}/actions/workflows/${encodeURIComponent(cfg.workflow)}${path}`;
  return fetch(url, {
    ...init,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${cfg.token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'uni-job-board',
      ...(init.headers || {}),
    },
  });
}

async function workflowRunning(cfg) {
  const res = await github(cfg, '/runs?per_page=5');
  if (!res.ok) throw new Error(`GitHub API returned ${res.status}`);
  const data = await res.json();
  return (data.workflow_runs || []).some(run => run.status !== 'completed');
}

async function fetchesUsed(env, day) {
  const row = await env.DB.prepare('SELECT COUNT(*) AS n FROM fetch_log WHERE day = ?').bind(day).first();
  return row.n;
}

async function getFetchStatus({ env, now }) {
  const cfg = fetchConfig(env);
  if (!cfg) return json({ enabled: false });
  const used = await fetchesUsed(env, berlinDay(now));
  const cutoff = new Date(now.getTime() - FETCH_COOLDOWN_MS).toISOString();
  // A run takes a moment to show up on GitHub, so a fresh click counts as running.
  const recent = await env.DB.prepare('SELECT 1 AS x FROM fetch_log WHERE requested_at > ? LIMIT 1')
    .bind(cutoff).first();
  let running = Boolean(recent);
  if (!running) {
    try {
      running = await workflowRunning(cfg);
    } catch {
      running = false;
    }
  }
  return json({ enabled: true, used, limit: cfg.limit, running });
}

async function startFetch({ env, email, now }) {
  const cfg = fetchConfig(env);
  if (!cfg) return fail(503, 'Manual fetching is not set up.');
  try {
    if (await workflowRunning(cfg)) return fail(409, 'A fetch is already running.');
  } catch {
    return fail(502, 'Could not reach GitHub. Try again later.');
  }

  const day = berlinDay(now);
  const cutoff = new Date(now.getTime() - FETCH_COOLDOWN_MS).toISOString();
  // Atomic check-and-claim, so simultaneous clicks can never exceed the limit.
  const claim = await env.DB.prepare(
    `INSERT INTO fetch_log (email, day, requested_at)
     SELECT ?1, ?2, ?3
     WHERE (SELECT COUNT(*) FROM fetch_log WHERE day = ?2) < ?4
       AND NOT EXISTS (SELECT 1 FROM fetch_log WHERE requested_at > ?5)
     RETURNING id`,
  ).bind(email, day, now.toISOString(), cfg.limit, cutoff).first();

  if (!claim) {
    if ((await fetchesUsed(env, day)) >= cfg.limit) {
      return fail(429, `All ${cfg.limit} fetches for today are used. They reset at midnight (Berlin time).`);
    }
    return fail(409, 'A fetch was just started. Please wait a few minutes.');
  }

  const res = await github(cfg, '/dispatches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: cfg.ref, inputs: { source: 'dashboard' } }),
  });
  if (!res.ok) {
    // Give the use back if GitHub did not start the run.
    await env.DB.prepare('DELETE FROM fetch_log WHERE id = ?').bind(claim.id).run();
    return fail(502, 'GitHub did not start the fetch. Try again later.');
  }
  return json({ ok: true, used: await fetchesUsed(env, day), limit: cfg.limit }, 202);
}

// ---------- Routing ----------

const ROUTES = [
  ['GET', /^\/api\/me$/, getMe],
  ['GET', /^\/api\/annotations$/, getAnnotations],
  ['POST', /^\/api\/jobs\/([0-9a-f]{16})\/notes$/, addNote],
  ['PATCH', /^\/api\/notes\/([1-9][0-9]{0,14})$/, editNote],
  ['DELETE', /^\/api\/notes\/([1-9][0-9]{0,14})$/, deleteNote],
  ['POST', /^\/api\/jobs\/([0-9a-f]{16})\/tags$/, addTag],
  ['DELETE', /^\/api\/jobs\/([0-9a-f]{16})\/tags\/([1-9][0-9]{0,14})$/, removeTag],
  ['PUT', /^\/api\/jobs\/([0-9a-f]{16})\/review$/, setReview],
  ['PUT', /^\/api\/jobs\/([0-9a-f]{16})\/deadline$/, setDeadline],
  ['DELETE', /^\/api\/jobs\/([0-9a-f]{16})\/deadline$/, resetDeadline],
  ['GET', /^\/api\/fetch-status$/, getFetchStatus],
  ['POST', /^\/api\/fetch$/, startFetch],
];

/** Handles an authenticated /api/ request. `email` is the verified Access identity. */
export async function handleApi(request, env, email, now = new Date()) {
  const url = new URL(request.url);
  let pathMatched = false;
  for (const [method, pattern, handler] of ROUTES) {
    const match = pattern.exec(url.pathname);
    if (!match) continue;
    pathMatched = true;
    if (method !== request.method) continue;

    if (method !== 'GET') {
      // Only the dashboard itself may change data (blocks cross-site requests).
      if (request.headers.get('Origin') !== url.origin) return fail(403, 'Cross-site request rejected.');
    }
    let body = null;
    if (method === 'POST' || method === 'PATCH' || method === 'PUT') {
      body = await readJson(request);
      if (body instanceof Response) return body;
    }
    return handler({ env, email, now, params: match.slice(1), body });
  }
  return pathMatched ? fail(405, 'Method not allowed.') : fail(404, 'Not found.');
}
