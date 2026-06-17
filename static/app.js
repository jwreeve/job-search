'use strict';

let allJobs = [];
let pollTimer = null;
let currentTab = 'all';

// Elapsed timer state
let elapsedTimer = null;
let scanStartClientMs = null;
let scanStartOffsetMs = 0;
let progressOpen = false;
let progressAutoOpened = false;

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
      if (!pollTimer) {
        pollTimer = setInterval(refreshStats, 6000);
      }
      await loadProgress();
    } else {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        await fetchJobs();
      }
      setScanUI(false);
    }
  } catch (e) { /* ignore */ }
}

// ── Elapsed timer ─────────────────────────────────────────────────────────────

function initElapsed(serverElapsedSeconds) {
  scanStartOffsetMs = (serverElapsedSeconds || 0) * 1000;
  scanStartClientMs = Date.now();
}

function getElapsedSeconds() {
  if (scanStartClientMs === null) return 0;
  return ((Date.now() - scanStartClientMs) + scanStartOffsetMs) / 1000;
}

function updateElapsed() {
  const s = getElapsedSeconds();
  const mins = Math.floor(s / 60);
  const secs = Math.round(s % 60);
  setText('scan-elapsed', mins > 0 ? `${mins}m ${secs}s` : `${secs}s`);
}

// ── Progress panel ────────────────────────────────────────────────────────────

async function loadProgress() {
  try {
    const data = await (await fetch('/api/scan/progress')).json();
    if (data.in_progress && scanStartClientMs === null) {
      initElapsed(data.elapsed_seconds || 0);
    }
    renderProgress(data.sites || []);
  } catch (e) { /* ignore */ }
}

function renderProgress(sites) {
  if (!sites.length) return;
  const done = sites.filter(s => ['success', 'error', 'stopped'].includes(s.status)).length;
  setText('progress-count', `${done}/${sites.length}`);

  const grid = document.getElementById('progress-grid');
  grid.innerHTML = sites.map(s => {
    const icons = { pending: '○', running: '▸', success: '✓', error: '✕', stopped: '–' };
    const icon = icons[s.status] || '○';
    let detail = '';
    if (s.status === 'success') detail = `${s.jobs_found} job${s.jobs_found !== 1 ? 's' : ''}`;
    else if (s.status === 'error') detail = s.error ? s.error.slice(0, 50) : 'error';
    else if (s.status === 'stopped') detail = 'stopped';
    return `<div class="progress-site status-${s.status}">` +
      `<span class="ps-icon">${icon}</span>` +
      `<span class="ps-name">${esc(s.name)}</span>` +
      `<span class="ps-detail">${esc(detail)}</span>` +
      `</div>`;
  }).join('');
}

function toggleProgress() {
  progressOpen = !progressOpen;
  document.getElementById('progress-panel').classList.toggle('hidden', !progressOpen);
  document.getElementById('progress-arrow').textContent = progressOpen ? '▲' : '▼';
}

async function stopScan() {
  const btn = document.getElementById('stop-btn');
  btn.disabled = true;
  btn.textContent = 'Stopping…';
  await fetch('/api/scan/stop', { method: 'POST' });
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

  if (scanning) {
    if (!elapsedTimer) {
      elapsedTimer = setInterval(updateElapsed, 1000);
    }
    if (!progressAutoOpened) {
      progressAutoOpened = true;
      progressOpen = true;
      document.getElementById('progress-panel').classList.remove('hidden');
      document.getElementById('progress-arrow').textContent = '▲';
    }
  } else {
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
    scanStartClientMs = null;
    progressAutoOpened = false;
    progressOpen = false;
    document.getElementById('progress-panel').classList.add('hidden');
    document.getElementById('progress-arrow').textContent = '▼';
    const stopBtn = document.getElementById('stop-btn');
    stopBtn.disabled = false;
    stopBtn.textContent = '⬛ Stop & Load';
    setText('progress-count', '0/0');
  }
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
        <span class="job-date" title="First seen in a scan on ${esc(fmtDate(j.first_seen))}">First seen ${fmtDate(j.first_seen)}</span>
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
  initElapsed(0);
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
          <th>Time</th><th>Site</th><th>Found</th><th>New</th><th>Already Tracked</th><th>Status</th>
        </tr>
      </thead>
      <tbody>
        ${logs.map(l => `
          <tr>
            <td>${fmtDate(l.scanned_at)}</td>
            <td>${esc(l.source_name || '')}</td>
            <td>${l.jobs_found}</td>
            <td>${l.jobs_new ?? 0}</td>
            <td${l.jobs_duplicate ? ' title="Matched a job already seen in a previous scan — not shown as new"' : ''}>${l.jobs_duplicate ?? 0}</td>
            <td class="status-${l.status}">${l.status}${
              l.error_message ? ` — ${esc(l.error_message.slice(0, 60))}` : ''
            }</td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
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
