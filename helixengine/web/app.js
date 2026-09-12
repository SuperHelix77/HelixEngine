'use strict';

const state = {
  snapshot: null,
  filter: 'all',
  paused: false,
  lastSeenAt: 0,
  streamOpen: false,
  settingsPending: false,
  timeline: new Map(),
  timelineCapped: false,
  maxTimeline: 300,
  capsuleSignature: ''
};

const $ = id => document.getElementById(id);
const hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const text = value => value == null ? '—' : String(value);
const formatInteger = value => number(value) == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
const formatDecimal = value => number(value) == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
const formatPercent = value => number(value) == null ? '—' : `${value.toFixed(1)}%`;

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = String(value);
  if (className) node.className = className;
  return node;
}

function formatBytes(value) {
  const bytes = number(value);
  if (bytes == null) return '—';
  if (bytes < 1024) return `${formatInteger(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatSeconds(value) {
  const seconds = number(value);
  if (seconds == null) return '—';
  return `${seconds < 10 ? seconds.toFixed(2) : seconds.toFixed(1)} s`;
}

function dateTime(value, fallback = '—') {
  const seconds = number(value);
  if (seconds == null) return fallback;
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString();
}

function timeOnly(value, fallback = 'time unavailable') {
  const seconds = number(value);
  if (seconds == null) return fallback;
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleTimeString();
}

function shortId(value) {
  const id = text(value);
  return id.length > 18 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id;
}

function commandText(run) {
  if (Array.isArray(run?.argv)) return run.argv.map(value => String(value)).join(' ');
  return text(run?.argv);
}

function modelName(lane) {
  const model = String(lane?.model || 'unknown').toLowerCase();
  const family = model.includes('luna') ? 'Luna' : model.includes('sol') ? 'Sol' : model.includes('astra') ? 'Astra' : text(lane?.model);
  const effort = lane?.effort === 'xhigh' ? 'XHigh' : lane?.effort ? String(lane.effort).replace(/^./, letter => letter.toUpperCase()) : '';
  return effort ? `${family} ${effort}` : family;
}

function visibleLanes() {
  const all = Array.isArray(state.snapshot?.release?.lanes) ? state.snapshot.release.lanes : [];
  return all.filter(lane => state.filter === 'all' || String(lane?.model || '').toLowerCase().includes(state.filter));
}

function safeLink(label, url) {
  const fallback = element('span', label);
  if (typeof url !== 'string' || !url) return fallback;
  try {
    const parsed = new URL(url, window.location.href);
    const sameOrigin = parsed.origin === window.location.origin;
    if (parsed.protocol !== 'https:' && !sameOrigin) return fallback;
    const link = element('a', label);
    link.href = parsed.href;
    if (!sameOrigin) {
      link.target = '_blank';
      link.rel = 'noopener';
    }
    return link;
  } catch {
    return fallback;
  }
}

function capsuleCard(lane) {
  const card = element('article', null, 'model-card');
  const title = element('div', null, 'card-title');
  const laneState = String(lane?.state || '').toUpperCase();
  const arms = Array.isArray(lane?.arms) ? lane.arms : [];
  const badge = laneState.startsWith('REJECTED') ? 'Rejected · N = 1' : arms.length ? 'N = 1 · development' : 'Pending';
  title.append(element('h3', modelName(lane)), element('span', badge, 'badge'));
  card.append(title);
  card.append(element('p', lane?.task || 'Task description unavailable', 'task'));
  card.append(element('p', lane?.policy || 'Policy text unavailable', 'policy'));

  const values = element('div', null, 'card-values');
  for (const [key, label] of [['input_tokens', 'INPUT SAVED'], ['output_tokens', 'OUTPUT SAVED'], ['uncached_input_tokens', 'UNCACHED SAVED']]) {
    const value = number(lane?.savings?.[key]);
    const cell = element('div');
    cell.append(element('strong', formatPercent(value), value == null ? '' : value < 0 ? 'negative' : 'positive'));
    cell.append(element('small', label));
    values.append(cell);
  }
  card.append(values);

  const gate = lane?.gate || lane?.comparison_gate || 'Gate not reported';
  card.append(element('p', `Gate: ${gate}`, 'gate'));
  card.append(element('p', 'Model-wide parity: unconfirmed · full release median: unavailable', 'small'));

  const regressions = Object.entries(lane?.savings || {})
    .filter(([, value]) => number(value) != null && value < 0)
    .map(([key]) => key.replaceAll('_', ' '));
  if (regressions.length) card.append(element('p', `Regression retained: ${regressions.join(', ')}`, 'regression'));

  const details = document.createElement('details');
  details.append(element('summary', 'Scope, caveats, and exact final answers'));
  const limits = document.createElement('ul');
  for (const limit of (Array.isArray(lane?.limits) ? lane.limits : [])) limits.append(element('li', limit));
  if (!limits.children.length) limits.append(element('li', 'No additional capsule limits were reported.'));
  details.append(limits);
  for (const arm of arms) {
    const label = arm?.arm === 'off' ? 'Control final ↗ ' : 'Helix final ↗ ';
    details.append(safeLink(label, arm?.final_url));
  }
  card.append(details);

  const links = element('div', null, 'receipt-links');
  if (lane?.report_url) links.append(safeLink('Paired receipt ↗', lane.report_url));
  if (lane?.review_url) links.append(safeLink('Semantic review ↗', lane.review_url));
  if (links.children.length) card.append(links);
  const hash = typeof lane?.capsule_sha256 === 'string' ? lane.capsule_sha256.slice(0, 16) : 'unavailable';
  card.append(element('p', `CAPSULE ${hash}`, 'hash'));
  return card;
}

function pricesFresh() {
  const pricing = state.snapshot?.pricing;
  const expires = number(pricing?.expires_at);
  return pricing?.fresh === true && expires != null && Date.now() / 1000 < expires;
}

function costView() {
  if (!state.snapshot) return;
  const pricing = state.snapshot.pricing || {};
  const fresh = pricesFresh();
  const checked = pricing.checked_at == null ? 'never' : dateTime(pricing.checked_at, 'unknown');
  const status = fresh
    ? `CURRENT · official tariff snapshot · checked ${checked} · refresh 2 min / expire 5 min`
    : `PRICES WITHHELD · official tariff snapshot unavailable or expired · checked ${checked}`;
  $('price-status').textContent = pricing.error ? `${status} · refresh failed` : status;
  $('price-status').classList.toggle('price-stale', !fresh);
  $('cost-table').replaceChildren();
  $('frontier-plot').replaceChildren();
  const tier = $('tariff').value;

  for (const lane of visibleLanes()) {
    const control = fresh ? number(lane?.costs?.off?.[tier]) : null;
    const helix = fresh ? number(lane?.costs?.on?.[tier]) : null;
    const saved = control != null && control > 0 && helix != null ? 100 * (1 - helix / control) : null;
    const row = document.createElement('tr');
    const values = [
      `${modelName(lane)} / ${lane?.task || 'Task unavailable'}`,
      formatPercent(lane?.savings?.input_tokens),
      formatPercent(lane?.savings?.output_tokens),
      formatPercent(lane?.savings?.uncached_input_tokens),
      control == null ? 'Unpriced' : `$${control.toFixed(4)}`,
      helix == null ? 'Unpriced' : `$${helix.toFixed(4)}`,
      formatPercent(saved)
    ];
    for (const value of values) row.append(element('td', value));
    $('cost-table').append(row);

    if (control != null && control > 0 && helix != null && helix >= 0) {
      const ratio = helix / control;
      const track = element('div', null, 'track');
      const bar = element('div', null, `bar${ratio > 1 ? ' negative' : ''}`);
      bar.style.width = `${Math.min(Math.max(ratio * 100, 0), 100)}%`;
      track.append(bar);
      const plotRow = element('div', null, 'frontier-row');
      plotRow.setAttribute('aria-label', `${modelName(lane)} ${lane?.comparison_gate || lane?.gate || 'gate not reported'} ratio ${(ratio * 100).toFixed(1)} percent of control`);
      plotRow.append(element('span', `${modelName(lane)} · ${lane?.comparison_gate || lane?.gate || 'GATE'}`), track, element('span', `${(ratio * 100).toFixed(1)}%`, 'ratio'));
      $('frontier-plot').append(plotRow);
    }
  }
  if (!$('cost-table').children.length) $('cost-table').append(emptyRow(7, 'No historical paired capsule is available in this view.'));
  if (!$('frontier-plot').children.length) $('frontier-plot').append(element('p', fresh ? 'No currently priced paired capsule in this view.' : 'Pricing is withheld until the official snapshot is fresh.', 'empty'));
}

function emptyRow(colspan, message) {
  const row = document.createElement('tr');
  const cell = element('td', message, 'empty');
  cell.colSpan = colspan;
  row.append(cell);
  return row;
}

function fallbackLabel(run) {
  if (hasOwn(run, 'fallback')) {
    if (typeof run.fallback === 'boolean') return run.fallback ? 'Used' : 'Not used';
    return text(run.fallback);
  }
  if (hasOwn(run, 'fallback_status')) return text(run.fallback_status);
  if (typeof run?.reducer_status === 'string' && run.reducer_status) return `Reducer: ${run.reducer_status}`;
  return '—';
}

function runCell(run) {
  const cell = document.createElement('td');
  cell.append(element('strong', commandText(run), 'run-command'));
  cell.append(element('small', `id ${shortId(run?.id)}`));
  if (run?.cwd != null) cell.append(element('small', `cwd ${run.cwd}`, 'run-detail'));
  if (run?.receipt != null) cell.append(element('small', `receipt ${run.receipt}`, 'run-detail'));
  return cell;
}

function renderRuns() {
  const runs = Array.isArray(state.snapshot?.runs) ? state.snapshot.runs : [];
  const tbody = $('run-list');
  tbody.replaceChildren();
  if (!runs.length) {
    tbody.append(emptyRow(7, 'No routed commands observed yet.'));
    return;
  }
  for (const run of runs) {
    const row = document.createElement('tr');
    row.append(runCell(run));
    const statusCell = document.createElement('td');
    const runState = String(run?.state || 'UNKNOWN').toUpperCase();
    statusCell.append(element('span', runState, `run-state ${runState.toLowerCase()}`));
    if (typeof run?.enabled === 'boolean') statusCell.append(element('small', run.enabled ? 'enabled at start' : 'disabled at start'));
    row.append(statusCell);
    const streams = document.createElement('td');
    streams.append(element('strong', `stdout ${formatBytes(run?.stdout_bytes)}`));
    streams.append(element('small', `stderr ${formatBytes(run?.stderr_bytes)}`));
    streams.append(element('em', 'raw stream bytes'));
    row.append(streams);
    const visible = document.createElement('td');
    visible.append(element('strong', formatBytes(run?.visible_bytes)));
    visible.append(element('small', 'reported visible bytes'));
    row.append(visible);
    row.append(element('td', formatSeconds(run?.elapsed_seconds)));
    row.append(element('td', run?.exit_code == null ? '—' : formatInteger(run.exit_code)));
    const fallback = document.createElement('td');
    fallback.append(element('strong', fallbackLabel(run)));
    if (run?.reducer_status != null && hasOwn(run, 'fallback')) fallback.append(element('small', `reducer ${run.reducer_status}`));
    row.append(fallback);
    tbody.append(row);
  }
}

function uncachedTokens(usage) {
  const input = number(usage?.input_tokens);
  const cached = number(usage?.cached_input_tokens);
  return input != null && cached != null && input >= cached ? input - cached : null;
}

function aggregate(rows, key) {
  if (!rows.length) return 0;
  let total = 0;
  for (const row of rows) {
    const value = number(row?.[key]);
    if (value == null) return null;
    total += value;
  }
  return total;
}

function aggregateUncached(rows) {
  if (!rows.length) return 0;
  let total = 0;
  for (const row of rows) {
    const value = uncachedTokens(row);
    if (value == null) return null;
    total += value;
  }
  return total;
}

function renderUsage() {
  const rows = Array.isArray(state.snapshot?.usages) ? state.snapshot.usages : [];
  $('usage-count').textContent = formatInteger(rows.length);
  const summary = $('usage-summary');
  summary.replaceChildren();
  const counters = [
    ['input_tokens', 'Imported input'],
    ['cached_input_tokens', 'Cached input'],
    ['uncached', 'Uncached input (derived)'],
    ['output_tokens', 'Output'],
    ['reasoning_output_tokens', 'Reasoning output']
  ];
  for (const [key, label] of counters) {
    const value = key === 'uncached' ? aggregateUncached(rows) : aggregate(rows, key);
    const cell = element('article', null, 'counter-cell');
    cell.append(element('strong', formatInteger(value)), element('small', label));
    summary.append(cell);
  }

  const tbody = $('usage-list');
  tbody.replaceChildren();
  if (!rows.length) {
    tbody.append(emptyRow(8, 'No native receipt has been imported.'));
    return;
  }
  for (const usage of rows) {
    const row = document.createElement('tr');
    const identity = document.createElement('td');
    identity.append(element('strong', text(usage?.model)));
    if (usage?.source_hash != null) identity.append(element('small', `receipt ${String(usage.source_hash).slice(0, 16)}`));
    row.append(identity);
    row.append(element('td', shortId(usage?.run)));
    row.append(element('td', formatInteger(usage?.input_tokens)));
    row.append(element('td', formatInteger(usage?.cached_input_tokens)));
    row.append(element('td', formatInteger(uncachedTokens(usage))));
    row.append(element('td', formatInteger(usage?.cache_write_input_tokens)));
    row.append(element('td', formatInteger(usage?.output_tokens)));
    row.append(element('td', formatInteger(usage?.reasoning_output_tokens)));
    tbody.append(row);
  }
}

function ingestEvents(events) {
  if (!Array.isArray(events)) return;
  for (const event of events) {
    if (!event || event.id == null) continue;
    const key = String(event.id);
    if (!state.timeline.has(key)) state.timeline.set(key, {
      id: event.id,
      at: event.at,
      kind: event.kind,
      run: event.run
    });
  }
  const ordered = timelineEntries();
  while (state.timeline.size > state.maxTimeline) {
    const oldest = ordered.shift();
    if (!oldest) break;
    state.timeline.delete(String(oldest.id));
    state.timelineCapped = true;
  }
}

function timelineEntries() {
  return [...state.timeline.values()].sort((left, right) => {
    const leftId = number(left.id);
    const rightId = number(right.id);
    if (leftId != null && rightId != null) return leftId - rightId;
    return (number(left.at) || 0) - (number(right.at) || 0);
  });
}

function renderTimeline() {
  const timeline = $('timeline');
  timeline.replaceChildren();
  const entries = timelineEntries();
  if (state.timelineCapped) timeline.append(element('li', 'Earlier session events are outside this bounded view.', 'timeline-note'));
  if (!entries.length) {
    timeline.append(element('li', 'No routed command events observed yet.', 'empty'));
    return;
  }
  for (const event of entries) {
    const item = document.createElement('li');
    item.append(element('time', timeOnly(event.at)));
    item.append(element('strong', text(event.kind || 'EVENT')));
    if (event.run != null) item.append(element('span', `run ${shortId(event.run)}`));
    timeline.append(item);
  }
}

function storageInfo() {
  const storage = state.snapshot?.storage || {};
  const bytes = number(storage.bytes);
  const objects = number(storage.objects);
  if (bytes != null || objects != null) {
    return {
      state: 'KNOWN',
      detail: bytes != null ? `${formatBytes(bytes)} reported` : `${formatInteger(objects)} objects reported`,
      bytes: bytes == null ? 'Unknown' : formatBytes(bytes),
      objects: objects == null ? 'Unknown' : formatInteger(objects)
    };
  }
  return { state: 'UNKNOWN', detail: 'Physical storage not reported', bytes: 'Unknown', objects: 'Unknown' };
}

function renderRuntime() {
  const runs = Array.isArray(state.snapshot?.runs) ? state.snapshot.runs : [];
  const active = runs.filter(run => ['STARTING', 'RUNNING'].includes(String(run?.state || '').toUpperCase())).length;
  $('active-runs').textContent = formatInteger(active);
  $('total-runs').textContent = number(state.snapshot?.total_runs) == null ? '—' : formatInteger(state.snapshot.total_runs);
  $('run-limit').textContent = number(state.snapshot?.run_view_limit) == null ? 'Snapshot limit unavailable' : `view limit ${formatInteger(state.snapshot.run_view_limit)}`;
  const storage = storageInfo();
  $('storage-state').textContent = storage.state;
  $('storage-detail').textContent = storage.detail;

  const details = $('runtime-details');
  details.replaceChildren();
  const settings = state.snapshot?.settings || {};
  const values = [
    ['Application version', state.snapshot?.app_version],
    ['Settings revision', number(settings.revision) == null ? '—' : formatInteger(settings.revision)],
    ['Storage bytes', storage.bytes],
    ['Storage objects', storage.objects],
    ['Last snapshot', dateTime(state.snapshot?.observed_at, 'Unknown')]
  ];
  for (const [label, value] of values) {
    const line = document.createElement('div');
    line.append(element('dt', label), element('dd', value));
    details.append(line);
  }
  renderRuns();
  renderUsage();
  renderTimeline();
}

function updateMeta() {
  if (!state.snapshot) return;
  $('version').textContent = text(state.snapshot.app_version);
  const observed = state.snapshot.observed_at == null ? 'Awaiting timestamp' : `Observed ${dateTime(state.snapshot.observed_at)}`;
  $('updated').textContent = observed;
}

function syncEngineSwitch() {
  const input = $('engine-switch');
  const stateLabel = $('engine-switch-state');
  const settings = state.snapshot?.settings;
  const ready = typeof settings?.enabled === 'boolean' && number(settings?.revision) != null && typeof state.snapshot?.csrf_token === 'string';
  input.disabled = !ready || state.settingsPending;
  if (!state.settingsPending && ready) input.checked = settings.enabled;
  stateLabel.textContent = state.settingsPending ? 'Saving setting…' : !ready ? 'Waiting for state' : settings.enabled ? 'ON · new commands' : 'OFF · exact native streams';
  $('engine-status').textContent = state.settingsPending ? 'Saving the revisioned setting…' : !ready ? 'Waiting for a valid local state snapshot.' : `Revision ${formatInteger(settings.revision)} · ${settings.enabled ? 'new routed commands may reduce output' : 'new routed commands preserve native output'}`;
}

async function changeEngine(enabled) {
  const snapshot = state.snapshot;
  const settings = snapshot?.settings;
  const token = snapshot?.csrf_token;
  if (!snapshot || typeof token !== 'string' || typeof settings?.enabled !== 'boolean' || number(settings?.revision) == null) {
    syncEngineSwitch();
    return;
  }
  const revision = settings.revision;
  state.settingsPending = true;
  syncEngineSwitch();
  try {
    const response = await fetch('/api/settings', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Helix-CSRF': token
      },
      body: JSON.stringify({ enabled: Boolean(enabled), revision })
    });
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (!response.ok) {
      const detail = payload?.error || payload?.detail || `HTTP ${response.status}`;
      const error = new Error(String(detail));
      error.status = response.status;
      throw error;
    }
    const returned = payload?.settings && typeof payload.settings === 'object' ? payload.settings : payload;
    const returnedRevision = number(returned?.revision);
    if (typeof returned?.enabled === 'boolean' && returnedRevision != null) {
      const currentRevision = number(state.snapshot?.settings?.revision);
      if (currentRevision == null || returnedRevision >= currentRevision) {
        state.snapshot = { ...state.snapshot, settings: { enabled: returned.enabled, revision: returnedRevision } };
      }
    }
    $('engine-status').textContent = `Saved · revision ${formatInteger(state.snapshot?.settings?.revision)} · applies to new routed commands`;
  } catch (error) {
    const message = error?.status === 409 ? 'Setting changed elsewhere; live state will reconcile this view.' : `Setting was not saved: ${error?.message || 'request failed'}`;
    $('engine-status').textContent = message;
  } finally {
    state.settingsPending = false;
    syncEngineSwitch();
    updateConnection();
    if (!state.paused) renderRuntime();
  }
}

function updateConnection() {
  const node = $('connection');
  node.classList.remove('is-live', 'is-stale', 'is-connecting', 'is-paused');
  if (!state.snapshot) {
    node.textContent = 'CONNECTING';
    node.classList.add('is-connecting');
    return;
  }
  const stale = !state.lastSeenAt || Date.now() - state.lastSeenAt > 12000;
  if (stale) {
    node.textContent = 'STALE · RECONNECTING';
    node.classList.add('is-stale');
  } else if (state.paused) {
    node.textContent = 'LIVE · VIEW PAUSED';
    node.classList.add('is-paused');
  } else if (state.streamOpen) {
    node.textContent = 'LIVE · SSE ~1 S';
    node.classList.add('is-live');
  } else {
    node.textContent = 'LIVE · STREAM RECONNECTING';
    node.classList.add('is-live');
  }
}

function renderChat() {
  const research = state.snapshot?.hub_mode === 'research';
  $('chat-research').hidden = !research;
  if (!research) return;
  document.title = 'Helix Engine · Research HUD';
  $('hero-title').textContent = 'Research, with receipts.';
  const chat = state.snapshot.chat_observer;
  if (!chat) { $('chat-health').textContent = 'No chat attached. Release service remains separate.'; return; }
  $('chat-health').textContent = `${chat.connected ? 'ATTACHED' : 'ATTENTION'} · ${text(chat.thread_id)} · ${chat.worker_error || chat.error || 'read-only'} · scan ${dateTime(chat.last_scan, 'pending')}`;
  const usage = chat.usage || {};
  const facts = [
    ['Current model / effort', `${text(chat.model)} / ${text(chat.effort)}`],
    ['Native responses since attachment', formatInteger(chat.response_count)],
    ['Input tokens', formatInteger(usage.input_tokens)],
    ['Cached input tokens', formatInteger(usage.cached_input_tokens)],
    ['Output tokens (includes reasoning)', formatInteger(usage.output_tokens)],
    ['Reasoning subset', formatInteger(usage.reasoning_output_tokens)],
    ['Observer bytes read', formatInteger(chat.bytes_read)],
    ['Receipt coverage since attachment', chat.coverage_complete === true ? 'Complete for supported records' : 'INCOMPLETE — inspect observer error'],
    ['Savings / capability parity', 'UNMEASURED for this chat']
  ];
  $('chat-metrics').replaceChildren(...facts.map(([label, value]) => {
    const row = element('p'); row.append(element('span', `${label}: `), element('strong', value)); return row;
  }));
  $('chat-recent').replaceChildren(...(chat.recent || []).map(record => {
    const tr = element('tr');
    for (const value of [record.timestamp, record.model, formatInteger(record.usage?.input_tokens), formatInteger(record.usage?.cached_input_tokens), formatInteger(record.usage?.output_tokens)]) tr.append(element('td', value));
    return tr;
  }));
}

function render() {
  if (!state.snapshot) return;
  updateMeta();
  syncEngineSwitch();
  if (state.paused) return;
  const signature = `${state.filter}|${JSON.stringify(state.snapshot.release || {})}`;
  if (signature !== state.capsuleSignature) {
    const cards = visibleLanes().map(capsuleCard);
    $('model-cards').replaceChildren(...(cards.length ? cards : [element('p', 'No historical paired capsule is available in this view.', 'empty')]));
    state.capsuleSignature = signature;
  }
  costView();
  renderRuntime();
  renderChat();
}

function accept(next) {
  if (!next || typeof next !== 'object') throw new Error('Invalid snapshot');
  state.snapshot = next;
  state.lastSeenAt = Date.now();
  ingestEvents(next.events);
  updateMeta();
  syncEngineSwitch();
  render();
  updateConnection();
}

function operationalRun(run) {
  const result = {};
  for (const key of ['id', 'argv', 'cwd', 'state', 'enabled', 'settings_revision', 'started', 'stdout_bytes', 'stderr_bytes', 'visible_bytes', 'elapsed_seconds', 'exit_code', 'receipt', 'reducer_status', 'fallback', 'fallback_status']) {
    if (!hasOwn(run, key)) continue;
    result[key] = key === 'argv' && Array.isArray(run.argv) ? run.argv.slice() : run[key];
  }
  return result;
}

function operationalEvent(event) {
  return { id: event?.id, at: event?.at, kind: event?.kind, run: event?.run };
}

function operationalUsage(usage) {
  const result = {};
  for (const key of ['run', 'source_hash', 'model', 'input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens']) {
    if (hasOwn(usage, key)) result[key] = usage[key];
  }
  return result;
}

function exportOperationalSnapshot() {
  if (!state.snapshot) {
    $('export-status').textContent = 'No local snapshot is available to export.';
    return;
  }
  const snapshot = state.snapshot;
  const storage = snapshot.storage || {};
  const data = {
    schema: 'helix.operational-export.v1',
    export_scope: 'operational telemetry only',
    exported_at: Date.now() / 1000,
    observed_at: snapshot.observed_at,
    app_version: snapshot.app_version,
    settings: {
      enabled: snapshot.settings?.enabled,
      revision: snapshot.settings?.revision
    },
    runs: (Array.isArray(snapshot.runs) ? snapshot.runs : []).map(operationalRun),
    events: timelineEntries().map(operationalEvent),
    usages: (Array.isArray(snapshot.usages) ? snapshot.usages : []).map(operationalUsage),
    total_runs: snapshot.total_runs,
    run_view_limit: snapshot.run_view_limit,
    storage: { bytes: storage.bytes ?? null, objects: storage.objects ?? null }
  };
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = element('a');
  link.href = url;
  link.download = 'helix-operational-snapshot.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $('export-status').textContent = 'Operational snapshot downloaded · per-server CSRF token omitted.';
}

for (const button of document.querySelectorAll('[data-model]')) {
  button.addEventListener('click', () => {
    state.filter = button.dataset.model || 'all';
    for (const sibling of document.querySelectorAll('[data-model]')) sibling.setAttribute('aria-pressed', String(sibling === button));
    state.capsuleSignature = '';
    render();
  });
}

$('tariff').addEventListener('change', costView);
$('pause').addEventListener('click', () => {
  state.paused = !state.paused;
  $('pause').textContent = state.paused ? 'Resume view' : 'Pause view';
  $('pause').setAttribute('aria-pressed', String(state.paused));
  if (!state.paused) render();
  updateConnection();
});
$('engine-switch').addEventListener('change', event => changeEngine(event.target.checked));
$('export-button').addEventListener('click', exportOperationalSnapshot);

const stream = new EventSource('/api/release-events');
stream.onopen = () => {
  state.streamOpen = true;
  updateConnection();
};
stream.onmessage = event => {
  try {
    accept(JSON.parse(event.data));
  } catch {
    $('connection').textContent = 'INVALID TELEMETRY';
    $('connection').classList.add('is-stale');
  }
};
stream.onerror = () => {
  state.streamOpen = false;
  updateConnection();
};

fetch('/api/release-state', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
  .then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(accept)
  .catch(error => {
    if (!state.snapshot) {
      $('connection').textContent = `CONNECTING · ${error.message}`;
      $('connection').classList.add('is-connecting');
    }
  });

setInterval(() => {
  updateConnection();
  if (state.snapshot && !state.paused) costView();
}, 1000);

window.addEventListener('beforeunload', () => stream.close());
