// Tests for the Worker API. Runs the real handlers against an in-memory SQLite
// database that mimics the parts of the D1 API the Worker uses.
// Run with: npm test (from worker/)

import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { SignJWT, generateKeyPair, exportJWK, createLocalJWKSet } from 'jose';
import {
  handleApi, verifyAccessToken, berlinDay, cleanTag, cleanNote, cleanDeadline, secure, isAdmin, WRITE_CAP,
} from '../src/api.js';
import worker from '../src/index.js';

// All migrations in order, as `wrangler d1 migrations apply` runs them.
const MIGRATIONS = new URL('../migrations/', import.meta.url);
const SCHEMA = readdirSync(MIGRATIONS).filter(f => f.endsWith('.sql')).sort()
  .map(f => readFileSync(new URL(f, MIGRATIONS), 'utf8')).join('\n');
const ORIGIN = 'https://board.example.org';
const HASH = '0123456789abcdef';
const HASH2 = 'fedcba9876543210';
const ALICE = 'alice@example.org';
const BOB = 'bob@example.org';
// When Access issued the caller's token (the start of their login session).
const LOGIN = '2026-11-16T09:00:00.000Z';

class FakeStatement {
  constructor(db, sql, params = []) { this.db = db; this.sql = sql; this.params = params; }
  bind(...params) { return new FakeStatement(this.db, this.sql, params); }
  async first() { return this.db.prepare(this.sql).get(...this.params) ?? null; }
  async all() { return { results: this.db.prepare(this.sql).all(...this.params) }; }
  async run() { return { meta: { changes: this.db.prepare(this.sql).run(...this.params).changes } }; }
}

class FakeD1 {
  constructor() {
    this.db = new DatabaseSync(':memory:');
    this.db.exec('PRAGMA foreign_keys = ON');
    this.db.exec(SCHEMA);
  }
  prepare(sql) { return new FakeStatement(this.db, sql); }
  async batch(statements) {
    this.db.exec('BEGIN');
    try {
      const out = statements.map(s => ({ results: this.db.prepare(s.sql).all(...s.params) }));
      this.db.exec('COMMIT');
      return out;
    } catch (err) {
      this.db.exec('ROLLBACK');
      throw err;
    }
  }
}

let env;
let githubCalls;
let githubRunning;
let githubDispatchStatus;
const realFetch = globalThis.fetch;

beforeEach(() => {
  env = { DB: new FakeD1() };
  githubCalls = [];
  githubRunning = false;
  githubDispatchStatus = 204;
  globalThis.fetch = async (url, init = {}) => {
    githubCalls.push({ url: String(url), init });
    if (String(url).includes('/dispatches')) return new Response(null, { status: githubDispatchStatus });
    const runs = githubRunning ? [{ status: 'in_progress' }] : [{ status: 'completed' }];
    return Response.json({ workflow_runs: runs });
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function req(method, path, body, { origin = ORIGIN, contentType = 'application/json' } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  if (body !== undefined) headers['Content-Type'] = contentType;
  return new Request(ORIGIN + path, {
    method,
    headers,
    body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  });
}

async function call(method, path, body, email = ALICE, opts = {}, now = new Date('2026-11-16T10:00:00Z')) {
  const user = { email, loginAt: opts.loginAt === undefined ? LOGIN : opts.loginAt };
  const res = await handleApi(req(method, path, body, opts), env, user, now);
  const data = (res.headers.get('Content-Type') || '').includes('json') ? await res.json() : null;
  return { status: res.status, data };
}

const annotations = async () => (await call('GET', '/api/annotations')).data;
const at = iso => new Date(iso);

// ---------- Identity and request rules ----------

test('me returns the verified email and whether the user is admin', async () => {
  const { status, data } = await call('GET', '/api/me');
  assert.equal(status, 200);
  assert.deepEqual(data, { email: ALICE, admin: false });
  env.ADMIN_EMAILS = ` Bob@Example.org ,${ALICE}`;
  assert.deepEqual((await call('GET', '/api/me')).data, { email: ALICE, admin: true });
  assert.equal((await call('GET', '/api/me', undefined, BOB)).data.admin, true);
});

test('writes need the dashboard origin', async () => {
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'hi' }, ALICE, { origin: null })).status, 403);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'hi' }, ALICE, { origin: 'https://evil.example' })).status, 403);
  assert.equal((await call('DELETE', '/api/notes/1', undefined, ALICE, { origin: 'https://evil.example' })).status, 403);
});

test('writes need a JSON body', async () => {
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, 'text=hi', ALICE, { contentType: 'application/x-www-form-urlencoded' })).status, 415);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, '{not json')).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, '[1,2]')).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'x'.repeat(9000) })).status, 413);
});

test('unknown paths and malformed ids are rejected', async () => {
  assert.equal((await call('GET', '/api/nothing')).status, 404);
  assert.equal((await call('POST', '/api/jobs/NOTAHASH/notes', { text: 'hi' })).status, 404);
  assert.equal((await call('POST', `/api/jobs/${HASH}'--/notes`, { text: 'hi' })).status, 404);
  assert.equal((await call('DELETE', '/api/notes/0')).status, 404);
  assert.equal((await call('GET', `/api/jobs/${HASH}/notes`)).status, 405);
});

// ---------- Logins ----------

const loginRows = () => env.DB.db.prepare('SELECT * FROM logins ORDER BY email, login_at').all()
  .map(r => ({ ...r }));

test('logins: one row per Access session, last seen follows page loads', async () => {
  await call('GET', '/api/me', undefined, ALICE, {}, at('2026-11-16T09:01:00Z'));
  await call('GET', '/api/me', undefined, ALICE, {}, at('2026-11-16T12:30:00Z'));
  // A late, slower request must not move last seen backwards.
  await call('GET', '/api/me', undefined, ALICE, {}, at('2026-11-16T11:00:00Z'));
  assert.deepEqual(loginRows(), [
    { email: ALICE, login_at: LOGIN, last_seen_at: '2026-11-16T12:30:00.000Z' },
  ]);

  const next = '2026-11-17T08:00:00.000Z';
  await call('GET', '/api/me', undefined, ALICE, { loginAt: next }, at('2026-11-17T08:00:05Z'));
  await call('GET', '/api/me', undefined, BOB, {}, at('2026-11-16T09:30:00Z'));
  assert.deepEqual(loginRows(), [
    { email: ALICE, login_at: LOGIN, last_seen_at: '2026-11-16T12:30:00.000Z' },
    { email: ALICE, login_at: next, last_seen_at: '2026-11-17T08:00:05.000Z' },
    { email: BOB, login_at: LOGIN, last_seen_at: '2026-11-16T09:30:00.000Z' },
  ]);
});

test('logins: only page loads (api/me) are recorded, and only with a login time', async () => {
  await call('GET', '/api/annotations');
  await call('POST', `/api/jobs/${HASH}/notes`, { text: 'hi' });
  assert.deepEqual(loginRows(), []);
  const me = await call('GET', '/api/me', undefined, ALICE, { loginAt: null });
  assert.equal(me.status, 200);
  assert.deepEqual(loginRows(), []);
});

test('logins: me still answers if recording fails', async () => {
  env.DB.db.exec('DROP TABLE logins');
  const realError = console.error;
  console.error = () => {};
  try {
    const { status, data } = await call('GET', '/api/me');
    assert.equal(status, 200);
    assert.equal(data.email, ALICE);
  } finally {
    console.error = realError;
  }
});

test('logins: the list is refused unless ADMIN_EMAILS names the caller', async () => {
  assert.equal((await call('GET', '/api/logins')).status, 403);
  env.ADMIN_EMAILS = '';
  assert.equal((await call('GET', '/api/logins')).status, 403);
  env.ADMIN_EMAILS = ',  ,';
  assert.equal((await call('GET', '/api/logins')).status, 403);
  env.ADMIN_EMAILS = BOB;
  assert.equal((await call('GET', '/api/logins')).status, 403);
  // Not just a substring match.
  env.ADMIN_EMAILS = `x${ALICE}`;
  assert.equal((await call('GET', '/api/logins')).status, 403);
  assert.equal((await call('POST', '/api/logins', {})).status, 405);
});

test('logins: admin sees a summary per member and the last 90 days of sessions', async () => {
  env.ADMIN_EMAILS = ALICE;
  const old = '2026-06-01T08:00:00.000Z';
  await call('GET', '/api/me', undefined, BOB, { loginAt: old }, at('2026-06-01T08:10:00Z'));
  await call('GET', '/api/me', undefined, BOB, {}, at('2026-11-16T09:05:00Z'));
  await call('GET', '/api/me', undefined, ALICE, {}, at('2026-11-16T10:00:00Z'));

  const { status, data } = await call('GET', '/api/logins', undefined, ALICE, {}, at('2026-11-16T10:00:00Z'));
  assert.equal(status, 200);
  assert.equal(data.history_days, 90);
  assert.deepEqual(data.members, [
    { email: ALICE, logins: 1, first_login: LOGIN, last_login: LOGIN, last_seen: '2026-11-16T10:00:00.000Z' },
    { email: BOB, logins: 2, first_login: old, last_login: LOGIN, last_seen: '2026-11-16T09:05:00.000Z' },
  ]);
  // The June login is older than 90 days: counted above, but not listed.
  assert.deepEqual(data.recent.map(r => [r.email, r.login_at]), [[ALICE, LOGIN], [BOB, LOGIN]]);
});

test('isAdmin', () => {
  assert.equal(isAdmin({}, ALICE), false);
  assert.equal(isAdmin({ ADMIN_EMAILS: 'ALICE@example.org' }, ALICE), true);
  assert.equal(isAdmin({ ADMIN_EMAILS: 'alice@example.org.evil' }, ALICE), false);
});

// ---------- Notes ----------

test('notes: add, list, and text is stored verbatim for escaping on display', async () => {
  const text = '<script>alert(1)</script>\r\nsecond line';
  const added = await call('POST', `/api/jobs/${HASH}/notes`, { text });
  assert.equal(added.status, 201);
  assert.equal(added.data.note.author, ALICE);
  assert.equal(added.data.note.text, '<script>alert(1)</script>\nsecond line');
  const a = await annotations();
  assert.equal(a.notes.length, 1);
  assert.equal(a.notes[0].job_hash, HASH);
});

test('notes: length limits', async () => {
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: '   ' })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'x'.repeat(2001) })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 42 })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'x'.repeat(2000) })).status, 201);
});

test('notes: only the author can edit or delete', async () => {
  const { data } = await call('POST', `/api/jobs/${HASH}/notes`, { text: 'from alice' });
  const id = data.note.id;

  assert.equal((await call('PATCH', `/api/notes/${id}`, { text: 'hijack' }, BOB)).status, 403);
  assert.equal((await call('DELETE', `/api/notes/${id}`, undefined, BOB)).status, 403);

  const edited = await call('PATCH', `/api/notes/${id}`, { text: 'fixed typo' });
  assert.equal(edited.status, 200);
  assert.equal(edited.data.note.text, 'fixed typo');
  assert.ok(edited.data.note.updated_at);

  assert.equal((await call('DELETE', `/api/notes/${id}`)).status, 200);
  assert.equal((await annotations()).notes.length, 0);
  assert.equal((await call('PATCH', `/api/notes/${id}`, { text: 'gone' })).status, 404);
});

// ---------- Tags ----------

test('tags: created once, matched case-insensitively, attached per ad', async () => {
  const first = await call('POST', `/api/jobs/${HASH}/tags`, { name: '  Good   fit ' });
  assert.equal(first.status, 201);
  assert.equal(first.data.tag.name, 'Good fit');
  const again = await call('POST', `/api/jobs/${HASH2}/tags`, { name: 'GOOD FIT' }, BOB);
  assert.equal(again.data.tag.id, first.data.tag.id);
  const dup = await call('POST', `/api/jobs/${HASH}/tags`, { name: 'good fit' });
  assert.equal(dup.status, 201);

  const a = await annotations();
  assert.equal(a.tags.length, 1);
  assert.equal(a.job_tags.length, 2);
});

test('tags: validation', async () => {
  assert.equal((await call('POST', `/api/jobs/${HASH}/tags`, { name: '' })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/tags`, { name: 'x'.repeat(31) })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/tags`, { name: 'bad​zero-width' })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/tags`, { name: ['array'] })).status, 400);
  assert.equal((await call('POST', `/api/jobs/${HASH}/tags`, { name: 'x'.repeat(30) })).status, 201);
});

test('tags: removing from the last ad deletes the tag', async () => {
  const { data } = await call('POST', `/api/jobs/${HASH}/tags`, { name: 'urgent' });
  await call('POST', `/api/jobs/${HASH2}/tags`, { name: 'urgent' });
  const id = data.tag.id;

  assert.equal((await call('DELETE', `/api/jobs/${HASH}/tags/${id}`)).status, 200);
  let a = await annotations();
  assert.equal(a.tags.length, 1, 'still used by the second ad');

  await call('DELETE', `/api/jobs/${HASH2}/tags/${id}`);
  a = await annotations();
  assert.equal(a.tags.length, 0);
  assert.equal(a.job_tags.length, 0);
});

// ---------- Needs review mark ----------

test('review: set and clear, last change wins and records who made it', async () => {
  assert.deepEqual((await annotations()).review_flags, []);
  const set = await call('PUT', `/api/jobs/${HASH}/review`, { needs_review: true });
  assert.equal(set.status, 200);
  assert.deepEqual(set.data.review, {
    job_hash: HASH, needs_review: 1, set_by: ALICE, set_at: '2026-11-16T10:00:00.000Z',
  });
  const later = new Date('2026-11-16T11:00:00Z');
  const cleared = await call('PUT', `/api/jobs/${HASH}/review`, { needs_review: false }, BOB, {}, later);
  assert.equal(cleared.status, 200);
  await call('PUT', `/api/jobs/${HASH2}/review`, { needs_review: false });
  const flags = (await annotations()).review_flags.sort((a, b) => a.job_hash.localeCompare(b.job_hash));
  assert.deepEqual(flags, [
    { job_hash: HASH, needs_review: 0, set_by: BOB, set_at: '2026-11-16T11:00:00.000Z' },
    { job_hash: HASH2, needs_review: 0, set_by: ALICE, set_at: '2026-11-16T10:00:00.000Z' },
  ]);
});

test('review: validation, origin check and allowed methods', async () => {
  for (const value of [undefined, 1, 'true', null]) {
    assert.equal((await call('PUT', `/api/jobs/${HASH}/review`, { needs_review: value })).status, 400);
  }
  assert.equal((await call('PUT', `/api/jobs/${HASH}/review`, { needs_review: true }, ALICE, { origin: 'https://evil.example' })).status, 403);
  assert.equal((await call('PUT', `/api/jobs/${HASH}/review`, 'needs_review=1', ALICE, { contentType: 'text/plain' })).status, 415);
  assert.equal((await call('POST', `/api/jobs/${HASH}/review`, { needs_review: true })).status, 405);
  assert.equal((await call('PUT', '/api/jobs/NOTAHASH/review', { needs_review: true })).status, 404);
  assert.deepEqual((await annotations()).review_flags, []);
});

test('review: counts towards the daily write cap', async () => {
  const now = new Date('2026-11-16T10:00:00Z');
  env.DB.db.prepare('INSERT INTO write_counts (email, day, n) VALUES (?, ?, ?)').run(ALICE, berlinDay(now), WRITE_CAP);
  assert.equal((await call('PUT', `/api/jobs/${HASH}/review`, { needs_review: true })).status, 429);
});

// ---------- Deadline corrections ----------

test('deadline: set a date, change it to none, reset to detected', async () => {
  assert.deepEqual((await annotations()).deadlines, []);
  const set = await call('PUT', `/api/jobs/${HASH}/deadline`, { kind: 'date', date: '2026-12-01' });
  assert.equal(set.status, 200);
  assert.deepEqual(set.data.deadline, {
    job_hash: HASH, kind: 'date', deadline: '2026-12-01', set_by: ALICE, set_at: '2026-11-16T10:00:00.000Z',
  });
  const later = new Date('2026-11-16T11:00:00Z');
  const none = await call('PUT', `/api/jobs/${HASH}/deadline`, { kind: 'none', date: '2026-12-01' }, BOB, {}, later);
  assert.deepEqual(none.data.deadline, {
    job_hash: HASH, kind: 'none', deadline: null, set_by: BOB, set_at: '2026-11-16T11:00:00.000Z',
  });
  await call('PUT', `/api/jobs/${HASH2}/deadline`, { kind: 'date', date: '2027-01-15' });
  assert.equal((await annotations()).deadlines.length, 2);
  assert.equal((await call('DELETE', `/api/jobs/${HASH}/deadline`)).status, 200);
  assert.deepEqual((await annotations()).deadlines.map(d => d.job_hash), [HASH2]);
  // Resetting an ad without a correction is fine too.
  assert.equal((await call('DELETE', `/api/jobs/${HASH}/deadline`)).status, 200);
});

test('deadline: validation, origin check and write cap', async () => {
  const bad = [
    {}, { kind: 'date' }, { kind: 'date', date: '2026-02-30' }, { kind: 'date', date: '2026-2-3' },
    { kind: 'date', date: '1999-12-31' }, { kind: 'date', date: '2101-01-01' }, { kind: 'date', date: 20261201 },
    { kind: 'date', date: '2026-12-01T00:00' }, { kind: 'rolling' }, { kind: 'none ' },
  ];
  for (const body of bad) {
    assert.equal((await call('PUT', `/api/jobs/${HASH}/deadline`, body)).status, 400, JSON.stringify(body));
  }
  assert.equal((await call('PUT', `/api/jobs/${HASH}/deadline`, { kind: 'none' }, ALICE, { origin: 'https://evil.example' })).status, 403);
  assert.equal((await call('DELETE', `/api/jobs/${HASH}/deadline`, undefined, ALICE, { origin: null })).status, 403);
  assert.equal((await call('POST', `/api/jobs/${HASH}/deadline`, { kind: 'none' })).status, 405);
  assert.deepEqual((await annotations()).deadlines, []);
  const now = new Date('2026-11-16T10:00:00Z');
  env.DB.db.prepare('INSERT INTO write_counts (email, day, n) VALUES (?, ?, ?)').run(ALICE, berlinDay(now), WRITE_CAP);
  assert.equal((await call('PUT', `/api/jobs/${HASH}/deadline`, { kind: 'none' })).status, 429);
  assert.equal((await call('DELETE', `/api/jobs/${HASH}/deadline`)).status, 429);
});

test('cleanDeadline', () => {
  assert.deepEqual(cleanDeadline({ kind: 'none' }), { kind: 'none', deadline: null });
  assert.deepEqual(cleanDeadline({ kind: 'date', date: '2028-02-29' }), { kind: 'date', deadline: '2028-02-29' });
  assert.equal(cleanDeadline({ kind: 'date', date: '2027-02-29' }), null);
});

// ---------- Write cap ----------

test('per-user daily write cap', async () => {
  const now = new Date('2026-11-16T10:00:00Z');
  env.DB.db.prepare('INSERT INTO write_counts (email, day, n) VALUES (?, ?, ?)').run(ALICE, berlinDay(now), WRITE_CAP - 1);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'last one' })).status, 201);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'one too many' })).status, 429);
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'bob is fine' }, BOB)).status, 201);
  const tomorrow = new Date('2026-11-17T10:00:00Z');
  assert.equal((await call('POST', `/api/jobs/${HASH}/notes`, { text: 'new day' }, ALICE, {}, tomorrow)).status, 201);
});

// ---------- Fetch button ----------

test('fetch: disabled without GitHub config', async () => {
  assert.deepEqual((await call('GET', '/api/fetch-status')).data, { enabled: false });
  assert.equal((await call('POST', '/api/fetch', {})).status, 503);
});

test('fetch: limit of 3 per Berlin day, cooldown, and dispatch payload', async () => {
  Object.assign(env, { GITHUB_TOKEN: 't', GITHUB_REPO: 'owner/data', FETCH_LIMIT: '3' });

  let st = await call('GET', '/api/fetch-status', undefined, ALICE, {}, at('2026-11-16T08:00:00Z'));
  assert.deepEqual(st.data, { enabled: true, used: 0, limit: 3, running: false });

  const first = await call('POST', '/api/fetch', {}, ALICE, {}, at('2026-11-16T08:00:00Z'));
  assert.equal(first.status, 202);
  const dispatch = githubCalls.find(c => c.url.endsWith('/actions/workflows/update.yml/dispatches'));
  assert.ok(dispatch, 'dispatch endpoint called');
  assert.deepEqual(JSON.parse(dispatch.init.body), { ref: 'main', inputs: { source: 'dashboard' } });
  assert.equal(dispatch.init.headers.Authorization, 'Bearer t');

  // Right after a click the button shows "running", and a second click is refused.
  st = await call('GET', '/api/fetch-status', undefined, ALICE, {}, at('2026-11-16T08:01:00Z'));
  assert.equal(st.data.running, true);
  assert.equal((await call('POST', '/api/fetch', {}, BOB, {}, at('2026-11-16T08:01:00Z'))).status, 409);

  assert.equal((await call('POST', '/api/fetch', {}, BOB, {}, at('2026-11-16T09:00:00Z'))).status, 202);
  assert.equal((await call('POST', '/api/fetch', {}, ALICE, {}, at('2026-11-16T10:00:00Z'))).status, 202);
  assert.equal((await call('POST', '/api/fetch', {}, ALICE, {}, at('2026-11-16T11:00:00Z'))).status, 429);

  st = await call('GET', '/api/fetch-status', undefined, ALICE, {}, at('2026-11-16T11:00:00Z'));
  assert.equal(st.data.used, 3);

  // 23:30 UTC on Nov 16 is already Nov 17 in Berlin: the limit has reset.
  assert.equal((await call('POST', '/api/fetch', {}, ALICE, {}, at('2026-11-16T23:30:00Z'))).status, 202);
});

test('fetch: refused while a run is in progress', async () => {
  Object.assign(env, { GITHUB_TOKEN: 't', GITHUB_REPO: 'owner/data' });
  githubRunning = true;
  assert.equal((await call('POST', '/api/fetch', {})).status, 409);
  assert.equal((await call('GET', '/api/fetch-status')).data.running, true);
});

test('fetch: a failed dispatch does not use up a fetch', async () => {
  Object.assign(env, { GITHUB_TOKEN: 't', GITHUB_REPO: 'owner/data' });
  githubDispatchStatus = 500;
  assert.equal((await call('POST', '/api/fetch', {})).status, 502);
  assert.equal((await call('GET', '/api/fetch-status')).data.used, 0);
});

test('fetch: invalid repo setting disables the button', async () => {
  Object.assign(env, { GITHUB_TOKEN: 't', GITHUB_REPO: 'owner/data/../../evil' });
  assert.deepEqual((await call('GET', '/api/fetch-status')).data, { enabled: false });
});

// ---------- Helpers ----------

test('berlinDay follows Berlin midnight, including daylight saving', () => {
  assert.equal(berlinDay(new Date('2026-11-16T22:59:00Z')), '2026-11-16');
  assert.equal(berlinDay(new Date('2026-11-16T23:00:00Z')), '2026-11-17');
  assert.equal(berlinDay(new Date('2026-07-01T21:59:00Z')), '2026-07-01');
  assert.equal(berlinDay(new Date('2026-07-01T22:00:00Z')), '2026-07-02');
});

test('cleanTag and cleanNote', () => {
  assert.equal(cleanTag('  a \n b  '), 'a b');
  assert.equal(cleanTag('\u0000'), null);
  assert.equal(cleanNote(' a\r\nb '), 'a\nb');
});

// ---------- Access token verification ----------

async function makeKeys() {
  const { publicKey, privateKey } = await generateKeyPair('RS256');
  const jwk = { ...(await exportJWK(publicKey)), kid: 'k1', alg: 'RS256' };
  return { privateKey, jwks: createLocalJWKSet({ keys: [jwk] }) };
}

async function sign(privateKey, claims, { alg = 'RS256', expires = '1h' } = {}) {
  return new SignJWT(claims).setProtectedHeader({ alg, kid: 'k1' }).setIssuedAt().setExpirationTime(expires).sign(privateKey);
}

test('Access token: valid token yields lowercased email and the login time', async () => {
  const { privateKey, jwks } = await makeKeys();
  const token = await new SignJWT({ iss: 'https://team.cloudflareaccess.com', aud: ['aud123'], email: 'Alice@Example.org' })
    .setProtectedHeader({ alg: 'RS256', kid: 'k1' }).setIssuedAt(Math.floor(Date.now() / 1000) - 3600).setExpirationTime('1h')
    .sign(privateKey);
  const user = await verifyAccessToken(token, { issuer: 'https://team.cloudflareaccess.com', audience: 'aud123', jwks });
  assert.equal(user.email, 'alice@example.org');
  assert.ok(Math.abs(Date.parse(user.loginAt) - (Date.now() - 3600 * 1000)) < 5000, user.loginAt);
  assert.match(user.loginAt, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z$/);

  const noIat = await new SignJWT({ iss: 'https://team.cloudflareaccess.com', aud: ['aud123'], email: 'a@b.c' })
    .setProtectedHeader({ alg: 'RS256', kid: 'k1' }).setExpirationTime('1h').sign(privateKey);
  const user2 = await verifyAccessToken(noIat, { issuer: 'https://team.cloudflareaccess.com', audience: 'aud123', jwks });
  assert.deepEqual(user2, { email: 'a@b.c', loginAt: null });
});

test('Access token: wrong audience, issuer, signer, or expired token is rejected', async () => {
  const { privateKey, jwks } = await makeKeys();
  const other = await makeKeys();
  const opts = { issuer: 'https://team.cloudflareaccess.com', audience: 'aud123', jwks };
  const good = { iss: 'https://team.cloudflareaccess.com', aud: ['aud123'], email: 'a@b.c' };

  await assert.rejects(verifyAccessToken(await sign(privateKey, { ...good, aud: ['other'] }), opts));
  await assert.rejects(verifyAccessToken(await sign(privateKey, { ...good, iss: 'https://evil.cloudflareaccess.com' }), opts));
  await assert.rejects(verifyAccessToken(await sign(other.privateKey, good), opts));
  await assert.rejects(verifyAccessToken(await sign(privateKey, good, { expires: '-1m' }), opts));
});

// ---------- Front door ----------

test('requests are refused when Access is not configured or no token is sent', async () => {
  const assets = { fetch: async () => new Response('<html>', { headers: { 'Content-Type': 'text/html' } }) };
  let res = await worker.fetch(new Request(ORIGIN + '/'), { ASSETS: assets });
  assert.equal(res.status, 403);
  res = await worker.fetch(new Request(ORIGIN + '/pdfs/x.pdf'), { ASSETS: assets, TEAM_DOMAIN: 'team.cloudflareaccess.com', POLICY_AUD: 'aud' });
  assert.equal(res.status, 403);
  res = await worker.fetch(
    new Request(ORIGIN + '/api/jobs.json', { headers: { 'Cf-Access-Jwt-Assertion': 'garbage' } }),
    { ASSETS: assets, TEAM_DOMAIN: 'team.cloudflareaccess.com', POLICY_AUD: 'aud' },
  );
  assert.equal(res.status, 403);
});

test('a valid Access token reaches the API and the page, and records the login', async () => {
  const { publicKey, privateKey } = await generateKeyPair('RS256');
  const jwk = { ...(await exportJWK(publicKey)), kid: 'k1', alg: 'RS256' };
  globalThis.fetch = async url => {
    assert.equal(String(url), 'https://frontdoor.cloudflareaccess.com/cdn-cgi/access/certs');
    return Response.json({ keys: [jwk] });
  };
  const iat = Math.floor(Date.now() / 1000) - 60;
  const token = await new SignJWT({ iss: 'https://frontdoor.cloudflareaccess.com', aud: ['aud'], email: 'Alice@example.org' })
    .setProtectedHeader({ alg: 'RS256', kid: 'k1' }).setIssuedAt(iat).setExpirationTime('1h').sign(privateKey);
  const assets = { fetch: async () => new Response('<html>', { headers: { 'Content-Type': 'text/html' } }) };
  Object.assign(env, { ASSETS: assets, TEAM_DOMAIN: 'frontdoor.cloudflareaccess.com', POLICY_AUD: 'aud', ADMIN_EMAILS: ALICE });
  const withToken = path => new Request(ORIGIN + path, { headers: { 'Cf-Access-Jwt-Assertion': token } });

  let res = await worker.fetch(withToken('/api/me'), env);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { email: ALICE, admin: true });
  const rows = env.DB.db.prepare('SELECT email, login_at FROM logins').all().map(r => ({ ...r }));
  assert.deepEqual(rows, [{ email: ALICE, login_at: new Date(iat * 1000).toISOString() }]);

  res = await worker.fetch(withToken('/api/logins'), env);
  assert.equal(res.status, 200);
  assert.equal((await res.json()).members[0].email, ALICE);

  res = await worker.fetch(withToken('/'), env);
  assert.equal(res.status, 200);
  assert.match(res.headers.get('Content-Security-Policy'), /script-src 'self'/);
});

test('security headers: CSP on HTML only, no-store everywhere', async () => {
  const html = secure(new Response('<html>', { headers: { 'Content-Type': 'text/html; charset=utf-8' } }));
  assert.match(html.headers.get('Content-Security-Policy'), /script-src 'self'/);
  assert.equal(html.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.equal(html.headers.get('Cache-Control'), 'private, no-store');
  const pdf = secure(new Response('%PDF', { headers: { 'Content-Type': 'application/pdf' } }));
  assert.equal(pdf.headers.get('Content-Security-Policy'), null);
  assert.equal(pdf.headers.get('X-Frame-Options'), 'DENY');
});
