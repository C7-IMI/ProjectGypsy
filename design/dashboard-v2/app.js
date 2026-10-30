(function () {
  'use strict';
  var tokenMeta = document.querySelector('meta[name="gypsy-token"]');
  var token = tokenMeta ? tokenMeta.getAttribute('content') : '';
  var shell = document.getElementById('shell');
  var state = null;
  var view = 'overview';
  var selectedRunId = null;
  var detail = null;
  var selectedArtifact = null;
  var artifactMeta = null;
  var pendingAction = null;
  var pollTimer = null;
  var toastTimer = null;
  var searchQuery = '';
  var jobStream = null;
  var jobTransport = null;
  var jobFinished = false;
  var RUN_ALL = 'python workstream/gypsy.py slices run --all';
  var ENGINE_LABELS = { godot: 'Godot', unity: 'Unity', ue5: 'Unreal Engine 5', flax: 'Flax' };

  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function bytes(n) {
    if (n === null || n === undefined) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }
  function secs(n) { return n === null || n === undefined ? '—' : (Math.round(Number(n) * 10) / 10) + 's'; }
  function pct(n) { return n === null || n === undefined ? '—' : Math.round(Number(n) * 100) + '%'; }
  function shortTime(value) {
    if (!value) return '—';
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value).slice(0, 16);
    return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function badge(status, label) {
    var s = String(status || 'ready').toLowerCase();
    var cls = 'n';
    if (s === 'pass' || s === 'passed' || s === 'done' || s === 'ok') cls = 'p';
    else if (s === 'blocked' || s === 'failed' || s === 'fail') cls = 'b';
    else if (s === 'untested') cls = 'u';
    return '<span class="badge ' + cls + '">' + esc(label || s.toUpperCase()) + '</span>';
  }
  function dot(status) {
    var s = String(status || 'ready').toLowerCase();
    var color = 'var(--dim)';
    if (s === 'pass' || s === 'passed' || s === 'done') color = 'var(--green)';
    else if (s === 'blocked' || s === 'failed' || s === 'fail') color = 'var(--red)';
    else if (s === 'untested') color = 'var(--amber)';
    return '<span class="dot" style="background:' + color + '"></span>';
  }
  function statusText(status) {
    var s = String(status || '').toLowerCase();
    if (s === 'passed' || s === 'pass') return 'PASS';
    if (s === 'failed' || s === 'fail') return 'FAIL';
    if (s === 'blocked') return 'BLOCKED';
    if (s === 'untested') return 'UNTESTED';
    return (s || 'READY').toUpperCase();
  }
  function engineLabel(id) {
    if (!id) return 'engine';
    return ENGINE_LABELS[id] || String(id).charAt(0).toUpperCase() + String(id).slice(1);
  }
  function commandFor(id) {
    if (!state || !state.commands) return '';
    for (var i = 0; i < state.commands.length; i++) {
      if (state.commands[i].id === id) return (state.commands[i].argv || []).join(' ');
    }
    return '';
  }
  function prettyCommand(id) {
    return commandFor(id).replace(/^.*?python(?:\.exe)?\s+/i, 'python ');
  }
  function actionAvailable(id) {
    if (!id || !state || !state.commands) return false;
    for (var i = 0; i < state.commands.length; i++) if (state.commands[i].id === id) return true;
    return false;
  }
  function runButton(id, label, primary) {
    if (!actionAvailable(id)) return '';
    return '<button class="btn small ' + (primary ? 'primary' : 'ghost') + '" data-run="' + esc(id) + '" title="' + esc(commandFor(id)) + '">' + esc(label) + '</button>';
  }
  function copyButton(text, label) {
    if (!text) return '';
    return '<button class="btn small ghost" data-copy="' + esc(text) + '">' + esc(label || 'Copy command') + '</button>';
  }
  function viewLink(target, label) {
    return '<a class="btn small ghost" href="' + esc(target) + '">' + esc(label || 'Open') + '</a>';
  }
  function insight() { return (state && state.insights) || {}; }
  function nextActions() { return insight().nextActions || []; }
  function kv(key, value) {
    return '<div class="kv"><div class="k">' + esc(key) + '</div><div class="v">' + esc(value) + '</div></div>';
  }
  function stat(label, value) {
    return '<div class="stat"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
  }
  function emptyState(title, body, actions) {
    return '<div class="empty" role="status"><b>' + esc(title) + '</b><p>' + esc(body) + '</p><div class="empty-actions">' + (actions || '') + '</div></div>';
  }
  function runAllActions() {
    return runButton('run_all', 'Run all gates', true) + ' ' + copyButton(RUN_ALL, 'Copy command');
  }
  function defaultArtifact() {
    var list = detail && detail.artifacts && detail.artifacts.length ? detail.artifacts : (state && state.artifacts) || [];
    if (!list.length) return null;
    for (var i = 0; i < list.length; i++) {
      if (list[i].path && list[i].path.indexOf('frame.png') >= 0) return list[i].path;
    }
    return list[0].path || null;
  }
  function selectedArtifactEntry() {
    var list = detail && detail.artifacts && detail.artifacts.length ? detail.artifacts : (state && state.artifacts) || [];
    for (var i = 0; i < list.length; i++) if (list[i].path === selectedArtifact) return list[i];
    return null;
  }
  function previewUrl(path) {
    return '/api/artifact?raw=1&path=' + encodeURIComponent(path);
  }
  function artifactPanel(compact) {
    var entry = selectedArtifactEntry() || (state && state.artifacts && state.artifacts[0]);
    if (!entry) return emptyState('No artifact selected', 'Pick an artifact from the artifacts view or a run to inspect its hash and preview.');
    var isImage = /\.(png|jpe?g|webp)$/i.test(entry.path || '');
    var meta = artifactMeta && artifactMeta.path === entry.path ? artifactMeta : entry;
    var hash = meta.sha256 || entry.sha256 || '';
    var image = isImage ? '<img src="' + esc(previewUrl(entry.path)) + '" alt="Preview of ' + esc(entry.path.split('/').pop()) + '">' : '<span class="cap">' + esc(meta.kind || 'file') + '</span>';
    return '<div class="art" style="height:' + (compact ? '112' : '132') + 'px">' + image + '</div>' +
      kv('path', entry.path) + kv('size', bytes(entry.bytes)) +
      '<div class="kv"><div class="k">sha256</div><div class="v" title="' + esc(hash) + '">' + esc((hash || '—').slice(0, 12)) + '…' + esc((hash || '').slice(-6)) + '</div></div>' +
      kv('kind', entry.kind || 'file') +
      '<div class="artfoot"><button class="btn small ghost" data-artifact="' + esc(entry.path) + '">Refresh</button>' + copyButton(hash, 'Copy hash') + '</div>';
  }
  function gatesMarkup() {
    var gates = state.gates || [];
    var passing = gates.filter(function (g) { return g.status === 'pass'; });
    var attention = gates.filter(function (g) { return g.status === 'untested' || g.status === 'ready'; });
    var blocked = gates.filter(function (g) { return g.status === 'blocked'; });
    function group(title, list) {
      if (!list.length) return '';
      return '<div class="gsep">' + esc(title) + '</div><div class="gates">' + list.map(function (g) {
        return '<div class="gate ' + (g.status === 'untested' || g.status === 'blocked' ? 'clickable' : '') + '"><span class="d" style="background:' + (g.status === 'pass' ? 'var(--green)' : g.status === 'blocked' ? 'var(--red)' : 'var(--amber)') + '"></span><div class="g"><b>' + esc(g.label) + '</b><p>' + esc(g.detail) + '</p></div>' + badge(g.status) + '</div>';
      }).join('') + '</div>';
    }
    return group('Passing', passing) + group('Needs attention', attention) + group('Blocked', blocked) +
      '<div class="note">No approval queue. Gates are automated; evidence is the review surface.</div>';
  }
  function railMarkup(active) {
    function nav(viewId, label, count) {
      return '<button class="nav' + (active === viewId ? ' active' : '') + '" data-view="' + viewId + '"' + (active === viewId ? ' aria-current="page"' : '') + '><span class="i"></span>' + label + (count !== null && count !== undefined ? '<span class="count">' + esc(count) + '</span>' : '') + '</button>';
    }
    var gatesAttention = ((state.metrics && state.metrics.blocked) || 0) + ((state.metrics && state.metrics.untested) || 0);
    return '<aside class="rail" aria-label="Sections">' +
      '<div class="label">Workspace</div>' + nav('overview', 'Overview') + nav('insights', 'Insights', (nextActions().length || null)) + nav('slices', 'Slices', (state.slices || []).length) + nav('artifacts', 'Artifacts', (state.artifacts || []).length) + nav('run', 'Runs', (state.runs || []).length) +
      '<div class="label">Console</div>' + nav('mission', 'Mission', state.metrics.untested || 0) + nav('commands', 'Commands') + nav('review', 'Review', state.metrics.blocked || 0) +
      '<div class="label">Quality</div><button class="nav" data-view="review"><span class="i"></span>Gates<span class="count">' + gatesAttention + '</span></button>' +
      '<a class="nav" href="/classic" style="text-decoration:none"><span class="i"></span>Classic views</a>' +
      '<div class="spacer"></div><div class="palette"><div class="k"><span>COMMAND PALETTE</span><span>⌘ K</span></div><div class="v">slices run --all</div></div>' +
      '<div class="note">The CLI is the source of truth. Every UI action is a named command.</div></aside>';
  }
  function actionRow(a) {
    var buttons = '';
    if (a.action && actionAvailable(a.action)) {
      buttons += runButton(a.action, a.action === 'run_all' ? 'Run all gates' : 'Run ' + a.action, a.tone === 'bad' || a.tone === 'warn');
    }
    if (a.command) buttons += copyButton(a.command, 'Copy command');
    if (a.view) buttons += viewLink(a.view, 'Open view');
    if (!a.action) buttons += '<span class="tag ' + (a.tone === 'bad' ? 'bad' : '') + '">No local action</span>';
    return '<div class="actionrow tone-' + esc(a.tone || 'info') + '"><div class="abody"><b>' + esc(a.title) + '</b><p>' + esc(a.why || '') + '</p>' + (a.command ? '<code>' + esc(a.command) + '</code>' : '') + '</div><div class="abtns">' + buttons + '</div></div>';
  }
  function nextActionMarkup() {
    var actions = nextActions();
    if (!actions.length) return '';
    var a = actions[0];
    var buttons = '';
    if (a.action && actionAvailable(a.action)) buttons += runButton(a.action, a.action === 'run_all' ? 'Run all gates' : 'Run ' + a.action, true);
    if (a.command) buttons += copyButton(a.command);
    if (a.view) buttons += viewLink(a.view, 'Open view');
    if (!a.action) buttons += '<span class="tag">No local action</span>';
    return '<div class="next tone-' + esc(a.tone || 'info') + '"><div class="icon" aria-hidden="true">!</div><div class="txt"><div class="eyebrow">Next best action</div><h3>' + esc(a.title) + '</h3><p>' + esc(a.why || '') + '</p></div><div class="actions">' + buttons + '</div></div>';
  }
  function metricCard(label, value, sub, badgeText, tone) {
    return '<div class="metric"><div class="top"><span>' + esc(label) + '</span><span class="status ' + esc(tone || 'pass') + '">' + esc(badgeText || '') + '</span></div><div class="v">' + esc(value) + '</div><div class="s">' + esc(sub) + '</div></div>';
  }
  function stageMarkup(item) {
    var status = item.passed ? 'passed' : 'failed';
    var stepText = item.steps && typeof item.steps === 'object' ? (item.steps.passed + '/' + item.steps.total + ' steps') : (typeof item.steps === 'number' ? item.steps + ' steps' : '— steps');
    return '<div class="stage clickable" data-run-id="' + esc(item.statePath || '') + '" data-stage-id="' + esc(item.id) + '"><div class="r">' + dot(status) + '<span class="n">' + esc(item.id) + '</span><span class="time">' + esc(secs(item.seconds)) + '</span></div><div class="sub">' + esc((item.detail || []).join(' → ') || 'slice') + '</div><div class="bar"><i></i></div><div class="foot"><span>' + esc(stepText) + '</span><span>' + esc(item.artifacts || 0) + ' artifacts</span></div></div>';
  }
  function runRow(run) {
    return '<tr data-run-id="' + esc(run.id) + '"><td class="runname">' + esc(String(run.title || '').slice(0, 22)) + '</td><td>' + esc(run.kind === 'toolpack' ? 'toolpack' : 'all gates') + '</td><td><span class="status ' + (run.passed ? 'pass' : 'fail') + '">● ' + statusText(run.status) + '</span></td><td class="t-mono">' + esc(secs(run.durationSeconds)) + '</td><td class="t-mono">' + esc(shortTime(run.startedAt)) + '</td><td class="t-mono">' + esc(run.artifactCount || 0) + '</td><td class="rowactions">Open →</td></tr>';
  }
  function readinessChecklist() {
    var gates = state.gates || [];
    if (!gates.length) return emptyState('No gates recorded', 'Gate state is computed from local evidence; run the checks to populate it.', runAllActions());
    return '<div class="checklist">' + gates.map(function (g) {
      var cls = g.status === 'pass' ? '' : g.status === 'blocked' ? ' red' : ' amber';
      return '<div class="check"><span class="d' + cls + '"></span><span class="k">' + esc(g.label) + '</span><span class="v">' + statusText(g.status) + '</span><span class="chk-d">' + esc(g.detail) + '</span></div>';
    }).join('') + '</div>';
  }
  function renderOverview() {
    shell.className = 'body';
    var s = state;
    var last = insight().lastRun || {};
    var pipeline = (s.slices || []).map(stageMarkup).join('');
    var runs = (s.runs || []).filter(function (r) { return !searchQuery || ((r.title || '') + ' ' + (r.kind || '')).toLowerCase().indexOf(searchQuery.toLowerCase()) >= 0; }).slice(0, 6);
    var rows = runs.map(runRow).join('');
    if (!rows) rows = '<tr><td colspan="7">' + emptyState('No runs recorded yet', 'Run all gates once; this table fills from task and toolpack state.', runAllActions()) + '</td></tr>';
    var artifactCards = (s.artifacts || []).slice(0, 4).map(function (a) {
      var isImage = /\.(png|jpe?g|webp)$/i.test(a.path || '');
      return '<div class="ev clickable" data-artifact="' + esc(a.path) + '"><div class="thumb">' + (isImage ? '<img src="' + esc(previewUrl(a.path)) + '" alt="' + esc(a.path.split('/').pop()) + '">' : esc(a.kind || 'file')) + '</div><div class="n">' + esc(a.path.split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + '</div></div>';
    }).join('');
    if (!artifactCards) artifactCards = emptyState('No artifacts yet', 'Artifacts appear after a run that declares them. Hashes and previews are read-only.', runAllActions());
    var lastText = last.available ? (last.passed ? 'last run passed' : 'last run failed') : 'no run yet';
    shell.innerHTML = railMarkup('overview') +
      '<main class="main"><div class="head"><div><h1>Workspace overview</h1><p>' + esc(s.metrics.slicesTotal) + ' slices · ' + esc(lastText) + ' · ' + esc((s.metrics.blocked || 0) + (s.metrics.untested || 0)) + ' gates need attention</p></div><div class="actions"><button class="btn ghost" data-view="insights">Open insights</button>' + runButton('run_all', 'Run all', true) + '</div></div>' +
      nextActionMarkup() +
      '<div class="metrics">' + metricCard('Slices passed', (s.metrics.slicesPassed || 0) + ' / ' + (s.metrics.slicesTotal || 0), 'latest task', s.metrics.slicesTotal ? '● RECORDED' : 'NO RUN') + metricCard('Tests', s.metrics.tests === null || s.metrics.tests === undefined ? '—' : s.metrics.tests, 'workstream suite', s.metrics.tests ? '● RECORDED' : 'NOT RUN') + metricCard('Capabilities', s.metrics.capabilities || '—', 'manifests valid', '') + metricCard('Blocking gates', (s.metrics.blocked || 0), (s.metrics.untested || 0) + ' untested · not hidden', (s.metrics.blocked || 0) ? 'BLOCKED' : 'NONE', (s.metrics.blocked || 0) ? 'fail' : 'pass') + '</div>' +
      '<div class="section" id="overview-pipeline"><div class="section-h"><h2>Pipeline</h2><span class="sub">left to right · click a stage to inspect</span><span class="right">' + ((s.slices || []).length ? ((s.slices || []).every(function (x) { return x.passed; }) ? 'All declared slices passed' : 'Some slices need attention') : 'No slices recorded') + '</span></div>' + (pipeline ? '<div class="pipeline">' + pipeline + '</div>' : emptyState('No slice state yet', 'Slice rows come from the latest task or per-slice state written by the orchestrator.', runAllActions())) + '</div>' +
      '<div class="runs"><div class="runs-h"><b>Recent runs</b><span>last ' + runs.length + '</span></div><table class="run-table"><thead><tr><th>Run</th><th>Scope</th><th>Status</th><th>Duration</th><th>Started</th><th>Artifacts</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<div class="bottomgrid" id="overview-artifacts"><div class="runs"><div class="runs-h"><b>Recent artifacts</b><span>hashed · local</span></div><div class="evidence-grid">' + artifactCards + '</div></div>' +
      '<div class="runs"><div class="runs-h"><b>Readiness checklist</b><span>' + ((s.gates || []).length) + ' gates</span></div>' + readinessChecklist() + '</div></div>' +
      '</main><aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Selected artifact</b><span class="right">LIVE HASH</span></div><div class="rpad">' + artifactPanel() + '</div></div><div class="rpanel"><div class="rpanel-h"><b>Gates</b><span class="right">HONEST STATE</span></div><div class="rpad">' + gatesMarkup() + '</div></div></aside>';
  }
  function insightCard(title, meta, body, wide) {
    return '<section class="icard' + (wide ? ' wide' : '') + '"><div class="icard-h"><b>' + esc(title) + '</b><span>' + esc(meta || '') + '</span></div><div class="icard-b">' + body + '</div></section>';
  }
  function engineCard() {
    var e = insight().engine || {};
    var current = e.current || {};
    var second = e.second || {};
    var def = e.default || {};
    var detected = e.detected || {};
    var rows = '';
    rows += kv('Current checkout', current.name ? current.name + ' · ' + engineLabel(current.engine) + ' ' + (current.version || '?') + ' (' + (current.adapter || '?') + ')' : 'No project manifest found');
    rows += kv('Second-engine proof', second.name ? second.name + ' · ' + engineLabel(second.engine) + ' ' + (second.version || '?') : 'No second-engine manifest found');
    rows += kv('Default for new projects', engineLabel(def.engine) + ' ' + (def.version || '?') + (def.detectedMatch === true ? ' · installed version matches' : def.detectedMatch === false ? ' · installed version differs' : ''));
    var detectedText = Object.keys(detected).map(function (key) {
      var item = detected[key] || {};
      return engineLabel(key) + ' ' + (item.version || '?') + (item.usable ? ' usable' : item.installed ? ' not usable' : ' not installed');
    }).join(' · ');
    rows += kv('Detected locally', detectedText || 'No probe state; run engines probe');
    var facts = (e.facts || []).map(function (fact) { return '<li>' + esc(fact) + '</li>'; }).join('');
    return rows + '<ul class="facts">' + facts + '</ul><div class="src">source: ' + esc(e.source || 'manifests + ADR-018') + '</div>';
  }
  function lastRunCard() {
    var l = insight().lastRun || {};
    if (!l.available) {
      return emptyState('No run recorded yet', l.emptyReason || 'Run all gates once; this card then explains the last run from task state.', runAllActions());
    }
    var actions = '';
    if (l.runId) actions += '<button class="btn small" data-run-id="' + esc(l.runId) + '">Open run</button>';
    actions += copyButton(l.command || RUN_ALL, 'Copy command');
    var failed = (l.failedSlices || []).length ? '<p class="warnline">Failed slices: ' + esc(l.failedSlices.join(', ')) + '</p>' : '';
    return '<div class="inlinerow"><span class="status ' + (l.passed ? 'pass' : 'fail') + '">● ' + statusText(l.status) + '</span><span class="t-mono">' + esc(secs(l.durationSeconds)) + '</span><span>' + esc(l.steps.passed) + '/' + esc(l.steps.total) + ' steps</span><span>' + esc(l.artifacts) + ' artifacts</span></div>' +
      '<p class="lead">' + esc(l.summary) + '</p>' + failed +
      '<div class="cardactions">' + actions + '</div>';
  }
  function qualityCard() {
    var q = insight().quality || {};
    var attention = q.attention || {};
    var blocked = q.blocked || {};
    var cells = stat('Passing', q.passing || 0) + stat('Attention', attention.count || 0) + stat('Blocked', blocked.count || 0) + stat('Tests', q.tests === null || q.tests === undefined ? '—' : q.tests);
    var names = '';
    if ((attention.names || []).length) names += 'Attention: ' + attention.names.join(', ') + '. ';
    if ((blocked.names || []).length) names += 'Blocked: ' + blocked.names.join(', ') + '.';
    return '<div class="stats4">' + cells + '</div><p class="lead">' + esc(q.summary || '') + '</p>' + (names ? '<p class="src">' + esc(names) + '</p>' : '') + '<div class="src">source: ' + esc(q.source || 'workstream state') + '</div>';
  }
  function cacheCard() {
    var c = insight().cache || {};
    if (!c.available) {
      var looked = (c.lookedFor || []).map(function (p) { return '<code>' + esc(p) + '</code>'; }).join(', ');
      return emptyState('No execution-cache stats yet', c.emptyReason || 'The action cache is opt-in and no hit/miss state is recorded here.', copyButton(RUN_ALL, 'Copy run command')) +
        (looked ? '<div class="looked">Looked for: ' + looked + '</div>' : '');
    }
    var cells = '';
    if (c.hits !== null && c.hits !== undefined) cells += stat('Hits', c.hits);
    if (c.misses !== null && c.misses !== undefined) cells += stat('Misses', c.misses);
    if (c.hitRate !== null && c.hitRate !== undefined) cells += stat('Hit rate', pct(c.hitRate));
    if (c.entries !== null && c.entries !== undefined) cells += stat('Entries', c.entries);
    if (c.savedSeconds !== null && c.savedSeconds !== undefined) cells += stat('Saved', secs(c.savedSeconds));
    return '<div class="stats4">' + cells + '</div><p class="lead">' + esc(c.summary) + '</p><div class="src">source: ' + esc(c.source || 'state') + '</div>';
  }
  function schedulerCard() {
    var s = insight().scheduler || {};
    if (!s.available) {
      var looked = (s.lookedFor || []).map(function (p) { return '<code>' + esc(p) + '</code>'; }).join(', ');
      return emptyState('No parallel-scheduler state yet', s.emptyReason || 'Parallel execution is opt-in and no scheduler state is recorded here.', copyButton(RUN_ALL, 'Copy run command')) +
        (looked ? '<div class="looked">Looked for: ' + looked + '</div>' : '');
    }
    var cells = '';
    if (s.mode) cells += stat('Mode', s.mode);
    if (s.workers !== null && s.workers !== undefined) cells += stat('Workers', s.workers);
    if (s.queueSeconds !== null && s.queueSeconds !== undefined) cells += stat('Queued', secs(s.queueSeconds));
    if (s.cancelled !== null && s.cancelled !== undefined) cells += stat('Cancelled', s.cancelled);
    return '<div class="stats4">' + cells + '</div><p class="lead">' + esc(s.summary) + '</p><div class="src">source: ' + esc(s.source || 'state') + '</div>';
  }
  function renderInsights() {
    shell.className = 'body';
    var ins = insight();
    var summaryList = (ins.summary || []).map(function (line) { return '<li>' + esc(line) + '</li>'; }).join('');
    var actions = (ins.nextActions || []).map(actionRow).join('');
    shell.innerHTML = railMarkup('insights') +
      '<main class="main"><div class="head"><div><h1>Insights</h1><p>Plain language over the same state the CLI writes — no second evidence model</p></div><div class="actions"><button class="btn ghost" data-view="overview">← Overview</button>' + runButton('run_all', 'Run all gates', true) + '</div></div>' +
      '<div class="insights">' +
      insightCard('What this screen is telling you', 'STATE-DERIVED', summaryList ? '<ul class="summary-list">' + summaryList + '</ul>' : emptyState('No summary yet', 'Run the gates; insights explain recorded state, never guessed state.', runAllActions()), true) +
      insightCard('Engine default', 'MANIFESTS + ADR-018', engineCard()) +
      insightCard('Last run health', 'LATEST TASK OR TOOLPACK', lastRunCard()) +
      insightCard('Quality and gates', 'AUTOMATED EVIDENCE', qualityCard()) +
      insightCard('Execution cache', 'OPT-IN', cacheCard()) +
      insightCard('Parallel scheduler', 'OPT-IN', schedulerCard()) +
      insightCard('Next actions', 'ACTIONABLE', actions || emptyState('No actions', 'Nothing needs attention in the recorded state.', '') , true) +
      '</div></main>' +
      '<aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Gates</b><span class="right">HONEST STATE</span></div><div class="rpad">' + gatesMarkup() + '</div></div><div class="rpanel"><div class="rpanel-h"><b>How this stays honest</b><span>READ ONLY</span></div><div class="rpad note">Every value comes from task/slice/toolpack state, project manifests, engine probe state and live artifact files. Cache and scheduler cards stay empty until opt-in runs record stats; they never invent hits or workers.</div></div></aside>';
  }
  function nextRunActionId(stepId) {
    if (!detail) return 'run_all';
    var title = String(detail.title || '').toLowerCase();
    var step = String(stepId || '').toLowerCase();
    if (title.indexOf('leftbehind') >= 0 && ['build', 'demo', 'capture'].indexOf(step) >= 0) return 'leftbehind_' + step;
    if (title.indexOf('leftbehind') >= 0) return 'leftbehind';
    return 'run_all';
  }
  function renderRun() {
    shell.className = 'body detail-body';
    if (!detail) {
      var runs = (state && state.runs) || [];
      shell.innerHTML = '<main class="main" style="grid-column:1/-1"><div class="head"><div><h1>Run detail</h1><p>No run selected</p></div><div class="actions"><button class="btn ghost" data-view="overview">← Overview</button>' + runButton('run_all', 'Run all gates', true) + '</div></div>' +
        (runs.length ? emptyState('Select a run', 'Open a run from the overview or the runs rail; deep links support ?view=run&id=...', '<button class="btn small" data-run-id="' + esc(runs[0].id) + '">Open newest run</button>') : emptyState('No runs recorded yet', 'Run all gates once to create the first task state; run detail then shows steps, logs and hashes.', runAllActions())) +
        '</main>';
      return;
    }
    var steps = detail.steps || [];
    var failedSteps = steps.filter(function (step) { return step.status === 'failed'; });
    var stepHtml = steps.map(function (step, index) {
      return '<div class="step ' + (index === 0 ? 'active' : '') + (step.status === 'failed' ? ' failed' : '') + '"><div class="track"><span class="circle">' + (step.status === 'passed' ? '✓' : '!') + '</span>' + (index < steps.length - 1 ? '<span class="line"></span>' : '') + '</div><div class="sbody"><b>' + esc(step.id) + '</b><div class="s">' + esc(step.status) + '</div><div class="time">' + esc(secs(step.seconds)) + ' · ' + statusText(step.status) + '</div></div></div>';
    }).join('');
    var log = steps.map(function (step) { return '[step] ' + step.id + ' · ' + step.status + '\n' + (step.output || step.error || ''); }).join('\n');
    var validators = (detail.validators || []).map(function (v) {
      return '<tr><td class="runname">' + esc(v.id) + '</td><td>' + esc(v.artifact || v.target || '') + '</td><td><span class="status ' + (v.passed ? 'pass' : 'fail') + '">● ' + (v.passed ? 'PASS' : 'FAIL') + '</span></td><td class="t-mono">' + esc(v.kind || '') + '</td></tr>';
    }).join('');
    var artifactRows = (detail.artifacts || []).slice(0, 5).map(function (a) {
      return '<div class="ditem"><div class="n">' + esc((a.path || '').split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + '</div></div>';
    }).join('');
    var primaryAction = String(detail.title || '').toLowerCase().indexOf('leftbehind') >= 0 ? 'leftbehind' : 'run_all';
    var actions = failedSteps.map(function (step) {
      var actionId = nextRunActionId(step.id);
      return runButton(actionId, 'Retry ' + step.id, true);
    }).slice(0, 3).join('');
    if (!actions) actions = runButton(primaryAction, 'Re-run', false);
    var rem = detail.remediation || {};
    var remButtons = '';
    if (rem.retryAction && actionAvailable(rem.retryAction)) remButtons += runButton(rem.retryAction, 'Retry matching command', true);
    if (rem.command) remButtons += copyButton(rem.command, 'Copy command');
    var runLink = '?view=run&id=' + encodeURIComponent(detail.id || '');
    remButtons += copyButton(location.origin + '/' + runLink, 'Copy run link');
    var validatorTone = (detail.validators || []).length && (detail.validators || []).every(function (v) { return v.passed; }) ? 'var(--green)' : ((detail.validators || []).length ? 'var(--red)' : 'var(--dim)');
    shell.innerHTML = '<aside class="steprail"><div class="runmeta"><div class="k">Run</div><div class="v">' + esc(detail.title) + '</div><div style="height:6px"></div><div class="k">started / duration</div><div class="v">' + esc(shortTime(detail.startedAt)) + ' · ' + esc(secs(detail.durationSeconds)) + '</div><div style="height:6px"></div><div class="k">kind</div><div class="v">' + esc(detail.kind) + '</div></div><div class="label" style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:#546b79;margin:2px 2px 0">Steps</div><div class="steps">' + stepHtml + '</div><div class="note" style="margin-top:auto;border-top:1px solid #1a2c36;padding-top:9px">A failed step stops later steps. Retry only the failed step from the run inspector.</div></aside>' +
      '<main class="detailmain"><div class="detailhead"><div><h1>' + esc(detail.title) + '</h1><p>' + esc(detail.command) + '</p></div><div class="actions"><button class="btn small ghost" data-view="overview">← Runs</button>' + runButton(primaryAction, 'Re-run', false) + '</div></div>' +
      '<div class="runsummary"><div class="sum"><div class="k">Status</div><div class="v" style="color:' + (detail.passed ? 'var(--green)' : 'var(--red)') + '">' + statusText(detail.status) + '</div><div class="s">' + (detail.passed ? 'exit 0' : 'needs attention') + '</div></div><div class="sum"><div class="k">Steps</div><div class="v">' + steps.length + '</div><div class="s">' + steps.filter(function (x) { return x.status === 'passed'; }).length + ' passed</div></div><div class="sum"><div class="k">Artifacts</div><div class="v">' + (detail.artifacts || []).length + '</div><div class="s">hashed</div></div><div class="sum"><div class="k">Validators</div><div class="v" style="color:' + validatorTone + '">' + (detail.validators || []).length + '</div><div class="s">' + ((detail.validators || []).length ? ((detail.validators || []).every(function (v) { return v.passed; }) ? 'all checked' : 'attention') : 'none declared') + '</div></div></div>' +
      '<div class="tabs"><b>Logs</b><span>Overview</span><span>Artifacts</span></div><div class="logbox"><div class="loghead"><span style="color:' + (detail.passed ? 'var(--green)' : 'var(--red)') + '">●</span> ' + esc(detail.title) + ' <span class="right">READ ONLY EVIDENCE</span></div><div class="log" aria-live="polite">' + esc(log) + '</div></div>' +
      '<div class="recovery"><div class="recover ' + (failedSteps.length ? 'bad' : '') + '"><b>If a step fails</b><p>' + esc(rem.summary || 'Read the failed step output, then retry only that step. Later steps are skipped, not silently passed.') + '</p><div class="cardactions">' + remButtons + '</div></div><div class="recover"><b>Reproduce locally</b><p>Every action shows its argv before running. Copy the command or run it from the terminal.</p><div class="cardactions">' + copyButton(rem.command || detail.command || RUN_ALL, 'Copy command') + '</div></div></div>' +
      (validators ? '<div class="runs validators"><div class="runs-h"><b>Validator evidence</b><span>this run</span></div><table><thead><tr><th>Check</th><th>Artifact</th><th>Result</th><th>Kind</th></tr></thead><tbody>' + validators + '</tbody></table></div>' : '') +
      '</main><aside class="detailright"><div class="rpanel"><div class="rpanel-h"><b>Step artifacts</b><span class="right">HASHED</span></div><div class="rpad">' + artifactPanel(true) + '</div></div><div class="rpanel"><div class="rpanel-h"><b>Step actions</b><span class="right">WHITELISTED</span></div><div class="rpad" style="display:flex;flex-direction:column;gap:5px">' + actions + runButton('run_all', 'Re-run all gates', false) + '<div class="note">Re-running writes a new state record; it never edits the old one.</div></div></div><div class="rpanel"><div class="rpanel-h"><b>Artifacts</b><span class="right">' + (detail.artifacts || []).length + '</span></div><div class="rpad"><div class="diffgrid">' + (artifactRows || '<div class="note">This run declared no artifacts.</div>') + '</div></div></div></aside>';
  }
  function phaseMarkup(item) {
    var ok = item.status === 'done' || item.status === 'pass';
    return '<div class="phase-row"><span class="phase-num">' + esc(item.phase) + '</span><span class="phase-dot" style="background:' + (ok ? 'var(--green)' : item.status === 'blocked' ? 'var(--red)' : 'var(--amber)') + '"></span><div class="phase-main"><b>' + esc(item.label) + '</b><span>' + esc(item.detail) + '</span></div>' + badge(item.status, String(item.status).toUpperCase()) + '</div>';
  }
  function machineMarkup() {
    var m = state.machine || {};
    var detected = (insight().engine || {}).detected || {};
    var unity = (detected.unity || {}).version;
    var items = [['GPU', m.gpu || '—'], ['VRAM', (m.vramGb || '—') + ' GB'], ['RAM', (m.ramGb || '—') + ' GB'], ['Disk C', (m.diskC || '—') + ' GB free'], ['Disk D', (m.diskD || '—') + ' GB free'], ['Godot', m.godot || ((detected.godot || {}).version || '—')], ['Unity', unity || '—'], ['Python', state.machine && state.machine.python ? state.machine.python : '—']];
    return '<div class="machine-grid">' + items.map(function (x) { return '<div class="machine-item"><span>' + esc(x[0]) + '</span><b>' + esc(x[1]) + '</b></div>'; }).join('') + '</div>';
  }
  function commandRows() {
    return (state.commands || []).map(function (cmd) {
      return '<div class="command-row"><div class="command-main"><b>' + esc(cmd.label) + '</b><span>' + esc(cmd.hint || '') + '</span><code>' + esc(prettyCommand(cmd.id)) + '</code></div><div class="command-actions">' + runButton(cmd.id, 'Run', false) + copyButton(prettyCommand(cmd.id), 'Copy') + '</div></div>';
    }).join('');
  }
  function artifactGallery() {
    var items = (state.artifacts || []).filter(function (a) { return !searchQuery || (a.path || '').toLowerCase().indexOf(searchQuery.toLowerCase()) >= 0; });
    if (!items.length) return emptyState('No artifacts match', 'Artifacts are hashed files under build/, artifacts/ and design/docs evidence. Run the gate that produces them, or clear the search.', runAllActions());
    return '<div class="artifact-grid">' + items.map(function (a) {
      var isImage = /\.(png|jpe?g|webp)$/i.test(a.path || '');
      return '<div class="artifact-card clickable" data-artifact="' + esc(a.path) + '"><div class="artifact-thumb">' + (isImage ? '<img src="' + esc(previewUrl(a.path)) + '" alt="' + esc(a.path.split('/').pop()) + '">' : esc(a.kind || 'file')) + '</div><div class="artifact-name">' + esc(a.path.split('/').pop()) + '</div><div class="artifact-meta">' + esc(bytes(a.bytes)) + ' · ' + esc(a.kind || 'file') + '</div></div>';
    }).join('') + '</div>';
  }
  function jobOutputMarkup() {
    var job = state.job || {};
    if (!job.output) return 'No job running. Start a command to stream its output here (SSE with a polling fallback).';
    return job.output;
  }
  function renderMission() {
    shell.className = 'body';
    var engine = insight().engine || {};
    var posture = (engine.facts || []).join(' ');
    shell.innerHTML = railMarkup('mission') +
      '<main class="main"><div class="head"><div><h1>Mission control</h1><p>Machine, engines, phase ladder and gate health</p></div><div class="actions"><button class="btn ghost" data-view="insights">Insights</button>' + runButton('run_all', 'Run all', true) + '</div></div>' +
      '<div class="metrics">' + metricCard('Slices', (state.metrics.slicesPassed || 0) + ' / ' + (state.metrics.slicesTotal || 0), 'latest task', state.metrics.slicesTotal ? '● RECORDED' : 'NO RUN') + metricCard('Capabilities', state.metrics.capabilities || '—', 'valid manifests', '') + metricCard('Tests', state.metrics.tests === null || state.metrics.tests === undefined ? '—' : state.metrics.tests, 'workstream suite', state.metrics.tests ? '● RECORDED' : 'NOT RUN') + metricCard('Open gates', ((state.metrics.blocked || 0) + (state.metrics.untested || 0)), 'not silently passed', '', 'warn') + '</div>' +
      '<div class="bottomgrid"><div class="runs"><div class="runs-h"><b>Phase ladder</b><span>0 → 6</span></div><div class="phase-list">' + (state.phases || []).map(phaseMarkup).join('') + '</div></div>' +
      '<div class="runs"><div class="runs-h"><b>Environment</b><span>local machine</span></div><div class="rpad">' + machineMarkup() + '<div class="callout" style="margin-top:8px"><b>Engine posture</b> ' + esc(posture || 'Run engines probe to populate engine posture.') + '</div></div></div></div>' +
      '<div class="runs" style="margin-top:12px"><div class="runs-h"><b>Gate state</b><span>same source as the CLI</span></div><div class="rpad">' + gatesMarkup() + '</div></div>' +
      '</main><aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Mission notes</b><span>HONEST STATE</span></div><div class="rpad note">' + esc((insight().summary || []).slice(0, 4).join(' ')) + '</div></div><div class="rpanel"><div class="rpanel-h"><b>Recent runs</b><span>latest 4</span></div><div class="rpad" style="display:flex;flex-direction:column;gap:5px">' + ((state.runs || []).slice(0, 4).map(function (r) { return '<button class="btn small ghost" data-run-id="' + esc(r.id) + '" style="justify-content:space-between">' + esc(String(r.title).slice(0, 18)) + '<span class="status ' + (r.passed ? 'pass' : 'fail') + '">' + statusText(r.status) + '</span></button>'; }).join('') || '<div class="note">No runs yet.</div>') + '</div></div></aside>';
  }
  function renderCommands() {
    shell.className = 'body';
    shell.innerHTML = railMarkup('commands') +
      '<main class="main"><div class="head"><div><h1>Commands</h1><p>Fixed server-side whitelist; the browser sends an action id, never argv</p></div><div class="actions"><button class="btn ghost" data-view="overview">← Overview</button></div></div>' +
      '<div class="runs"><div class="runs-h"><b>Available commands</b><span>' + (state.commands || []).length + ' actions</span></div><div class="command-list">' + commandRows() + '</div></div>' +
      '<div class="bottomgrid"><div class="recover"><b>How actions run</b><p>Click Run, review the exact argv, then confirm. One job at a time; output streams into the drawer over SSE and falls back to polling.</p></div><div class="recover"><b>Safety boundary</b><p>Only server-side actions are accepted. There is no arbitrary shell and no browser-supplied argv.</p></div></div>' +
      '</main><aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Job output</b><span>LATEST</span></div><div class="rpad"><div class="logbox"><div class="loghead"><span style="color:var(--green)">●</span> /api/job · /api/logs/stream <span class="right">READ ONLY</span></div><div class="log" id="command-log" aria-live="polite">' + esc(jobOutputMarkup()) + '</div></div><div class="artfoot"><button class="btn small ghost" id="refresh">Refresh state</button><button class="btn small ghost" data-view="run">Open last run</button></div></div></div><div class="rpanel"><div class="rpanel-h"><b>Last job</b><span>' + esc((state.job && state.job.status ? state.job.status.toUpperCase() : 'IDLE')) + '</span></div><div class="rpad" style="font:9px/1.6 var(--mono);color:#93aab5">' + esc((state.job && state.job.action) || '—') + '<br>' + esc((state.job && state.job.commandLine) || 'No command has run in this process yet.') + '</div></div></aside>';
  }
  function renderReview() {
    shell.className = 'body';
    var gates = state.gates || [];
    var passing = gates.filter(function (g) { return g.status === 'pass'; }).length;
    var attention = gates.filter(function (g) { return g.status === 'untested'; }).length;
    var blocked = gates.filter(function (g) { return g.status === 'blocked'; }).length;
    shell.innerHTML = railMarkup('review') +
      '<main class="main"><div class="head"><div><h1>Review</h1><p>Release readiness, gates and evidence — no approval queue</p></div><div class="actions"><button class="btn ghost" data-view="insights">Insights</button>' + runButton('run_all', 'Re-run all', true) + '</div></div>' +
      '<div class="metrics">' + metricCard('Passing gates', passing, 'verified', '') + metricCard('Needs attention', attention, 'open gates', attention ? 'OPEN' : '', 'warn') + metricCard('Blocked', blocked, 'external constraint', blocked ? 'BLOCKED' : '', 'fail') + metricCard('Artifacts', (state.artifacts || []).length, 'hashed evidence', '') + '</div>' +
      '<div class="bottomgrid"><div class="runs"><div class="runs-h"><b>Release gates</b><span>automated</span></div><div class="rpad">' + gatesMarkup() + '</div></div><div class="runs"><div class="runs-h"><b>Evidence</b><span>selected artifacts</span></div><div class="rpad">' + artifactGallery() + '</div></div></div>' +
      '<div class="runs" style="margin-top:12px"><div class="runs-h"><b>Review checklist</b><span>derived from gates</span></div>' + readinessChecklist() + '</div>' +
      '</main><aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Review rule</b><span>READ ONLY</span></div><div class="rpad note">A gate is automated evidence, not an approval button. Untested and blocked are shown as such.<br><br>Use Run detail to inspect logs and retries.</div></div><div class="rpanel"><div class="rpanel-h"><b>Selected artifact</b><span>LIVE</span></div><div class="rpad">' + artifactPanel() + '</div></div></aside>';
  }
  function renderSlices() {
    shell.className = 'body';
    var items = (state.slices || []).filter(function (s) { return !searchQuery || (s.id || '').toLowerCase().indexOf(searchQuery.toLowerCase()) >= 0; });
    var rows = items.map(function (s) {
      var stepText = s.steps && typeof s.steps === 'object' ? (s.steps.passed + '/' + s.steps.total) : (typeof s.steps === 'number' ? s.steps : '—');
      var open = s.statePath ? ' data-run-id="' + esc(s.statePath) + '"' : ' data-stage-id="' + esc(s.id) + '"';
      return '<tr><td class="runname">' + esc(s.id) + '</td><td><span class="status ' + (s.passed ? 'pass' : 'fail') + '">● ' + statusText(s.status) + '</span></td><td>' + esc((s.detail || []).join(' → ')) + '</td><td class="t-mono">' + esc(stepText) + '</td><td class="t-mono">' + esc(secs(s.seconds)) + '</td><td class="t-mono">' + esc(s.artifacts || 0) + '</td><td style="text-align:right">' + runButton(s.id, 'Run', false) + ' <button class="btn small ghost" ' + open + '>Open</button></td></tr>';
    }).join('');
    var table = items.length ? '<div class="runs"><div class="runs-h"><b>Slice state</b><span>' + items.length + ' declared</span></div><table><thead><tr><th>Slice</th><th>Status</th><th>Steps</th><th>Progress</th><th>Duration</th><th>Artifacts</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' : emptyState('No slice state', 'Slices appear after the orchestrator writes state. Run all gates to create it.', runAllActions());
    shell.innerHTML = railMarkup('slices') +
      '<main class="main"><div class="head"><div><h1>Slices</h1><p>Declared slices, their steps, duration and artifacts</p></div><div class="actions">' + runButton('run_all', 'Run all slices', true) + '</div></div>' + table +
      '<div class="bottomgrid"><div class="recover"><b>Run state is derived</b><p>Every row comes from the latest slice state; old runs remain available in the Runs view.</p></div><div class="recover"><b>Failures are explicit</b><p>A failed slice stops later steps; open Run detail for logs and retry controls.</p></div></div></main>' +
      '<aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Pipeline</b><span>ORDERED</span></div><div class="rpad" style="display:flex;flex-direction:column;gap:5px">' + ((state.slices || []).map(function (s) { return '<div class="gate"><span class="d" style="background:' + (s.passed ? 'var(--green)' : 'var(--red)') + '"></span><div class="g"><b>' + esc(s.id) + '</b><p>' + esc(secs(s.seconds)) + ' · ' + esc(s.status) + '</p></div></div>'; }).join('') || '<div class="note">No slices yet.</div>') + '</div></div></aside>';
  }
  function renderArtifacts() {
    shell.className = 'body';
    shell.innerHTML = railMarkup('artifacts') +
      '<main class="main"><div class="head"><div><h1>Artifacts</h1><p>Hashed evidence produced by the workstream</p></div><div class="actions"><button class="btn ghost" data-view="overview">← Overview</button></div></div><div class="runs"><div class="runs-h"><b>Artifact library</b><span>' + (state.artifacts || []).length + ' files</span></div><div class="rpad">' + artifactGallery() + '</div></div><div class="bottomgrid"><div class="recover"><b>Live metadata</b><p>Size and hash are read from the current file; previews never modify the artifact.</p></div><div class="recover"><b>Path safety</b><p>Only build/, artifacts/, docs/ and design/ are readable; traversal is rejected.</p></div></div></main>' +
      '<aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Selected artifact</b><span>LIVE HASH</span></div><div class="rpad">' + artifactPanel() + '</div></div></aside>';
  }
  function render() {
    if (!state) return;
    document.querySelectorAll('.tab').forEach(function (tab) {
      var active = tab.getAttribute('data-view') === view;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.setAttribute('tabindex', active ? '0' : '-1');
    });
    if (view === 'run') renderRun();
    else if (view === 'insights') renderInsights();
    else if (view === 'mission') renderMission();
    else if (view === 'commands') renderCommands();
    else if (view === 'review') renderReview();
    else if (view === 'slices') renderSlices();
    else if (view === 'artifacts') renderArtifacts();
    else renderOverview();
  }
  function loadState() {
    return fetch('/api/state', { cache: 'no-store' }).then(function (res) { if (!res.ok) throw new Error('state HTTP ' + res.status); return res.json(); }).then(function (data) {
      state = data;
      if (!selectedArtifact) selectedArtifact = defaultArtifact();
      if (selectedArtifact && (!artifactMeta || artifactMeta.path !== selectedArtifact)) loadArtifact(selectedArtifact, true);
      if (view === 'run' && !detail && selectedRunId) return loadRun(selectedRunId).then(render);
      if (view === 'run' && !detail) {
        var first = (state.runs || [])[0];
        if (first) return loadRun(first.id).then(render);
      }
      render();
    }).catch(function (err) {
      shell.innerHTML = emptyState('Dashboard backend unreachable', 'The local state endpoint failed: ' + err.message + '. Start the server with python workstream/gypsy.py dashboard --no-open, then refresh.', '<button class="btn small" id="refresh">Retry</button>');
    });
  }
  function loadRun(id) {
    selectedRunId = id;
    return fetch('/api/run?id=' + encodeURIComponent(id), { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (data) {
      detail = data;
      selectedArtifact = defaultArtifact();
      render();
    }).catch(function (err) { shell.innerHTML = emptyState('Could not load run', err.message + '. The run id must be a state file under workstream/state.', '<button class="btn small ghost" data-view="overview">← Overview</button>'); });
  }
  function openRun(id) {
    view = 'run';
    detail = null;
    try { history.replaceState(null, '', '?view=run&id=' + encodeURIComponent(id)); } catch (e) {}
    loadRun(id).then(function () { render(); focusHeading(); });
  }
  function loadArtifact(path, rerender) {
    selectedArtifact = path;
    fetch('/api/artifact?path=' + encodeURIComponent(path), { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (meta) { artifactMeta = meta; if (rerender !== false) render(); }).catch(function () { artifactMeta = null; });
  }
  function showModal(action) {
    var cmd = commandFor(action);
    if (!cmd) { showToast('Unknown action', true); return; }
    pendingAction = action;
    document.getElementById('modal-title').textContent = 'Run ' + action + '?';
    document.getElementById('modal-hint').textContent = 'This executes a real local command and writes state under workstream/state.';
    document.getElementById('modal-cmd').textContent = prettyCommand(action);
    document.getElementById('modal').classList.add('show');
    var focusTarget = document.getElementById('modal-cancel');
    if (focusTarget) focusTarget.focus();
  }
  function runPending() {
    var action = pendingAction;
    if (!action) return;
    document.getElementById('modal').classList.remove('show');
    pendingAction = null;
    fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Gypsy-Token': token }, body: JSON.stringify({ action: action }) }).then(function (res) { return res.json().then(function (body) { return { status: res.status, body: body }; }); }).then(function (result) {
      if (result.status !== 202) { showToast((result.body && result.body.error) || 'Could not start', true); return; }
      showJob(action);
    }).catch(function (err) { showToast('Run failed: ' + err.message, true); });
  }
  function jobButtons(job) {
    var rem = job.remediation || {};
    var buttons = '';
    var status = job.status;
    if (status === 'failed') {
      if (rem.retryAction && actionAvailable(rem.retryAction)) buttons += runButton(rem.retryAction, 'Retry', true);
      if (rem.command) buttons += copyButton(rem.command);
      buttons += viewLink('?view=run', 'Open latest run');
    } else if (status === 'running') {
      if (rem.command) buttons += copyButton(rem.command);
    } else {
      if (rem.command) buttons += copyButton(rem.command);
      buttons += viewLink('?view=run', 'Open latest run');
    }
    var summary = rem.summary ? '<span class="remsum">' + esc(rem.summary) + '</span>' : '';
    return summary + buttons;
  }
  function updateJob(job) {
    var stateEl = document.getElementById('job-state');
    var liveEl = document.getElementById('job-live');
    stateEl.textContent = (job.status || 'idle').toUpperCase();
    stateEl.className = 'status ' + (job.status === 'passed' ? 'pass' : job.status === 'failed' ? 'fail' : 'warn');
    document.getElementById('job-title').textContent = job.action || 'run';
    var outputEl = document.getElementById('job-output');
    outputEl.textContent = job.output || (job.status === 'running' ? 'starting…' : 'No output captured.');
    var meta = job.commandLine || (job.command ? job.command.join(' ') : '');
    document.getElementById('job-meta').textContent = meta;
    if (liveEl) {
      liveEl.textContent = job.status === 'running' ? (jobTransport === 'sse' ? 'LIVE · SSE' : 'LIVE · POLL') : (job.status === 'failed' ? 'FAILED' : 'DONE');
      liveEl.className = 'live ' + (job.status === 'running' ? 'on' : 'off');
    }
    var actionsEl = document.getElementById('job-actions');
    if (actionsEl) actionsEl.innerHTML = jobButtons(job);
  }
  function stopJobStream() {
    if (jobStream) { try { jobStream.close(); } catch (e) {} jobStream = null; }
  }
  function finishJob(job) {
    if (jobFinished) return;
    jobFinished = true;
    stopJobStream();
    loadState();
    if (view === 'run' && selectedRunId) loadRun(selectedRunId);
    showToast(job && job.status === 'failed' ? 'Command failed — review the output, then retry or copy the command.' : 'Command passed.', !!(job && job.status === 'failed'));
  }
  function pollJob() {
    if (pollTimer) clearTimeout(pollTimer);
    fetch('/api/job', { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (job) {
      updateJob(job);
      if (job.status === 'running') pollTimer = setTimeout(pollJob, 1000);
      else if (job.status === 'passed' || job.status === 'failed') finishJob(job);
    }).catch(function () { pollTimer = setTimeout(pollJob, 2000); });
  }
  function startPolling() {
    if (jobFinished) return;
    jobTransport = 'poll';
    pollJob();
  }
  function startJobStream() {
    stopJobStream();
    if (!window.EventSource) { startPolling(); return; }
    jobTransport = 'sse';
    try {
      jobStream = new EventSource('/api/logs/stream');
      jobStream.addEventListener('job', function (event) { updateJob(JSON.parse(event.data)); });
      jobStream.addEventListener('done', function (event) {
        var job = JSON.parse(event.data);
        updateJob(job);
        finishJob(job);
      });
      jobStream.addEventListener('idle', function () {
        stopJobStream();
        startPolling();
      });
      jobStream.onerror = function () {
        if (!jobStream) return;
        stopJobStream();
        startPolling();
      };
    } catch (err) {
      startPolling();
    }
  }
  function showJob(action) {
    jobFinished = false;
    document.getElementById('job').classList.add('show');
    updateJob({ status: 'running', action: action || 'run', output: '', commandLine: commandFor(action || '') });
    startJobStream();
  }
  function showToast(message, bad) {
    var el = document.getElementById('toast');
    el.textContent = message;
    el.style.display = 'block';
    el.style.borderColor = bad ? '#6d3434' : '#2b4b54';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.style.display = 'none'; }, 6000);
  }
  function focusHeading() {
    var heading = shell.querySelector('h1');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      try { heading.focus({ preventScroll: true }); } catch (e) { heading.focus(); }
    }
  }
  function setView(next) {
    view = next;
    detail = null;
    if (view === 'run' && !selectedRunId) {
      var first = state && state.runs && state.runs[0];
      if (first) selectedRunId = first.id;
    }
    try { history.replaceState(null, '', '?view=' + view); } catch (e) {}
    if (view === 'run' && selectedRunId) loadRun(selectedRunId).then(function () { render(); focusHeading(); });
    else { render(); focusHeading(); }
  }
  document.addEventListener('click', function (ev) {
    var tab = ev.target.closest('[data-view]');
    if (tab) { ev.preventDefault(); setView(tab.getAttribute('data-view')); return; }
    var runId = ev.target.closest('[data-run-id]');
    if (runId && runId.getAttribute('data-run-id')) { ev.preventDefault(); openRun(runId.getAttribute('data-run-id')); return; }
    var stage = ev.target.closest('[data-stage-id]');
    if (stage && !stage.getAttribute('data-run-id')) {
      var stageId = stage.getAttribute('data-stage-id');
      var match = (state.runs || []).filter(function (r) { return String(r.title || '').toLowerCase().indexOf(stageId.toLowerCase()) >= 0; })[0];
      if (match) { openRun(match.id); } else { showToast('No recorded run for this stage yet.', false); }
      return;
    }
    var run = ev.target.closest('[data-run]');
    if (run) { showModal(run.getAttribute('data-run')); return; }
    var art = ev.target.closest('[data-artifact]');
    if (art) { loadArtifact(art.getAttribute('data-artifact')); return; }
    var help = ev.target.closest('[data-help]');
    if (help) {
      var kind = help.getAttribute('data-help');
      showToast(kind === 'device-connect' ? 'Device launch is verified by the recorded emulator evidence. Physical-device, input and performance checks remain separate.' : 'Open the Device launch gate detail to see what was and was not verified.', false);
      return;
    }
    var scroll = ev.target.closest('[data-scroll]');
    if (scroll) {
      if (view !== 'overview') setView('overview');
      setTimeout(function () { var target = document.getElementById('overview-' + scroll.getAttribute('data-scroll')); if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 60);
      return;
    }
    var copy = ev.target.closest('[data-copy]');
    if (copy) {
      var textValue = copy.getAttribute('data-copy') || '';
      if (textValue && navigator.clipboard) {
        navigator.clipboard.writeText(textValue).then(function () { showToast('Copied.', false); }).catch(function () { showToast('Copy failed; select the text manually.', true); });
      } else { showToast(textValue || 'Nothing to copy.', !textValue); }
      return;
    }
    if (ev.target.closest('#modal-cancel') || ev.target.id === 'modal') { document.getElementById('modal').classList.remove('show'); return; }
    if (ev.target.closest('#modal-run')) { runPending(); return; }
    if (ev.target.closest('#job-close')) { document.getElementById('job').classList.remove('show'); stopJobStream(); return; }
    if (ev.target.closest('#refresh')) { loadState(); return; }
    if (ev.target.closest('#run-all')) { showModal('run_all'); return; }
  });
  var searchInput = document.getElementById('search');
  if (searchInput) searchInput.addEventListener('input', function () { searchQuery = searchInput.value.trim(); if (view === 'overview' || view === 'slices' || view === 'artifacts') render(); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') {
      document.getElementById('modal').classList.remove('show');
      document.getElementById('job').classList.remove('show');
      stopJobStream();
      return;
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      var input = document.getElementById('search');
      if (input) input.focus();
      return;
    }
    var tab = ev.target.closest('[role="tab"]');
    if (tab && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft' || ev.key === 'Home' || ev.key === 'End')) {
      ev.preventDefault();
      var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
      var index = tabs.indexOf(tab);
      var target = index;
      if (ev.key === 'ArrowRight') target = (index + 1) % tabs.length;
      else if (ev.key === 'ArrowLeft') target = (index - 1 + tabs.length) % tabs.length;
      else if (ev.key === 'Home') target = 0;
      else target = tabs.length - 1;
      var chosen = tabs[target];
      chosen.focus();
      setView(chosen.getAttribute('data-view'));
    }
  });
  var query = new URLSearchParams(location.search);
  var allowedViews = ['overview', 'insights', 'run', 'mission', 'commands', 'review', 'slices', 'artifacts'];
  var queryView = query.get('view');
  view = allowedViews.indexOf(queryView) >= 0 ? queryView : 'overview';
  selectedRunId = query.get('id') || null;
  loadState();
  setInterval(function () { if (!document.hidden) loadState(); }, 15000);
})();
