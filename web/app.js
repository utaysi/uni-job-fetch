'use strict';

// Dashboard logic. Works in two modes:
// - local (`jobs.py serve`): read-only list, charts and filters.
// - hosted (Cloudflare Worker): adds notes, tags and the "Fetch now" button.
// The page detects hosted mode by asking for api/me, which only the Worker answers.

const COLORS = [
  '#6c5ce7','#00cec9','#fd79a8','#f39c12','#00b894',
  '#e74c3c','#0984e3','#a29bfe','#55efc4','#fab1a0',
  '#81ecec','#ffeaa7','#dfe6e9','#74b9ff','#ff7675',
  '#636e72','#b2bec3','#fdcb6e','#e17055','#00b894',
  '#e84393','#2d3436','#6c5ce7','#00cec9','#fd79a8',
  '#f39c12','#00b894','#e74c3c','#0984e3'
];
const FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const STATUS_FILTERS = ['Online', 'Offline', 'Needs Review'];
const SORT_OPTIONS = [
  ['newest', 'Newest first'],
  ['oldest', 'Oldest first'],
  ['deadline', 'Deadline soonest'],
  ['title', 'Title A-Z'],
  ['department', 'Department A-Z'],
];
const FETCH_POLL_MS = 20000;

let allJobs = [];
let jobsByHash = new Map();
let activeSources = new Set();
let knownSources = new Set();
let activeStatuses = new Set();
let activeTags = new Set();
let filterUntagged = false;
let sortBy = 'newest';
let serverOrder = new Map();
let sourceCounts = {};
let sourceChart = null;
let timelineChart = null;

// Hosted-only state. `me` stays null on the local read-only server.
let me = null;
let notesByJob = new Map();
let tagsById = new Map();
let tagIdsByJob = new Map();
const expanded = new Set();
const editingNotes = new Set();

const $ = id => document.getElementById(id);

// Every value from the data or from users goes through esc() before it is
// placed into HTML, so ad text or notes can never inject markup or scripts.
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// ---------- Formatting ----------

// Deadlines arrive as dd.mm.yyyy, yyyy-mm-dd, or free text. Return a Date or null.
function parseDate(str) {
  if (!str) return null;
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  m = /(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})/.exec(str);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
  return null;
}

function jobTitle(j) {
  return j.position_title || j.job_id || j.original_pdf_name || 'Untitled';
}

function formatDate(str) {
  const d = parseDate(str);
  if (!d) return str || '';
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

const pad = n => String(n).padStart(2, '0');

// Fetch timestamps are naive Berlin times ("2026-11-16T06:03:12"); show them as written.
function formatBerlinStamp(str) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(str || '');
  if (!m) return '-';
  return `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[1]}, ${m[4]}:${m[5]}`;
}

// Note timestamps are UTC ISO strings; show them in the viewer's local time.
function formatInstant(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function displayName(email) {
  return String(email || '').split('@')[0] || email;
}

// ---------- Deadlines ----------

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfToday() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

// The deadline as a Date, or null. The server reads it (src/deadline.py) and
// sends deadline_iso; data from before that only has the text.
function deadlineDate(j) {
  return parseDate(j.deadline_kind ? j.deadline_iso : j.application_deadline);
}

// Whole days until the deadline. The deadline day itself is 0 and still open.
function daysLeft(d) {
  return Math.round((d - startOfToday()) / DAY_MS);
}

function deadlineStatus(d) {
  const days = daysLeft(d);
  if (days < 0) return { text: 'Expired', cls: 'deadline-past' };
  if (days === 0) return { text: 'Today', cls: 'deadline-soon' };
  return { text: `${days}d left`, cls: days <= 7 ? 'deadline-soon' : 'deadline-future' };
}

// What the Deadline line shows: a date or a word, a countdown, and a tooltip
// with what the ad actually says.
function deadlineView(j) {
  const raw = j.application_deadline || '';
  const d = deadlineDate(j);
  const kind = j.deadline_kind || (d ? 'date' : raw ? 'text' : 'none');
  if ((kind === 'date' || kind === 'relative') && d) {
    const relative = kind === 'relative';
    return {
      text: (relative ? '~' : '') + formatDate(j.deadline_iso || raw),
      status: deadlineStatus(d),
      title: relative
        ? `The ad gives no date, only "${raw}" after it was posted. Estimated as ${j.deadline_days} days after the day it was first seen.`
        : `The ad says: ${raw}`,
    };
  }
  if (kind === 'rolling') {
    return { text: 'No deadline', open: true, title: `Applications are accepted at any time. The ad says: ${raw}` };
  }
  if (kind === 'unknown') {
    return { text: 'Unknown', open: true,
      title: 'This PDF is a scanned image without text, so the deadline could not be read. Open the PDF to check.' };
  }
  if (raw) return { text: raw, title: raw };
  return { text: 'No deadline', open: true, title: 'The ad does not give an application deadline.' };
}

function sourceColor(source) {
  const idx = Object.keys(sourceCounts).indexOf(source);
  return COLORS[(idx < 0 ? 0 : idx) % COLORS.length];
}

let toastTimer = null;
function toast(message, isError = false) {
  const el = $('toast');
  el.textContent = message;
  el.classList.toggle('error', isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 7000 : 4000);
}

// ---------- Filters ----------

function buildSourceList() {
  sourceCounts = {};
  allJobs.forEach(j => {
    const s = j.department || 'Unknown';
    sourceCounts[s] = (sourceCounts[s] || 0) + 1;
  });

  const sorted = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]);
  const container = $('sourceList');
  container.innerHTML = '';

  sorted.forEach(([source, count]) => {
    // Keep the user's selection on reload; departments seen for the first time start selected.
    if (!knownSources.has(source)) {
      knownSources.add(source);
      activeSources.add(source);
    }
    const chip = document.createElement('div');
    chip.className = 'source-chip';
    chip.dataset.source = source;
    chip.innerHTML = `
      <span class="source-dot" style="background:${sourceColor(source)}"></span>
      <span class="source-name">${esc(source)}</span>
      <span class="source-count">${count}</span>
    `;
    chip.addEventListener('click', () => {
      if (activeSources.size === sorted.length && activeSources.has(source)) {
        activeSources.clear();
      } else if (!activeSources.has(source)) {
        activeSources.add(source);
      } else {
        activeSources.delete(source);
      }
      updateSourceChips();
      render();
    });
    container.appendChild(chip);
  });

  updateSourceChips();
  $('sourcesCount').textContent = sorted.length;
}

function updateSourceChips() {
  document.querySelectorAll('.source-chip').forEach(chip => {
    chip.classList.toggle('active', activeSources.has(chip.dataset.source));
  });
}

function buildFetchChips() {
  const container = $('fetchChips');
  container.innerHTML = '';
  // Default to showing only Online ads; Offline and Needs Review are opt-in.
  STATUS_FILTERS.forEach(s => {
    const chip = document.createElement('button');
    const on = s === 'Online';
    chip.className = on ? 'fetch-chip active' : 'fetch-chip';
    chip.textContent = s;
    chip.dataset.status = s;
    chip.addEventListener('click', () => {
      if (activeStatuses.has(s)) {
        if (activeStatuses.size > 1) activeStatuses.delete(s);
      } else {
        activeStatuses.add(s);
      }
      updateFetchChips();
      render();
    });
    container.appendChild(chip);
    if (on) activeStatuses.add(s);
  });
}

function updateFetchChips() {
  document.querySelectorAll('#fetchChips .fetch-chip').forEach(chip => {
    chip.classList.toggle('active', activeStatuses.has(chip.dataset.status));
  });
}

function buildTagPanel() {
  const container = $('tagChips');
  // Drop filters for tags that no longer exist.
  for (const id of activeTags) if (!tagsById.has(id)) activeTags.delete(id);

  const counts = new Map();
  for (const ids of tagIdsByJob.values()) ids.forEach(id => counts.set(id, (counts.get(id) || 0) + 1));
  const tags = [...tagsById.values()].sort((a, b) => a.name.localeCompare(b.name));

  if (!tags.length) {
    // Without any tags every ad is untagged, so the "No tags" filter would do nothing.
    filterUntagged = false;
    container.innerHTML = '<span class="muted">No tags yet. Open an ad to add one.</span>';
    return;
  }
  const untagged = allJobs.filter(j => !(tagIdsByJob.get(j.hash) || []).length).length;
  container.innerHTML = `
    <button type="button" class="fetch-chip untagged${filterUntagged ? ' active' : ''}" data-untagged="1">
      No tags (${untagged})
    </button>` + tags.map(t => `
    <button type="button" class="fetch-chip${activeTags.has(t.id) ? ' active' : ''}" data-tag-id="${esc(t.id)}">
      ${esc(t.name)} (${counts.get(t.id) || 0})
    </button>`).join('');
}

function buildSortChips() {
  const container = $('sortChips');
  container.innerHTML = SORT_OPTIONS.map(([id, label]) => `
    <button type="button" class="fetch-chip${sortBy === id ? ' active' : ''}" data-sort="${esc(id)}" aria-pressed="${sortBy === id}">
      ${esc(label)}
    </button>`).join('');
}

// ---------- Sorting ----------

// The server sends ads newest first (first seen, then the order they were found
// within that fetch), so the original position breaks ties between ads that
// were first seen in the same fetch.
function byFirstSeen(a, b) {
  return (b.first_seen || '').localeCompare(a.first_seen || '')
    || serverOrder.get(a.hash) - serverOrder.get(b.hash);
}

// Upcoming deadlines first (soonest first, estimates included), then expired
// ones (most recent first), then ads without a deadline, then unreadable ones.
// Uses the same cut-off as the "Expired" label so the order matches the cards.
function deadlineKey(j) {
  const d = deadlineDate(j);
  if (d) return daysLeft(d) < 0 ? [1, -d.getTime()] : [0, d.getTime()];
  return [j.deadline_kind === 'unknown' ? 3 : 2, 0];
}

function sortJobs(jobs) {
  const text = (a, b) => a.localeCompare(b, 'de', { sensitivity: 'base' });
  const compare = {
    newest: byFirstSeen,
    oldest: (a, b) => byFirstSeen(b, a),
    deadline: (a, b) => {
      const ka = deadlineKey(a), kb = deadlineKey(b);
      return ka[0] - kb[0] || ka[1] - kb[1] || byFirstSeen(a, b);
    },
    title: (a, b) => text(jobTitle(a), jobTitle(b)) || byFirstSeen(a, b),
    department: (a, b) => text(a.department || 'Unknown', b.department || 'Unknown') || byFirstSeen(a, b),
  }[sortBy] || byFirstSeen;
  return jobs.slice().sort(compare);
}

function updateTagSuggestions() {
  const list = $('tagSuggestions');
  list.innerHTML = '';
  [...tagsById.values()].sort((a, b) => a.name.localeCompare(b.name)).forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.name;
    list.appendChild(opt);
  });
}

function jobMatchesStatus(j) {
  if (activeStatuses.has('Needs Review') && j.needs_review) return true;
  if (activeStatuses.has('Online') && j.status === 'Online') return true;
  if (activeStatuses.has('Offline') && j.status === 'Offline') return true;
  return false;
}

function getFilteredJobs() {
  const search = $('searchInput').value.toLowerCase().trim();
  const dateFrom = $('dateFrom').value;
  const dateTo = $('dateTo').value;

  return allJobs.filter(j => {
    if (!activeSources.has(j.department || 'Unknown')) return false;
    if (!jobMatchesStatus(j)) return false;

    // Tag chips and "No tags" combine with OR: an ad shows if it matches any of them.
    if (activeTags.size || filterUntagged) {
      const ids = tagIdsByJob.get(j.hash) || [];
      const match = (filterUntagged && !ids.length) || ids.some(id => activeTags.has(id));
      if (!match) return false;
    }

    if (search) {
      const tagNames = (tagIdsByJob.get(j.hash) || []).map(id => tagsById.get(id)?.name || '');
      const hay = [jobTitle(j), j.department, j.job_id, j.working_group,
                   j.contact_name, ...tagNames].join(' ').toLowerCase();
      if (!hay.includes(search)) return false;
    }

    if (dateFrom) {
      const d = deadlineDate(j);
      if (!d || d < parseDate(dateFrom)) return false;
    }
    if (dateTo) {
      const d = deadlineDate(j);
      if (!d || d > parseDate(dateTo)) return false;
    }

    return true;
  });
}

// ---------- Job cards ----------

function tagChip(id, removable) {
  const tag = tagsById.get(id);
  if (!tag) return '';
  const remove = removable
    ? `<button type="button" class="tag-remove" data-action="remove-tag" data-tag-id="${esc(id)}" aria-label="Remove tag ${esc(tag.name)}">&times;</button>`
    : '';
  return `<span class="tag-chip">${esc(tag.name)}${remove}</span>`;
}

function noteHtml(n) {
  if (editingNotes.has(n.id)) {
    return `
      <li class="note" data-note-id="${esc(n.id)}">
        <form class="note-form" data-action="save-note">
          <textarea name="text" maxlength="2000" rows="3" required>${esc(n.text)}</textarea>
          <div class="note-buttons">
            <button class="action-btn small" type="submit">Save</button>
            <button class="link-btn" type="button" data-action="cancel-edit">Cancel</button>
          </div>
        </form>
      </li>`;
  }
  const mine = n.author === me;
  const when = formatInstant(n.created_at) + (n.updated_at ? ' (edited)' : '');
  return `
    <li class="note" data-note-id="${esc(n.id)}">
      <div class="note-head">
        <span class="note-author" title="${esc(n.author)}">${esc(displayName(n.author))}</span>
        <span class="note-time">${esc(when)}</span>
        ${mine ? `<button class="link-btn" type="button" data-action="edit-note">Edit</button>
                  <button class="link-btn danger" type="button" data-action="delete-note">Delete</button>` : ''}
      </div>
      <div class="note-text">${esc(n.text)}</div>
    </li>`;
}

function detailsHtml(j) {
  const notes = notesByJob.get(j.hash) || [];
  const tagIds = tagIdsByJob.get(j.hash) || [];
  return `
    <div class="job-details">
      <section class="details-block">
        <h4>Tags</h4>
        <div class="job-tags">${tagIds.map(id => tagChip(id, true)).join('') || '<span class="muted">No tags yet</span>'}</div>
        <form class="inline-form" data-action="add-tag">
          <input name="tag" list="tagSuggestions" maxlength="30" placeholder="New or existing tag" autocomplete="off" required>
          <button class="action-btn small" type="submit">Add</button>
        </form>
      </section>
      <section class="details-block">
        <h4>Notes</h4>
        ${notes.length ? `<ul class="notes">${notes.map(noteHtml).join('')}</ul>` : '<p class="muted">No notes yet</p>'}
        <form class="note-form" data-action="add-note">
          <textarea name="text" maxlength="2000" rows="2" placeholder="Add a note for the council" required></textarea>
          <button class="action-btn small" type="submit">Add note</button>
        </form>
      </section>
    </div>`;
}

const NOTE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

function cardHtml(j, i, animate) {
  const dl = deadlineView(j);
  const isOpen = me && expanded.has(j.hash);
  const tagIds = tagIdsByJob.get(j.hash) || [];
  const noteCount = (notesByJob.get(j.hash) || []).length;
  const notesWord = `${noteCount} note${noteCount === 1 ? '' : 's'}`;
  const notesBadge = me && noteCount
    ? `<span class="note-badge" title="${notesWord}" aria-label="${notesWord}">${NOTE_ICON}${noteCount}</span>`
    : '';
  const review = j.needs_review ? '<span style="color:var(--orange)">&#9888; review</span>' : '';
  const offline = j.status === 'Offline' ? '<span style="color:var(--text-muted)">offline</span>' : '';
  const pdf = j.pdf ? encodeURI(j.pdf) : '';
  const seen = j.first_seen ? formatDate(j.first_seen) : '-';
  const classes = ['job-card', isOpen ? 'expanded' : '', animate ? '' : 'no-anim'].filter(Boolean).join(' ');
  return `
    <div class="${classes}" data-hash="${esc(j.hash)}" style="animation-delay:${Math.min(i * 0.03, 0.5)}s">
      <div class="job-source-badge" style="background:${sourceColor(j.department || 'Unknown')}"></div>
      <div class="job-info">
        <div class="job-title-row">
          <div class="job-title">${esc(jobTitle(j))}</div>
          ${notesBadge}
        </div>
        <div class="job-meta">
          <span>${esc(j.department || 'Unknown')}</span>
          ${j.job_id ? `<span>${esc(j.job_id)}</span>` : ''}
          ${review} ${offline}
        </div>
        ${!isOpen && tagIds.length ? `<div class="job-tags">${tagIds.map(id => tagChip(id, false)).join('')}</div>` : ''}
      </div>
      <div class="job-dates">
        <span class="date-label">Deadline</span>
        <span class="deadline-date${dl.status ? '' : ' wide'}${dl.open ? ' open' : ''}" title="${esc(dl.title)}">${esc(dl.text)}</span>
        ${dl.status ? `<span class="deadline-status ${dl.status.cls}">${esc(dl.status.text)}</span>` : ''}
        <span class="date-label">First seen</span>
        <span class="seen-date"${j.first_seen ? ` title="First found by a fetch on ${esc(formatBerlinStamp(j.first_seen))} (Berlin time)"` : ''}>${esc(seen)}</span>
      </div>
      <div class="job-actions">
        ${pdf ? `<a class="action-btn small" href="${esc(pdf)}" target="_blank" rel="noopener noreferrer">PDF</a>` : ''}
      </div>
      ${isOpen ? detailsHtml(j) : ''}
    </div>`;
}

function renderJobs(jobs) {
  const container = $('jobsList');
  $('filteredCount').textContent = `${jobs.length} of ${allJobs.length} jobs`;

  if (jobs.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <p>No jobs match your filters</p>
      </div>
    `;
    return;
  }
  container.innerHTML = jobs.map((j, i) => cardHtml(j, i, true)).join('');
}

// Re-render a single card in place, keeping any text the user is still typing.
function updateCard(hash) {
  const el = document.querySelector(`.job-card[data-hash="${CSS.escape(hash)}"]`);
  const job = jobsByHash.get(hash);
  if (!el || !job) return;

  const draft = el.querySelector('form[data-action="add-note"] textarea')?.value || '';
  const editDrafts = new Map();
  el.querySelectorAll('.note[data-note-id] form textarea').forEach(t => {
    editDrafts.set(t.closest('.note').dataset.noteId, t.value);
  });

  const tmp = document.createElement('div');
  tmp.innerHTML = cardHtml(job, 0, false);
  const fresh = tmp.firstElementChild;
  el.replaceWith(fresh);

  const noteBox = fresh.querySelector('form[data-action="add-note"] textarea');
  if (noteBox) noteBox.value = draft;
  editDrafts.forEach((value, id) => {
    const t = fresh.querySelector(`.note[data-note-id="${CSS.escape(id)}"] form textarea`);
    if (t) t.value = value;
  });
  return fresh;
}

function updateStats() {
  $('totalJobs').textContent = allJobs.length;
  $('activeJobs').textContent = allJobs.filter(j => j.status === 'Online').length;
  // Every fetch stamps last_seen on each ad it sees, so the newest value is the last successful fetch.
  const last = allJobs.reduce((max, j) => (j.last_seen && j.last_seen > max ? j.last_seen : max), '');
  $('lastFetched').textContent = formatBerlinStamp(last);
}

// ---------- Charts ----------

function renderCharts(jobs) {
  const sourceData = {};
  jobs.forEach(j => {
    const s = j.department || 'Unknown';
    sourceData[s] = (sourceData[s] || 0) + 1;
  });

  const sortedSources = Object.entries(sourceData).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const labels = sortedSources.map(s => s[0]);
  const data = sortedSources.map(s => s[1]);
  const colors = labels.map(sourceColor);

  if (sourceChart) sourceChart.destroy();
  sourceChart = new Chart($('sourceChart'), {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderColor: 'transparent', borderWidth: 0, hoverOffset: 8 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: '#8888a0',
            font: { size: 10, family: FONT },
            padding: 8,
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true
          }
        }
      }
    }
  });

  const deadlineMap = {};
  jobs.forEach(j => {
    const d = deadlineDate(j);
    if (d) {
      const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
      deadlineMap[key] = (deadlineMap[key] || 0) + 1;
    }
  });

  const timelineEntries = Object.entries(deadlineMap).sort((a, b) => a[0].localeCompare(b[0]));
  const tlLabels = timelineEntries.map(e => {
    const [, m, d] = e[0].split('-');
    return `${+d}/${+m}`;
  });
  const tlData = timelineEntries.map(e => e[1]);

  if (timelineChart) timelineChart.destroy();
  timelineChart = new Chart($('timelineChart'), {
    type: 'bar',
    data: {
      labels: tlLabels,
      datasets: [{
        data: tlData,
        backgroundColor: 'rgba(108, 92, 231, 0.6)',
        borderColor: '#6c5ce7',
        borderWidth: 1,
        borderRadius: 4,
        barPercentage: 0.8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: '#555568', font: { size: 9, family: FONT }, maxRotation: 45 },
          grid: { color: 'rgba(42,42,58,0.5)' }
        },
        y: {
          ticks: { color: '#555568', font: { size: 9, family: FONT }, stepSize: 1 },
          grid: { color: 'rgba(42,42,58,0.5)' }
        }
      }
    }
  });
}

function render() {
  const jobs = sortJobs(getFilteredJobs());
  updateStats();
  renderJobs(jobs);
  renderCharts(jobs);
}

// ---------- Hosted API ----------

const SESSION_EXPIRED = 'Your login has expired. Reload the page to sign in again.';

async function api(method, path, body) {
  const opts = { method, headers: {}, redirect: 'manual', cache: 'no-store' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error('Network error. Check your connection and try again.');
  }
  // Cloudflare Access answers an expired session with a redirect to its login page.
  if (res.type === 'opaqueredirect') throw new Error(SESSION_EXPIRED);
  const isJson = (res.headers.get('Content-Type') || '').includes('application/json');
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    if (!isJson && (res.status === 401 || res.status === 403)) throw new Error(SESSION_EXPIRED);
    throw new Error((data && data.error) || `Request failed (${res.status}).`);
  }
  return data;
}

async function loadAnnotations() {
  const data = await api('GET', 'api/annotations');
  notesByJob = new Map();
  tagsById = new Map();
  tagIdsByJob = new Map();
  (data.tags || []).forEach(t => tagsById.set(t.id, t));
  (data.notes || []).forEach(n => {
    if (!notesByJob.has(n.job_hash)) notesByJob.set(n.job_hash, []);
    notesByJob.get(n.job_hash).push(n);
  });
  (data.job_tags || []).forEach(jt => {
    if (!tagsById.has(jt.tag_id)) return;
    if (!tagIdsByJob.has(jt.job_hash)) tagIdsByJob.set(jt.job_hash, []);
    tagIdsByJob.get(jt.job_hash).push(jt.tag_id);
  });
  for (const ids of tagIdsByJob.values()) {
    ids.sort((a, b) => tagsById.get(a).name.localeCompare(tagsById.get(b).name));
  }
}

// After any change: refresh shared data so everyone's latest edits show up too.
// The edited card is updated in place and stays visible even if it no longer
// matches the tag filter (for example after tagging an ad under "No tags"), so
// several tags can be added in a row. The list catches up on the next filter change.
async function afterChange(hash) {
  await loadAnnotations();
  buildTagPanel();
  updateTagSuggestions();
  return updateCard(hash);
}

async function runAction(button, fn) {
  if (button) button.disabled = true;
  try {
    await fn();
  } catch (err) {
    toast(err.message, true);
  } finally {
    if (button && button.isConnected) button.disabled = false;
  }
}

function setupHostedHandlers() {
  const list = $('jobsList');

  list.addEventListener('click', e => {
    const card = e.target.closest('.job-card');
    if (!card) return;
    const hash = card.dataset.hash;
    const action = e.target.closest('[data-action]');

    if (action && action.tagName === 'BUTTON') {
      const noteId = action.closest('.note')?.dataset.noteId;
      switch (action.dataset.action) {
        case 'remove-tag':
          runAction(action, async () => {
            await api('DELETE', `api/jobs/${hash}/tags/${action.dataset.tagId}`);
            await afterChange(hash);
          });
          return;
        case 'edit-note':
          editingNotes.add(Number(noteId));
          updateCard(hash)?.querySelector(`.note[data-note-id="${CSS.escape(noteId)}"] textarea`)?.focus();
          return;
        case 'cancel-edit':
          editingNotes.delete(Number(noteId));
          updateCard(hash);
          return;
        case 'delete-note':
          if (!confirm('Delete this note?')) return;
          runAction(action, async () => {
            await api('DELETE', `api/notes/${noteId}`);
            editingNotes.delete(Number(noteId));
            await afterChange(hash);
          });
          return;
      }
    }

    // Clicks inside links, forms or the details area should not collapse the card.
    if (e.target.closest('a, button, input, textarea, form, .job-details')) return;
    if (expanded.has(hash)) expanded.delete(hash); else expanded.add(hash);
    updateCard(hash);
  });

  list.addEventListener('submit', e => {
    e.preventDefault();
    const form = e.target;
    const card = form.closest('.job-card');
    if (!card) return;
    const hash = card.dataset.hash;
    const button = form.querySelector('button[type="submit"]');

    switch (form.dataset.action) {
      case 'add-tag': {
        const name = form.elements.tag.value.trim();
        if (!name) return;
        runAction(button, async () => {
          await api('POST', `api/jobs/${hash}/tags`, { name });
          const fresh = await afterChange(hash);
          fresh?.querySelector('form[data-action="add-tag"] input')?.focus();
        });
        return;
      }
      case 'add-note': {
        const box = form.elements.text;
        const text = box.value.trim();
        if (!text) return;
        runAction(button, async () => {
          await api('POST', `api/jobs/${hash}/notes`, { text });
          box.value = '';
          const fresh = await afterChange(hash);
          const freshBox = fresh?.querySelector('form[data-action="add-note"] textarea');
          if (freshBox) freshBox.value = '';
        });
        return;
      }
      case 'save-note': {
        const noteId = form.closest('.note').dataset.noteId;
        const text = form.elements.text.value.trim();
        if (!text) return;
        runAction(button, async () => {
          await api('PATCH', `api/notes/${noteId}`, { text });
          editingNotes.delete(Number(noteId));
          await afterChange(hash);
        });
        return;
      }
    }
  });

  $('tagChips').addEventListener('click', e => {
    const chip = e.target.closest('[data-tag-id], [data-untagged]');
    if (!chip) return;
    if (chip.dataset.untagged) {
      filterUntagged = !filterUntagged;
    } else {
      const id = Number(chip.dataset.tagId);
      if (activeTags.has(id)) activeTags.delete(id); else activeTags.add(id);
    }
    buildTagPanel();
    render();
  });
}

// ---------- Fetch button ----------

let fetchWasRunning = false;
let fetchPollTimer = null;

async function refreshFetchStatus() {
  clearTimeout(fetchPollTimer);
  let st;
  try {
    st = await api('GET', 'api/fetch-status');
  } catch {
    fetchPollTimer = setTimeout(refreshFetchStatus, FETCH_POLL_MS * 3);
    return;
  }
  if (!st || !st.enabled) {
    $('fetchCtl').hidden = true;
    return;
  }
  const left = Math.max(0, st.limit - st.used);
  $('fetchCtl').hidden = false;
  $('fetchLeft').textContent = `${left}/${st.limit} left today`;
  $('fetchBtn').disabled = st.running || left === 0;
  $('fetchBtn').textContent = st.running ? 'Fetching...' : 'Fetch now';

  if (fetchWasRunning && !st.running) {
    await reloadJobs();
    toast('Fetch finished. The list is up to date.');
  }
  fetchWasRunning = st.running;
  if (st.running) fetchPollTimer = setTimeout(refreshFetchStatus, FETCH_POLL_MS);
}

async function startFetch() {
  const left = $('fetchLeft').textContent.split('/')[0];
  if (!confirm(`Start a fetch now? Fetches are shared by all council members (${left} left today).`)) return;
  $('fetchBtn').disabled = true;
  try {
    await api('POST', 'api/fetch', {});
    toast('Fetch started. New ads appear here in a few minutes.');
    fetchWasRunning = true;
  } catch (err) {
    toast(err.message, true);
  }
  refreshFetchStatus();
}

// ---------- Loading ----------

function indexJobs() {
  jobsByHash = new Map(allJobs.map(j => [j.hash, j]));
  serverOrder = new Map(allJobs.map((j, i) => [j.hash, i]));
}

async function reloadJobs() {
  try {
    const res = await fetch('api/jobs.json', { cache: 'no-store' });
    if (!res.ok) return;
    allJobs = await res.json();
    indexJobs();
    buildSourceList();
    if (me) await loadAnnotations().catch(() => {});
    buildTagPanel();
    updateTagSuggestions();
    render();
  } catch {
    // Keep showing the current list; the next reload will try again.
  }
}

// Only the hosted Worker answers api/me; the local server returns 404.
async function detectHosted() {
  try {
    const res = await fetch('api/me', { cache: 'no-store', redirect: 'manual' });
    if (!res.ok) return;
    const data = await res.json();
    if (data && typeof data.email === 'string') me = data.email;
  } catch {
    return;
  }
  if (!me) return;
  try {
    await loadAnnotations();
  } catch (err) {
    toast(err.message, true);
  }
  $('tagPanel').hidden = false;
  buildTagPanel();
  updateTagSuggestions();
  setupHostedHandlers();
  $('fetchBtn').addEventListener('click', startFetch);
  refreshFetchStatus();
}

function setupLocalHandlers() {
  // Read-only mode: clicking a card opens its PDF, as before.
  $('jobsList').addEventListener('click', e => {
    if (me || e.target.closest('a')) return;
    const card = e.target.closest('.job-card');
    const job = card && jobsByHash.get(card.dataset.hash);
    if (job && job.pdf) window.open(encodeURI(job.pdf), '_blank', 'noopener');
  });
}

async function init() {
  try {
    const res = await fetch('api/jobs.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allJobs = await res.json();
  } catch (err) {
    $('jobsList').innerHTML = `
      <div class="empty-state">
        <p>Failed to load the job list. Locally, start the dashboard with <code>python src/jobs.py serve</code>.</p>
      </div>
    `;
    console.error(err);
    return;
  }
  indexJobs();
  buildSourceList();
  buildFetchChips();
  buildSortChips();
  setupLocalHandlers();
  await detectHosted();
  render();
}

$('searchInput').addEventListener('input', render);
$('dateFrom').addEventListener('change', render);
$('dateTo').addEventListener('change', render);

$('sortChips').addEventListener('click', e => {
  const chip = e.target.closest('[data-sort]');
  if (!chip || chip.dataset.sort === sortBy) return;
  sortBy = chip.dataset.sort;
  buildSortChips();
  render();
});

$('clearFilters').addEventListener('click', () => {
  $('searchInput').value = '';
  $('dateFrom').value = '';
  $('dateTo').value = '';
  activeSources.clear();
  Object.keys(sourceCounts).forEach(s => activeSources.add(s));
  updateSourceChips();
  activeStatuses.clear();
  activeStatuses.add('Online');
  updateFetchChips();
  activeTags.clear();
  filterUntagged = false;
  if (me) buildTagPanel();
  render();
});

init();
