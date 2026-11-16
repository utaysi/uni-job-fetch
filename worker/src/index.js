// Cloudflare Worker for the hosted job dashboard.
//
// Every request passes through here first (run_worker_first). The Worker:
// 1. Verifies the Cloudflare Access login token. No valid token, no access:
//    this holds even if Access were ever misconfigured or turned off.
// 2. Answers the small JSON API for council notes, tags and the "Fetch now" button.
// 3. Serves the static dashboard, job data and PDFs with strict security headers.
//
// Configuration (wrangler.toml vars, plus one secret):
//   TEAM_DOMAIN      Access team domain, e.g. "myteam.cloudflareaccess.com"
//   POLICY_AUD       Access application audience (AUD) tag
//   GITHUB_REPO      "owner/repo" of the private data repo (enables the fetch button)
//   GITHUB_WORKFLOW  workflow file name (default "update.yml")
//   GITHUB_REF       branch to run the workflow on (default "main")
//   FETCH_LIMIT      manual fetches per day for everyone together (default 3)
//   GITHUB_TOKEN     secret: fine-grained token, data repo only, "Actions: read and write"

import { authenticate, fail, handleApi, secure } from './api.js';

export default {
  async fetch(request, env) {
    const email = await authenticate(request, env);
    if (!email) {
      return secure(new Response('Forbidden', {
        status: 403,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      }));
    }

    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/') && url.pathname !== '/api/jobs.json') {
      try {
        return secure(await handleApi(request, env, email));
      } catch (err) {
        console.error('API error', err && err.message);
        return secure(fail(500, 'Something went wrong. Try again.'));
      }
    }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return secure(fail(405, 'Method not allowed.'));
    }
    return secure(await env.ASSETS.fetch(request));
  },
};
