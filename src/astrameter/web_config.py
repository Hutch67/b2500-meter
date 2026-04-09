"""
Web-based configuration editor for AstraMeter.

Provides helpers and an HTML page for reading and editing config.ini via a browser.
"""

import configparser
import contextlib
import errno
import json
import os
import shutil
import tempfile
import threading
from collections import OrderedDict

CONFIG_EDITOR_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AstraMeter &ndash; Configuration Editor</title>
<style>
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f0f2f5;
  color: #1a1a2e;
  margin: 0;
  min-height: 100vh;
}
header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  padding: 1rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  box-shadow: 0 2px 8px rgba(0,0,0,.3);
}
header h1 { font-size: 1.25rem; font-weight: 600; margin: 0; }
header .subtitle { font-size: 0.8rem; opacity: .7; margin: 0; }
main {
  max-width: 900px;
  margin: 1.5rem auto;
  padding: 0 1rem 4rem;
}
.banner {
  display: none;
  background: #fff3cd;
  border: 1px solid #ffc107;
  border-radius: 8px;
  padding: .75rem 1rem;
  margin-bottom: 1rem;
  font-size: .875rem;
  color: #856404;
}
.banner.visible { display: flex; align-items: center; gap: .5rem; }
.section-card {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,.1);
  margin-bottom: 1rem;
  overflow: hidden;
}
.section-header {
  display: flex;
  align-items: center;
  padding: .6rem 1rem;
  background: #16213e;
  color: #fff;
  cursor: pointer;
  user-select: none;
  gap: .5rem;
}
.section-header h2 {
  font-size: .95rem;
  font-weight: 600;
  margin: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: .5rem;
}
.section-header h2 input {
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255,255,255,.4);
  color: #fff;
  font-size: .95rem;
  font-weight: 600;
  width: auto;
  min-width: 120px;
  padding: 0 2px;
  outline: none;
}
.section-header h2 input:focus { border-bottom-color: #4ecca3; }
.section-header .chevron {
  transition: transform .2s;
  font-size: .75rem;
}
.section-header.collapsed .chevron { transform: rotate(-90deg); }
.section-body {
  padding: .5rem 0;
}
.section-body.hidden { display: none; }
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: .45rem .9rem;
  text-align: left;
  font-size: .875rem;
}
th {
  color: #888;
  font-weight: 500;
  font-size: .75rem;
  text-transform: uppercase;
  letter-spacing: .05em;
  border-bottom: 1px solid #f0f0f0;
}
tr:not(:last-child) td { border-bottom: 1px solid #f8f8f8; }
tr:hover td { background: #fafbff; }
td.key-cell { width: 35%; }
td.key-cell input, td.val-cell input, td.val-cell select {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: .35rem .5rem;
  font-size: .875rem;
  background: transparent;
  color: #1a1a2e;
  transition: border-color .15s, background .15s;
}
td.key-cell input:hover, td.val-cell input:hover, td.val-cell select:hover { border-color: #ddd; background: #f9f9f9; }
td.key-cell input:focus, td.val-cell input:focus, td.val-cell select:focus {
  border-color: #4ecca3;
  background: #fff;
  outline: none;
  box-shadow: 0 0 0 3px rgba(78,204,163,.15);
}
td.val-cell select { cursor: pointer; appearance: auto; }
td.action-cell { width: 36px; text-align: center; }
.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: .25rem;
  border-radius: 4px;
  color: #aaa;
  font-size: 1rem;
  line-height: 1;
  transition: color .15s, background .15s;
}
.btn-icon:hover { color: #e74c3c; background: #fdf0f0; }
.section-footer {
  padding: .4rem .9rem;
  border-top: 1px solid #f4f4f4;
  display: flex;
  gap: .5rem;
}
.btn {
  border: none;
  cursor: pointer;
  border-radius: 6px;
  font-size: .8rem;
  font-weight: 500;
  padding: .35rem .75rem;
  transition: opacity .15s, transform .1s;
}
.btn:hover { opacity: .88; }
.btn:active { transform: scale(.97); }
.btn-add-key { background: #eaf6f0; color: #27ae60; }
.btn-remove-section { background: #fdecea; color: #c0392b; margin-left: auto; }
.toolbar {
  display: flex;
  gap: .75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  align-items: center;
}
.btn-add-section { background: #e8f4fd; color: #2980b9; }
.btn-save {
  background: #4ecca3;
  color: #1a1a2e;
  font-weight: 700;
  font-size: .95rem;
  padding: .5rem 1.5rem;
  border-radius: 8px;
  margin-left: auto;
}
.btn-save:disabled { opacity: .5; cursor: not-allowed; }
.status-bar {
  position: fixed;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background: #222;
  color: #fff;
  border-radius: 8px;
  padding: .6rem 1.2rem;
  font-size: .875rem;
  box-shadow: 0 4px 16px rgba(0,0,0,.25);
  opacity: 0;
  pointer-events: none;
  transition: opacity .3s;
  white-space: nowrap;
}
.status-bar.success { background: #27ae60; }
.status-bar.error { background: #c0392b; }
.status-bar.visible { opacity: 1; pointer-events: auto; }
.btn-save-restart {
  background: #e67e22;
  color: #fff;
  font-weight: 700;
  font-size: .95rem;
  padding: .5rem 1.5rem;
  border-radius: 8px;
}
.btn-save-restart:disabled { opacity: .5; cursor: not-allowed; }
.overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(22, 33, 62, 0.92);
  z-index: 999;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  gap: 1rem;
}
.overlay.visible { display: flex; }
.overlay h2 { font-size: 1.5rem; margin: 0; }
.overlay p { font-size: 1rem; opacity: .75; margin: 0; }
.spinner {
  width: 48px; height: 48px;
  border: 4px solid rgba(255,255,255,.2);
  border-top-color: #4ecca3;
  border-radius: 50%;
  animation: spin .9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>
  <div>
    <h1>&#9889; AstraMeter &ndash; Configuration Editor</h1>
    <p class="subtitle">Edit and save your config.ini settings</p>
  </div>
</header>
<main>
  <div id="restart-banner" class="banner">
    <span>&#9888;&#65039;</span>
    <span>Configuration saved. <strong>Restart the service</strong> to apply the changes.</span>
  </div>

  <div class="toolbar">
    <button class="btn btn-add-section" onclick="addSection()">&#43; Add Section</button>
    <button id="save-btn" class="btn btn-save" onclick="saveConfig()">&#128190; Save Configuration</button>
    <button id="save-restart-btn" class="btn btn-save-restart" onclick="saveAndRestart()">&#9654; Save &amp; Restart</button>
  </div>

  <div id="config-container">
    <p class="loading">Loading configuration&hellip;</p>
  </div>
</main>
<div id="status-bar" class="status-bar"></div>
<div id="restart-overlay" class="overlay">
  <div class="spinner"></div>
  <h2>Restarting service&hellip;</h2>
  <p id="reconnect-msg">Reconnecting in <span id="reconnect-countdown">20</span>s</p>
</div>

<script>
/* ===== State ===== */
let currentConfig = {};   // { sectionName: { key: value, ... }, ... }
let sectionOrder = [];    // preserve section order

/* ===== Boot ===== */
async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    currentConfig = data.sections || {};
    sectionOrder = data.order || Object.keys(currentConfig);
    renderAll();
  } catch (e) {
    document.getElementById('config-container').innerHTML =
      '<p class="loading" style="color:#c0392b">&#10060; Failed to load configuration: ' + e.message + '</p>';
  }
}

/* ===== Rendering ===== */
function renderAll() {
  const container = document.getElementById('config-container');
  container.innerHTML = '';
  sectionOrder.forEach(sec => {
    container.appendChild(renderSection(sec, currentConfig[sec] || {}));
  });
}

function renderSection(sectionName, pairs) {
  const card = document.createElement('div');
  card.className = 'section-card';
  card.dataset.section = sectionName;

  // Header
  const header = document.createElement('div');
  header.className = 'section-header';
  header.innerHTML = `
    <h2>
      <span style="opacity:.6;font-size:.8rem">[</span>
      <input type="text" class="section-name-input" value="${esc(sectionName)}" title="Section name">
      <span style="opacity:.6;font-size:.8rem">]</span>
    </h2>
    <span class="chevron">&#9660;</span>`;
  header.addEventListener('click', (e) => {
    if (e.target.tagName === 'INPUT') return;
    header.classList.toggle('collapsed');
    card.querySelector('.section-body').classList.toggle('hidden');
  });

  // Body
  const body = document.createElement('div');
  body.className = 'section-body';
  const table = document.createElement('table');
  table.innerHTML = '<thead><tr><th>Key</th><th>Value</th><th></th></tr></thead>';
  const tbody = document.createElement('tbody');
  tbody.className = 'key-value-body';
  Object.entries(pairs).forEach(([k, v]) => {
    tbody.appendChild(renderRow(k, v));
  });
  table.appendChild(tbody);
  body.appendChild(table);

  // Footer
  const footer = document.createElement('div');
  footer.className = 'section-footer';
  footer.innerHTML = `
    <button class="btn btn-add-key" onclick="addKey(this)">&#43; Add Key</button>
    <button class="btn btn-remove-section" onclick="removeSection(this)">&#128465; Remove Section</button>`;

  card.appendChild(header);
  card.appendChild(body);
  card.appendChild(footer);
  return card;
}

/* ===== Key-type metadata ===== */
const KEY_TYPES = {
  // Booleans
  SKIP_POWERMETER_TEST:    { type: 'boolean' },
  WEB_CONFIG_ENABLED:      { type: 'boolean' },
  ENABLE_HEALTH_CHECK:     { type: 'boolean' },
  DISABLE_SUM_PHASES:      { type: 'boolean' },
  DISABLE_ABSOLUTE_VALUES: { type: 'boolean' },
  HTTPS:                   { type: 'boolean' },
  POWER_CALCULATE:         { type: 'boolean' },
  JSON_POWER_CALCULATE:    { type: 'boolean' },
  // Integers
  POLL_INTERVAL:           { type: 'integer' },
  PORT:                    { type: 'integer' },
  UNIT_ID:                 { type: 'integer' },
  ADDRESS:                 { type: 'integer' },
  COUNT:                   { type: 'integer' },
  // Floats
  THROTTLE_INTERVAL:       { type: 'float' },
  EMA_ALPHA:               { type: 'float', min: 0, max: 1 },
  EMA_INTERVAL:            { type: 'float' },
  POWER_OFFSET:            { type: 'float' },
  POWER_MULTIPLIER:        { type: 'float' },
  SLEW_RATE_WATTS_PER_SEC: { type: 'float' },
  DEADBAND_WATTS:          { type: 'float' },
  HOLD_TIME:               { type: 'float' },
  TIMEOUT:                 { type: 'float' },
  // Passwords
  PASS:                    { type: 'password' },
  PASSWORD:                { type: 'password' },
  ACCESSTOKEN:             { type: 'password' },
  // Enums
  TYPE:                    { type: 'select', options: ['1PM', 'PLUS1PM', 'EM', '3EM', '3EMPro'] },
  DEVICE_TYPE:             { type: 'select', options: ['ct002', 'ct003', 'shellypro3em', 'shellyemg3', 'shellyproem50'] },
  DATA_TYPE:               { type: 'select', options: ['UINT16', 'INT16', 'UINT32', 'INT32', 'FLOAT32', 'FLOAT64'] },
  BYTE_ORDER:              { type: 'select', options: ['BIG', 'LITTLE'] },
  WORD_ORDER:              { type: 'select', options: ['BIG', 'LITTLE'] },
  REGISTER_TYPE:           { type: 'select', options: ['HOLDING', 'INPUT'] },
};

function makeValueInput(key, value) {
  const info = KEY_TYPES[(key || '').toUpperCase()] || {};
  switch (info.type) {

    case 'boolean': {
      const sel = document.createElement('select');
      sel.className = 'val-input';
      const lower = String(value).toLowerCase();
      const boolOptions = ['True', 'False'];
      const normalised = ['true', 'yes', 'on', '1'].includes(lower) ? boolOptions[0] : boolOptions[1];
      boolOptions.forEach(opt => {
        const o = document.createElement('option');
        o.value = opt;
        o.textContent = opt;
        if (opt === normalised) o.selected = true;
        sel.appendChild(o);
      });
      return sel;
    }

    case 'integer': {
      const inp = document.createElement('input');
      inp.type = 'number';
      inp.step = '1';
      inp.className = 'val-input';
      inp.value = value;
      inp.placeholder = '0';
      return inp;
    }

    case 'float': {
      const inp = document.createElement('input');
      inp.type = 'number';
      inp.step = 'any';
      inp.className = 'val-input';
      inp.value = value;
      inp.placeholder = '0';
      if (info.min !== undefined) inp.min = info.min;
      if (info.max !== undefined) inp.max = info.max;
      return inp;
    }

    case 'password': {
      const wrapper = document.createElement('span');
      wrapper.style.cssText = 'display:flex;align-items:center;gap:4px;width:100%';
      const inp = document.createElement('input');
      inp.type = 'password';
      inp.className = 'val-input';
      inp.value = value;
      inp.autocomplete = 'off';
      inp.style.flex = '1';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn-icon';
      toggle.title = 'Show / hide';
      toggle.style.cssText = 'flex-shrink:0;font-size:.85rem;color:#aaa';
      toggle.textContent = '\uD83D\uDC41';
      toggle.addEventListener('click', () => {
        inp.type = inp.type === 'password' ? 'text' : 'password';
      });
      wrapper.appendChild(inp);
      wrapper.appendChild(toggle);
      return wrapper;
    }

    case 'select': {
      const sel = document.createElement('select');
      sel.className = 'val-input';
      const lower = String(value).toLowerCase();
      const hasMatch = info.options.some(o => o.toLowerCase() === lower);
      if (value !== '' && !hasMatch) {
        // Preserve an unknown current value as a custom option
        const o = document.createElement('option');
        o.value = value;
        o.textContent = value;
        o.selected = true;
        sel.appendChild(o);
      }
      info.options.forEach(opt => {
        const o = document.createElement('option');
        o.value = opt;
        o.textContent = opt;
        if (opt.toLowerCase() === lower) o.selected = true;
        sel.appendChild(o);
      });
      return sel;
    }

    default: {
      const inp = document.createElement('input');
      inp.type = 'text';
      inp.className = 'val-input';
      inp.value = value;
      inp.placeholder = 'value';
      return inp;
    }
  }
}

function renderRow(key, value) {
  const tr = document.createElement('tr');

  const keyTd = document.createElement('td');
  keyTd.className = 'key-cell';
  const keyInp = document.createElement('input');
  keyInp.type = 'text';
  keyInp.className = 'key-input';
  keyInp.value = key;
  keyInp.placeholder = 'KEY';
  keyTd.appendChild(keyInp);

  const valTd = document.createElement('td');
  valTd.className = 'val-cell';
  valTd.appendChild(makeValueInput(key, value));

  const actTd = document.createElement('td');
  actTd.className = 'action-cell';
  const delBtn = document.createElement('button');
  delBtn.className = 'btn-icon';
  delBtn.title = 'Remove key';
  delBtn.innerHTML = '&#215;';
  delBtn.addEventListener('click', function () { removeRow(this); });
  actTd.appendChild(delBtn);

  tr.appendChild(keyTd);
  tr.appendChild(valTd);
  tr.appendChild(actTd);

  // When the key name is changed, swap the value element to the right type.
  keyInp.addEventListener('change', () => {
    const elem = valTd.querySelector('.val-input');
    const currentVal = elem ? elem.value : '';
    valTd.replaceChildren(makeValueInput(keyInp.value, currentVal));
  });

  return tr;
}

/* ===== Actions ===== */
function addSection() {
  const sectionName = 'NEW_SECTION';
  let name = sectionName;
  let i = 1;
  while (sectionOrder.includes(name)) { name = sectionName + '_' + (i++); }
  sectionOrder.push(name);
  currentConfig[name] = {};
  const container = document.getElementById('config-container');
  container.appendChild(renderSection(name, {}));
  // Focus the section name input
  const lastCard = container.lastElementChild;
  const input = lastCard.querySelector('.section-name-input');
  input.select();
  input.focus();
}

function addKey(btn) {
  const card = btn.closest('.section-card');
  const tbody = card.querySelector('.key-value-body');
  tbody.appendChild(renderRow('', ''));
  tbody.lastElementChild.querySelector('.key-input').focus();
}

function removeRow(btn) {
  btn.closest('tr').remove();
}

function removeSection(btn) {
  const card = btn.closest('.section-card');
  const name = card.dataset.section;
  if (!confirm('Remove section [' + name + '] and all its keys?')) return;
  card.remove();
  sectionOrder = sectionOrder.filter(s => s !== name);
  delete currentConfig[name];
}

/* ===== Collect data from DOM ===== */
function collectConfig() {
  const result = {};
  const order = [];
  const seenSections = new Set();
  let hasEmptySection = false;
  document.querySelectorAll('.section-card').forEach(card => {
    const nameInput = card.querySelector('.section-name-input');
    const sectionName = nameInput.value.trim();
    if (!sectionName) {
      hasEmptySection = true;
      return;
    }
    if (seenSections.has(sectionName)) {
      throw new Error('Duplicate section name: [' + sectionName + ']');
    }
    seenSections.add(sectionName);
    const pairs = {};
    card.querySelectorAll('.key-value-body tr').forEach(tr => {
      const key = tr.querySelector('.key-input').value.trim();
      const val = tr.querySelector('.val-input').value.trim();
      if (key) pairs[key] = val;
    });
    result[sectionName] = pairs;
    order.push(sectionName);
  });
  if (hasEmptySection) {
    throw new Error('One or more sections have no name — fill in the section name or remove the section before saving.');
  }
  return { sections: result, order };
}

/* ===== Save ===== */
async function saveConfig() {
  const saveBtn = document.getElementById('save-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving\u2026';
  try {
    const payload = collectConfig();
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      showStatus('Configuration saved successfully!', 'success');
      document.getElementById('restart-banner').classList.add('visible');
    } else {
      showStatus('Error: ' + (data.error || 'Unknown error'), 'error');
    }
  } catch (e) {
    showStatus('Failed to save: ' + e.message, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '\uD83D\uDCBE Save Configuration';
  }
}

/* ===== Save & Restart ===== */
async function saveAndRestart() {
  const saveRestartBtn = document.getElementById('save-restart-btn');
  const saveBtn = document.getElementById('save-btn');
  saveRestartBtn.disabled = true;
  saveBtn.disabled = true;
  saveRestartBtn.textContent = 'Saving\u2026';
  try {
    // Step 1: save config
    const payload = collectConfig();
    const saveResp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const saveData = await saveResp.json();
    if (!saveResp.ok || !saveData.success) {
      showStatus('Error saving: ' + (saveData.error || 'Unknown error'), 'error');
      saveRestartBtn.disabled = false;
      saveBtn.disabled = false;
      saveRestartBtn.textContent = '\u25B6 Save & Restart';
      return;
    }

    // Step 2: trigger restart
    saveRestartBtn.textContent = 'Restarting\u2026';
    try {
      await fetch('/api/restart', { method: 'POST' });
    } catch (_) {
      // Connection drop is expected as the service restarts
    }

    // Step 3: show overlay and poll until the service is back
    showRestartOverlay();
  } catch (e) {
    showStatus('Failed: ' + e.message, 'error');
    saveRestartBtn.disabled = false;
    saveBtn.disabled = false;
    saveRestartBtn.textContent = '\u25B6 Save & Restart';
  }
}

function showRestartOverlay() {
  const overlay = document.getElementById('restart-overlay');
  overlay.classList.add('visible');
  let remaining = 20;
  document.getElementById('reconnect-countdown').textContent = remaining;

  const ticker = setInterval(() => {
    remaining -= 1;
    document.getElementById('reconnect-countdown').textContent = remaining;
  }, 1000);

  // Poll /health until it responds, then reload
  const poll = setInterval(async () => {
    try {
      const r = await fetch('/health', { cache: 'no-store' });
      if (r.ok) {
        clearInterval(poll);
        clearInterval(ticker);
        window.location.reload();
      }
    } catch (_) { /* still restarting */ }
  }, 1500);

  // Safety: reload after 30 s even if polling hasn't confirmed yet
  setTimeout(() => {
    clearInterval(poll);
    clearInterval(ticker);
    window.location.reload();
  }, 30000);
}

/* ===== Utilities ===== */
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

let statusTimer = null;
function showStatus(msg, type) {
  const bar = document.getElementById('status-bar');
  bar.textContent = msg;
  bar.className = 'status-bar visible ' + (type || '');
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { bar.className = 'status-bar'; }, 4000);
}

/* ===== Init ===== */
loadConfig();
</script>
</body>
</html>
"""


def read_config_as_dict(config_path: str) -> tuple[dict, list]:
    """
    Read config.ini and return (sections_dict, ordered_section_list).

    The sections_dict maps section names to dicts of key->value.
    Case of keys is preserved.
    """
    cfg = configparser.RawConfigParser(dict_type=OrderedDict)
    cfg.optionxform = str  # type: ignore[assignment]  # preserve key case
    if os.path.exists(config_path):
        cfg.read(config_path)
    sections: dict[str, dict[str, str]] = {}
    order = []
    for section in cfg.sections():
        sections[section] = dict(cfg.items(section))
        order.append(section)
    return sections, order


_CONFIG_WRITE_LOCK = threading.Lock()


def _atomic_write_lines(config_path: str, lines: list) -> None:
    """Write *lines* to *config_path* atomically via a temp-file + os.replace.

    On overlayfs / bind-mount environments (e.g. Home Assistant add-ons) the
    kernel returns EBUSY for rename(2) on a bind-mounted destination.  In that
    case we fall back to an in-place overwrite: copy the temp file content into
    the existing file, then remove the temp file.
    """
    dir_name = os.path.dirname(config_path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False) as tmp:
        tmp.writelines(lines)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    try:
        os.replace(tmp_path, config_path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        # EBUSY on overlayfs/bind-mount: fall back to copy-then-remove.
        try:
            shutil.copyfile(tmp_path, config_path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def write_config_from_dict(config_path: str, sections: dict, order: list) -> None:
    """
    Write config.ini from the provided sections dict, preserving existing comments.

    If *config_path* already exists, comment lines (``#`` / ``;``) and blank
    lines are kept in their original positions while key values are updated
    in-place.  Keys absent from *sections* are removed; keys that are new are
    appended at the end of their section.  Sections absent from *sections* are
    dropped.  If the file does not yet exist it is written from scratch.

    ``sections`` maps section names to dicts of key->value.
    ``order`` controls the section order; sections not listed are appended last.
    """
    write_order = list(order) + [s for s in sections if s not in order]

    if not os.path.exists(config_path):
        lines: list = []
        for section in write_order:
            if section not in sections:
                continue
            lines.append(f"[{section}]\n")
            for key, value in sections[section].items():
                lines.append(f"{key} = {value}\n")
            lines.append("\n")
        with _CONFIG_WRITE_LOCK:
            _atomic_write_lines(config_path, lines)
        return

    with open(config_path) as f:
        original_lines = f.readlines()

    # Split the original file into a preamble (lines before the first section
    # header) and a list of [section_name, raw_lines] pairs.
    pre_lines: list = []
    parsed_sections: list = []  # list of [name, [raw lines including header]]
    cur_name = None
    cur_lines: list = []

    for line in original_lines:
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            name = stripped[1 : stripped.index("]")]
            if cur_name is not None:
                parsed_sections.append([cur_name, cur_lines])
            else:
                pre_lines = cur_lines
            cur_name = name
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_name is not None:
        parsed_sections.append([cur_name, cur_lines])
    elif cur_lines:
        pre_lines = cur_lines

    orig_section_lines = {name: sec_lines for name, sec_lines in parsed_sections}

    def _update_section(orig_sec_lines: list, new_pairs: dict) -> list:
        """Return updated raw lines for one section, preserving comments."""
        result = [orig_sec_lines[0]]  # section header line
        written: set = set()
        pending: list = []  # buffered comment/blank lines preceding a key

        for line in orig_sec_lines[1:]:
            stripped = line.strip()
            if stripped == "" or stripped.startswith("#") or stripped.startswith(";"):
                pending.append(line)
            elif "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in new_pairs:
                    result.extend(pending)
                    pending = []
                    result.append(f"{key} = {new_pairs[key]}\n")
                    written.add(key)
                else:
                    # Key was deleted - discard its associated comments too
                    pending = []
            else:
                result.extend(pending)
                pending = []
                result.append(line)

        result.extend(pending)  # trailing blank/comment lines at section end

        # Append brand-new keys not present in the original section
        for key, value in new_pairs.items():
            if key not in written:
                result.append(f"{key} = {value}\n")

        return result

    output_lines = list(pre_lines)

    for section in write_order:
        if section not in sections:
            continue
        if section in orig_section_lines:
            output_lines.extend(
                _update_section(orig_section_lines[section], sections[section])
            )
        else:
            # Entirely new section
            if output_lines and output_lines[-1].strip():
                output_lines.append("\n")
            output_lines.append(f"[{section}]\n")
            for key, value in sections[section].items():
                output_lines.append(f"{key} = {value}\n")
            output_lines.append("\n")

    with _CONFIG_WRITE_LOCK:
        _atomic_write_lines(config_path, output_lines)


def config_to_json(config_path: str) -> str:
    """Return the config as a JSON string suitable for the web UI."""
    sections, order = read_config_as_dict(config_path)
    return json.dumps({"sections": sections, "order": order})
