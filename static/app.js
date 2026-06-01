'use strict';

let allJobs = [];
let pollTimer = null;
let currentTab = 'all';

// ── Bootstrap ────────────────────────────────────────────────────────────────

async function init() {
  await fetchJobs();
  setInterval(refreshStats, 30_000);
}

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchJobs() {
  show('loading');
  hide('empty-state');
  try {
    const res = await fetch('/api/jobs');
    allJobs = await res.json();
    populateFilters(allJobs);
    updateSavedCount();
    applyFilters();
    await refreshStats();
  } catch (e) {
    console.error('Failed to load jobs', e);
  } finally {
    hide('loading');
  }
}

async function refreshStats() {
  try {
    const s = await (await fetch('/api/stats')).json();
    setText('new-count', s.new_jobs);
    setText('total-count', s.total_jobs);
    setText('site-count', s.sites_count);
    setText('last-scan', s.last_scan ? relativeTime(s.last_scan) : 'Never');

    if (s.scan_in_progress) {
      setScanUI(true);
    } else {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        setScanUI(false);
        await fetchJobs(); // refresh after scan finishes
      }
    }
  } catch (e) { /* ignore */ }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tab-all').classList.toggle('active', tab === 'all');
  document.getElementById('tab-saved').classList.toggle('active', tab === 'saved');
  applyFilters();
}

function updateSavedCount() {
  setText('saved-tab-count', allJobs.filter(j => j.is_saved).length);
}

function applyFilters() {
  const q = document.getElementById('q').value.toLowerCase();
  const site = document.getElementById('filter-site').value;
  const kw = document.getElementById('filter-kw').value.toLowerCase();
  const newOnly = document.getElementById('new-only').checked;

  let filtered = currentTab === 'saved' ? allJobs.filter(j => j.is_saved) : allJobs;
  if (newOnly) filtered = filtered.filter(j => j.is_new);
  if (site) filtered = filtered.filter(j => j.source_name === site);
  if (kw) filtered = filtered.filter(j => j.matched_keywords.toLowerCase().includes(kw));
  if (q) {
    filtered = filtered.filter(j =>
      j.title.toLowerCase().includes(q) ||
      j.source_name.toLowerCase().includes(q) ||
      (j.matched_keywords || '').toLowerCase().includes(q)
    );
  }

  renderJobs(filtered);
  setText('result-count', `${filtered.length} position${filtered.length !== 1 ? 's' : ''} found`);
}

function renderJobs(jobs) {
  const grid = document.getElementById('jobs-grid');

  if (!jobs.length) {
    grid.innerHTML = '';
    show('empty-state');
    return;
  }
  hide('empty-state');

  grid.innerHTML = jobs.map(j => {
    const kws = (j.matched_keywords || '').split(', ').filter(Boolean);
    return `
    <article class="job-card${j.is_new ? ' is-new' : ''}${j.is_saved ? ' is-saved' : ''}" data-id="${esc(j.id)}">
      ${j.is_new ? '<span class="new-badge">NEW</span>' : ''}
      ${j.is_saved ? '<span class="saved-badge">★ SAVED</span>' : ''}
      <div class="job-main">
        <div class="job-title">
          <a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a>
        </div>
        <div class="job-sub">
          <span class="job-source">${esc(j.source_name)}</span>
          ${kws.length ? '<span class="job-sep">·</span>' : ''}
          <div class="job-keywords">
            ${kws.map(k => `<span class="kw-badge">${esc(k)}</span>`).join('')}
          </div>
        </div>
      </div>
      <div class="job-right">
        <span class="job-date">${fmtDate(j.first_seen)}</span>
        <div class="job-actions">
          ${j.is_new
            ? `<button class="btn-xs" onclick="markSeen('${esc(j.id)}')">Mark Seen</button>`
            : ''}
          <button class="btn-xs${j.is_saved ? ' save-active' : ' save'}" onclick="toggleSave('${esc(j.id)}')">
            ${j.is_saved ? '★ Saved' : '☆ Save'}
          </button>
          ${!j.is_saved
            ? `<button class="btn-xs danger" onclick="removeJob('${esc(j.id)}')">Remove</button>`
            : ''}
          <a class="btn-xs" href="${esc(j.url)}" target="_blank" rel="noopener">Open ↗</a>
        </div>
      </div>
    </article>`;
  }).join('');
}

function populateFilters(jobs) {
  const sites = [...new Set(jobs.map(j => j.source_name))].sort();
  const kws = [...new Set(
    jobs.flatMap(j => (j.matched_keywords || '').split(', ').filter(Boolean))
  )].sort();

  const siteEl = document.getElementById('filter-site');
  const cur = siteEl.value;
  siteEl.innerHTML = '<option value="">All Sites</option>' +
    sites.map(s => `<option${s === cur ? ' selected' : ''}>${esc(s)}</option>`).join('');

  const kwEl = document.getElementById('filter-kw');
  const curKw = kwEl.value;
  kwEl.innerHTML = '<option value="">All Keywords</option>' +
    kws.map(k => `<option${k.toLowerCase() === curKw ? ' selected' : ''}>${esc(k)}</option>`).join('');
}

// ── Actions ────────────────────────────────────────────────────────────────────

async function markSeen(id) {
  await fetch(`/api/jobs/${id}/mark-seen`, { method: 'POST' });
  const job = allJobs.find(j => j.id === id);
  if (job) job.is_new = false;
  applyFilters();
  await refreshStats();
}

async function removeJob(id) {
  if (!confirm('Remove this job from the list?')) return;
  await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
  allJobs = allJobs.filter(j => j.id !== id);
  populateFilters(allJobs);
  applyFilters();
  await refreshStats();
}

async function toggleSave(id) {
  const res = await fetch(`/api/jobs/${id}/toggle-save`, { method: 'POST' });
  const data = await res.json();
  const job = allJobs.find(j => j.id === id);
  if (job) job.is_saved = data.is_saved;
  updateSavedCount();
  applyFilters();
}

async function clearList() {
  if (!confirm('Clear all unsaved jobs? This cannot be undone.')) return;
  await fetch('/api/jobs', { method: 'DELETE' });
  await fetchJobs();
}

async function markAllSeen() {
  if (!confirm('Mark all new jobs as seen?')) return;
  await fetch('/api/jobs/mark-all-seen', { method: 'POST' });
  allJobs.forEach(j => j.is_new = false);
  applyFilters();
  await refreshStats();
}

async function triggerScan() {
  const res = await fetch('/api/scan', { method: 'POST' });
  const data = await res.json();
  if (data.status === 'already_running') {
    alert('A scan is already running.');
    return;
  }
  setScanUI(true);
  pollTimer = setInterval(refreshStats, 6000);
}

// ── Logs ───────────────────────────────────────────────────────────────────────

async function toggleLogs() {
  const panel = document.getElementById('logs-panel');
  const btn = document.getElementById('logs-toggle');
  if (panel.classList.contains('hidden')) {
    await loadLogs();
    panel.classList.remove('hidden');
    btn.textContent = '▲ Scan History';
  } else {
    panel.classList.add('hidden');
    btn.textContent = '▼ Scan History';
  }
}

async function loadLogs() {
  const logs = await (await fetch('/api/scan/logs')).json();
  const panel = document.getElementById('logs-panel');
  if (!logs.length) {
    panel.innerHTML = '<p style="padding:1rem;color:var(--muted)">No scan history yet.</p>';
    return;
  }
  panel.innerHTML = `
    <table class="logs-table">
      <thead>
        <tr>
          <th>Time</th><th>Site</th><th>Jobs Found</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${logs.map(l => `
          <tr>
            <td>${fmtDate(l.scanned_at)}</td>
            <td>${esc(l.source_name || '')}</td>
            <td>${l.jobs_found}</td>
            <td class="status-${l.status}">${l.status}${
              l.error_message ? ` — ${esc(l.error_message.slice(0, 60))}` : ''
            }</td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
}

// ── Scan UI helpers ────────────────────────────────────────────────────────────

function setScanUI(scanning) {
  const btn = document.getElementById('scan-btn');
  const spinner = document.getElementById('scan-spinner');
  const label = document.getElementById('scan-label');
  const banner = document.getElementById('scan-banner');

  btn.disabled = scanning;
  spinner.classList.toggle('hidden', !scanning);
  label.textContent = scanning ? 'Scanning…' : '▶ Scan Now';
  banner.classList.toggle('hidden', !scanning);
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function esc(str) {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(String(str ?? '')));
  return d.innerHTML;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function relativeTime(iso) {
  const diff = (Date.now() - new Date(iso).getTime()) / 60000;
  if (diff < 1) return 'just now';
  if (diff < 60) return `${Math.round(diff)}m ago`;
  if (diff < 1440) return `${Math.round(diff / 60)}h ago`;
  return `${Math.round(diff / 1440)}d ago`;
}

// ── Start ─────────────────────────────────────────────────────────────────────
init();
