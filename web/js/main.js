import { CONFIG } from './config.js';
import { Scene } from './scene.js';

const $ = (id) => document.getElementById(id);
const scene = new Scene($('cloud'), $('featured'));
const statusEl = $('status');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PROVIDER = { gdrive: 'gdrive', dropbox: 'dropbox', gphotos: 'gphotos' };
const LABELS = {
  local: ['Photo folder', '/Users/me/Pictures'],
  gdrive: ['Drive folder link or ID (blank = My Drive)', 'https://drive.google.com/drive/folders/…'],
  dropbox: ['Dropbox folder (blank = whole Dropbox)', '/Photos'],
};
let info = { connected: {}, configured: {}, gphotos_saved: false };

function setStatus(msg, isError = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle('error', isError);
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.error || 'Request failed'), { auth: data.auth });
  return data;
}

function loadImage(url) {
  return new Promise((resolve) => {
    const el = new Image();
    el.decoding = 'async';
    el.draggable = false;
    el.onload = () => resolve({ el, aspect: el.naturalWidth / el.naturalHeight });
    el.onerror = () => resolve(null);
    el.src = url;
  });
}

async function showCollection() {
  const { images } = await api('/api/images');
  const pick = images.sort(() => Math.random() - 0.5).slice(0, CONFIG.maxPhotos);
  setStatus(`Loading ${pick.length} photos…`);
  const loaded = (await Promise.all(pick.map((i) => loadImage(i.url)))).filter(Boolean);
  if (!loaded.length) throw new Error('None of the images could be decoded.');
  scene.setPhotos(loaded);
  setStatus(`Showing ${loaded.length} of ${images.length} photos.`);
}

// --- panel state -------------------------------------------------------------
const kindEl = $('kind');
const panel = $('panel');

function saved() { try { return JSON.parse(localStorage.getItem('photocloud.source') || '{}'); } catch { return {}; } }
function remember(cfg) { localStorage.setItem('photocloud.source', JSON.stringify(cfg)); }

function currentConfig() {
  return { kind: kindEl.value, path: $('path').value, recursive: $('recursive').checked };
}

function refreshPanel() {
  const kind = kindEl.value;
  const remote = kind !== 'local';
  const isPhotos = kind === 'gphotos';
  const connected = !!info.connected[PROVIDER[kind]];

  $('path-group').hidden = isPhotos;
  $('pick').hidden = !isPhotos;
  $('conn').hidden = !remote;
  if (LABELS[kind]) {
    $('path-label').textContent = LABELS[kind][0];
    $('path').placeholder = LABELS[kind][1];
  }
  const text = $('conn-text');
  const needs = kind === 'dropbox' ? info.configured.dropbox : info.configured.google;
  text.textContent = connected ? 'Connected' : needs ? 'Not connected' : 'Not set up (see README)';
  text.classList.toggle('ok', connected);
  $('conn-btn').textContent = connected ? 'Disconnect' : 'Connect';
  $('conn-btn').disabled = !connected && !needs;
  // Google Photos: the button picks; "Load" re-uses the saved selection.
  $('submit').textContent = isPhotos ? 'Use my saved selection' : 'Load / refresh';
  $('submit').disabled = isPhotos && !info.gphotos_saved;
  $('pick').disabled = !connected;
}

async function refreshInfo() {
  info = await api('/api/state');
  refreshPanel();
  return info;
}

kindEl.addEventListener('change', () => {
  const s = saved();
  $('path').value = s.kind === kindEl.value ? (s.path || '') : '';
  setStatus('');
  refreshPanel();
});

// --- connecting accounts -----------------------------------------------------
async function connect(kind) {
  const win = window.open(`/oauth/start/${PROVIDER[kind]}`, '_blank');
  if (!win) { setStatus('Allow pop-ups for this page, then try again.', true); return false; }
  setStatus('Finish signing in in the new tab…');
  for (let i = 0; i < 120; i++) {               // wait up to ~3 minutes
    await sleep(1500);
    await refreshInfo();
    if (info.connected[PROVIDER[kind]]) { setStatus('Connected.'); return true; }
    if (win.closed && !info.connected[PROVIDER[kind]] && i > 2) break;
  }
  setStatus('Not connected.', true);
  return false;
}

$('conn-btn').addEventListener('click', async () => {
  const kind = kindEl.value;
  try {
    if (info.connected[PROVIDER[kind]]) {
      await api('/api/disconnect', { provider: PROVIDER[kind] });
      await refreshInfo();
      setStatus('Disconnected.');
    } else {
      await connect(kind);
    }
  } catch (err) { setStatus(err.message, true); }
});

// --- loading a source --------------------------------------------------------
async function loadSource(cfg) {
  try {
    await api('/api/source', cfg);
    remember(cfg);
    await refreshInfo();
    await showCollection();
    return true;
  } catch (err) {
    setStatus(err.message, true);
    if (err.auth) await refreshInfo();
    return false;
  }
}

// Google Photos: Google only lets the user pick photos in its own picker.
$('pick').addEventListener('click', async () => {
  const win = window.open('', '_blank');          // open synchronously so pop-up blockers allow it
  try {
    setStatus('Opening Google Photos…');
    const { pickerUri } = await api('/api/gphotos/start', {});
    if (win) win.location = pickerUri; else { setStatus('Allow pop-ups, then try again.', true); return; }
    for (;;) {
      const s = await api('/api/gphotos/status');
      if (s.state === 'error') throw new Error(s.message);
      if (s.state === 'done') break;
      setStatus(s.state === 'downloading' && s.total ? `Downloading ${s.done}/${s.total}…` : s.message);
      await sleep(Math.max(s.poll_seconds, 2) * 1000);
    }
    await refreshInfo();
    if (await loadSource({ kind: 'gphotos' })) togglePanel(false);
  } catch (err) {
    if (win) win.close();
    setStatus(err.message, true);
  }
});

panel.addEventListener('submit', async (e) => {
  e.preventDefault();
  setStatus('Loading…');
  if (await loadSource(currentConfig())) togglePanel(false);
});

// --- settings UI: gear appears on mouse movement, hides when idle ---------
let idle;
function wake() {
  document.body.classList.add('active');
  clearTimeout(idle);
  idle = setTimeout(() => document.body.classList.remove('active'), 3000);
}
addEventListener('mousemove', wake);
function togglePanel(open = panel.hidden) {
  panel.hidden = !open;
  document.body.classList.toggle('panel-open', open);
  if (open) { refreshInfo().catch(() => {}); kindEl.focus(); }
}
$('gear').addEventListener('click', () => togglePanel());
addEventListener('keydown', (e) => { if (e.key === 'Escape') togglePanel(false); });

// --- startup ---------------------------------------------------------------
(async () => {
  const s = saved();
  // Older versions stored only the local path.
  const legacy = localStorage.getItem('photocloud.path');
  const cfg = s.kind ? s : (legacy ? { kind: 'local', path: legacy, recursive: !!localStorage.getItem('photocloud.recursive') } : {});
  kindEl.value = cfg.kind || 'local';
  $('path').value = cfg.path || '';
  $('recursive').checked = !!cfg.recursive;
  await refreshInfo();

  if (info.count > 0) {                       // a source was already loaded via the command line
    kindEl.value = info.kind;
    refreshPanel();
    try { await showCollection(); return; } catch (err) { setStatus(err.message, true); }
  } else if (cfg.kind && (cfg.kind === 'local' ? cfg.path : cfg.kind !== 'gphotos' || info.gphotos_saved)) {
    if (await loadSource({ ...cfg, kind: cfg.kind })) return;
  }
  togglePanel(true);
  wake();
  if (!statusEl.textContent) setStatus('Choose a photo source to begin.');
})();
