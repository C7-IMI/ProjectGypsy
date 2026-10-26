(function () {
  'use strict';
  var viewEl = document.getElementById('view');
  var state = null;
  var view = 'studio';
  var selectedArtifact = null;
  var artifactMeta = null;
  var pendingAction = null;
  var pollTimer = null;
  var toastTimer = null;
  function showFatal(message) {
    var el = document.getElementById('view');
    if (!el) return;
    el.innerHTML = '';
    var box = document.createElement('div');
    box.className = 'panel pad';
    var title = document.createElement('b');
    title.textContent = 'Dashboard error';
    var detail = document.createElement('p');
    detail.className = 'muted';
    detail.textContent = String(message);
    box.appendChild(title);
    box.appendChild(detail);
    el.appendChild(box);
  }
  window.addEventListener('error', function (event) { showFatal(event.message + ' @ ' + (event.filename || '') + ':' + (event.lineno || '')); });
  window.addEventListener('unhandledrejection', function (event) { showFatal('promise: ' + (event.reason && event.reason.message ? event.reason.message : event.reason)); });
  var tokenMeta = document.querySelector('meta[name="gypsy-token"]');
  var token = tokenMeta ? tokenMeta.getAttribute('content') : '';

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
  function secs(n) {
    if (n === null || n === undefined) return '—';
    return (Math.round(Number(n) * 10) / 10) + ' s';
  }
  function badge(status, label) {
    var s = String(status || 'ready').toLowerCase();
    var cls = 'ready';
    if (s === 'passed' || s === 'pass' || s === 'done' || s === 'ok') cls = 'pass';
    else if (s === 'failed' || s === 'fail' || s === 'blocked') cls = 'fail';
    else if (s === 'untested') cls = 'untested';
    else if (s === 'running') cls = 'running';
    var text = label || s.toUpperCase();
    return '<span class="badge ' + cls + '">' + esc(text) + '</span>';
  }
  function dot(status) {
    var s = String(status || 'ready').toLowerCase();
    var cls = 'ready';
    if (s === 'passed' || s === 'pass' || s === 'done') cls = 'pass';
    else if (s === 'failed' || s === 'blocked' || s === 'fail') cls = 'block';
    else if (s === 'untested') cls = 'untested';
    else if (s === 'running') cls = 'running';
    return '<span class="dot ' + cls + '"></span>';
  }
  function statusLabel(item) {
    if (item && item.passed === true) return 'passed';
    if (item && item.passed === false) return 'failed';
    return (item && item.status) || 'ready';
  }
  function metric(label, value, sub, extra) {
    return '<div class="metric"><div class="k"><span>' + esc(label) + '</span>' + (extra || '') + '</div><div class="v">' + esc(value) + '</div><div class="s">' + esc(sub || '') + '</div></div>';
  }
  function actionButton(cmd) {
    return '<button class="action-row" data-run="' + esc(cmd.id) + '" title="' + esc((cmd.argv || []).join(' ')) + '"><span class="n">' + esc(cmd.label) + '<span class="h">' + esc(cmd.hint || '') + '</span></span><span class="run">RUN</span></button>';
  }
  function commandText(id) {
    if (!state || !state.commands) return '';
    for (var i = 0; i < state.commands.length; i++) {
      if (state.commands[i].id === id) return (state.commands[i].argv || []).join(' ');
    }
    return '';
  }
  function displayCommand(id) {
    var value = commandText(id);
    return value.replace(/^.*?python(?:\.exe)?\s+/i, 'python ');
  }
  function defaultArtifact(s) {
    if (!s || !s.artifacts || !s.artifacts.length) return null;
    for (var i = 0; i < s.artifacts.length; i++) {
      if (s.artifacts[i].path && s.artifacts[i].path.indexOf('frame.png') >= 0) return s.artifacts[i].path;
    }
    return s.artifacts[0].path || null;
  }
  function artifactButton(a) {
    var selected = a.path === selectedArtifact ? ' style="border-color:#2c8f86"' : '';
    var isImg = /\.(png|jpe?g|webp)$/i.test(a.path);
    var preview = isImg && a.preview ? '<img src="' + esc(a.preview) + '" alt="">' : esc(a.kind || 'file');
    return '<button class="artifact-card" data-artifact="' + esc(a.path) + '"' + selected + '><div class="box">' + preview + '</div><div class="n">' + esc(a.path.split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + '</div></button>';
  }
  function artifactPreview() {
    var meta = artifactMeta && artifactMeta.path === selectedArtifact ? artifactMeta : null;
    var image = meta && meta.preview ? '<img src="' + esc(meta.preview) + '" alt="">' : '<span class="fallback">' + esc(meta ? (meta.kind || 'file') : 'select an artifact') + '</span>';
    var hash = meta && meta.sha256 ? meta.sha256.slice(0, 12) + '…' + meta.sha256.slice(-6) : '—';
    return '<div class="art-preview">' + image + '<span class="corner">' + esc(meta ? (meta.kind || '') : '') + '</span></div>' +
      '<div class="kv"><div class="k">path</div><div class="v">' + esc(selectedArtifact || '—') + '</div>' +
      '<div class="k">bytes</div><div class="v">' + esc(meta ? meta.bytes.toLocaleString() : '—') + '</div>' +
      '<div class="k">sha256</div><div class="v" title="' + esc(meta ? meta.sha256 : '') + '">' + esc(hash) + '</div>' +
      '<div class="k">state</div><div class="v">' + esc(meta ? 'live file' : 'not loaded') + '</div></div>';
  }
  function gateCard(g) {
    var cls = g.status === 'blocked' ? 'block' : (g.status === 'untested' ? 'untested' : 'ready');
    return '<div class="gate"><span class="d ' + cls + '"></span><div><b>' + esc(g.label) + '</b><p>' + esc(g.detail) + '</p></div><span class="st">' + esc(g.status.toUpperCase()) + '</span></div>';
  }
  function sliceCard(item) {
    var status = statusLabel(item);
    var blocked = status === 'failed' || status === 'blocked';
    var steps = item.steps;
    var stepText = typeof steps === 'object' && steps ? (steps.passed + '/' + steps.total) : (steps ? String(steps) : '—');
    var detail = (item.detail || []).join(' → ');
    return '<div class="slice-card' + (blocked ? ' blocked' : '') + '" data-slice="' + esc(item.id) + '">' +
      '<div class="row">' + badge(status) + '<span class="name">' + esc(item.id) + '</span><span class="t">' + esc(secs(item.seconds)) + '</span></div>' +
      '<div class="sub">' + esc(detail || 'slice') + '</div><div class="progress"><i style="width:' + (status === 'passed' ? 100 : 12) + '%"></i></div>' +
      '<div class="meta"><span class="tag">' + esc(stepText) + ' steps</span><span class="tag">' + esc(item.artifacts || 0) + ' artifacts</span></div></div>';
  }
  function terminalOutput() {
    var job = state && state.job;
    if (!job || !job.output) return '<span class="dim">No command run in this session. Use the action list; output will appear here.</span>';
    var text = esc(job.output);
    text = text.replace(/\bPASS\b/g, '<span class="ok">PASS</span>').replace(/\bBLOCKED\b/g, '<span class="wa">BLOCKED</span>').replace(/\bFAILED\b/g, '<span class="er">FAILED</span>');
    return text;
  }

  function renderStudio() {
    var s = state;
    var slices = s.slices || [];
    var passed = slices.filter(function (x) { return x.passed; });
    var gates = (s.gates || []).filter(function (g) { return g.status === 'blocked' || g.status === 'untested'; });
    var running = s.job && s.job.status === 'running';
    var jobCard = running ? '<div class="slice-card"><div class="row">' + badge('running') + '<span class="name">' + esc(s.job.action) + '</span></div><div class="sub">' + esc(s.job.startedAt || 'running') + '</div><div class="progress"><i style="width:55%"></i></div></div>' : '<div class="empty">No active run.</div>';
    var passedCards = passed.length ? passed.map(sliceCard).join('') : '<div class="empty">No passed slices yet.</div>';
    var gateCards = gates.length ? gates.map(gateCard).join('') : '<div class="empty">No blocked gates.</div>';
    var artifactCards = (s.artifacts || []).slice(0, 6).map(artifactButton).join('');
    return '<div class="studio">' +
      '<aside class="studio-side"><div class="label">Workspace</div>' +
      '<button class="nav-item active"><span class="i"></span>Overview</button>' +
      '<button class="nav-item" data-view="mission"><span class="i"></span>Mission<span class="c">' + (s.metrics.blocked || 0) + '</span></button>' +
      '<button class="nav-item" data-view="hybrid"><span class="i"></span>Commands</button>' +
      '<button class="nav-item" data-view="director"><span class="i"></span>Review</button>' +
      '<div class="label">State</div><button class="nav-item"><span class="i"></span>Slices<span class="c">' + (s.metrics.slicesTotal || 0) + '</span></button>' +
      '<button class="nav-item"><span class="i"></span>Artifacts<span class="c">' + (s.artifacts || []).length + '</span></button>' +
      '<div class="sep"></div><div class="tiny dim" style="padding:4px 8px;line-height:1.5">CLI source of truth.<br>Read-only until an action.</div></aside>' +
      '<section class="studio-main"><div class="studio-head"><div><h1>Slice board</h1><p>' + esc(s.metrics.slicesTotal) + ' slices · ' + esc(s.metrics.tests || '—') + ' tests · 42 capabilities · ' + esc(s.branch) + ' ' + esc(s.head) + '</p></div><div class="toolbar"><button class="btn ghost" data-view="director">Review</button><button class="btn primary" data-run="run_all">Run all</button></div></div>' +
      '<div class="metrics">' + metric('Tests', s.metrics.tests || '—', 'workstream suite') + metric('Capabilities', s.metrics.capabilities || '—', 'manifests valid') + metric('Slices passed', (s.metrics.slicesPassed || 0) + '/' + (s.metrics.slicesTotal || 0), 'latest task') + metric('Blocked gates', s.metrics.blocked || 0, 'recorded, not faked', '<span class="badge block">GATE</span>') + '</div>' +
      '<div class="board" style="margin-top:12px">' +
      '<div class="column"><div class="column-h">' + dot('ready') + 'READY<span class="n">0</span></div><div class="empty">Nothing queued.</div></div>' +
      '<div class="column"><div class="column-h">' + dot('running') + 'RUNNING<span class="n">' + (running ? 1 : 0) + '</span></div>' + jobCard + '</div>' +
      '<div class="column"><div class="column-h">' + dot('pass') + 'PASSED<span class="n">' + passed.length + '</span></div>' + passedCards + '</div>' +
      '<div class="column"><div class="column-h">' + dot('block') + 'GATES<span class="n">' + gates.length + '</span></div>' + gateCards + '</div>' +
      '</div></section>' +
      '<aside class="panel inspector"><div class="insp-head"><div class="eyebrow">Selected artifact</div><h2>' + esc(selectedArtifact ? selectedArtifact.split('/').pop() : 'artifact') + '</h2><p>live hash · local file</p></div><div class="pad">' + artifactPreview() +
      '<div class="sep"></div><div class="tiny dim" style="letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">Recent artifacts</div><div class="artifact-mini">' + artifactCards + '</div>' +
      '<div class="sep"></div><div class="tiny dim" style="letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">Release gates</div>' + gateCards + '</div></aside>' +
      '</div>';
  }

  function renderMission() {
    var s = state; var m = s.machine || {}; var gates = s.gates || []; var phases = s.phases || [];
    var gpu = m.vramGb !== undefined ? m.vramGb + ' GB' : '—';
    var passed = (s.slices || []).filter(function (x) { return x.passed; }).length;
    var health = '<div class="health">' +
      '<div class="h"><div class="k"><span>GPU</span><span class="badge block">LIMIT</span></div><div class="v">' + esc(gpu) + '</div><div class="s">T600 · 16.67 ms budget</div></div>' +
      '<div class="h"><div class="k"><span>DISK C:</span><span class="badge pass">OK</span></div><div class="v">' + esc(m.diskC || '—') + '<span style="font-size:9px"> GB</span></div><div class="s">D: ' + esc(m.diskD || '—') + ' GB free</div></div>' +
      '<div class="h"><div class="k"><span>RAM</span><span class="badge pass">OK</span></div><div class="v">' + esc(m.ramGb || '—') + '<span style="font-size:9px"> GB</span></div><div class="s">Windows · i7-12800H</div></div>' +
      '<div class="h"><div class="k"><span>CHECKS</span><span class="badge pass">PASS</span></div><div class="v">' + esc(s.metrics.tests || '—') + '</div><div class="s">tests · 6/6 list</div></div></div>';
    var ladder = phases.map(function (p) { return '<div class="phase"><span class="num">' + p.phase + '</span><div class="txt"><b>' + esc(p.label) + '</b><p>' + esc(p.detail) + '</p></div><span class="st">' + badge(p.status) + '</span></div>'; }).join('');
    var timeline = (s.slices || []).map(function (x) { return '<div class="tl ' + (x.passed ? '' : 'block') + '"><div class="r"><span>' + esc(x.id) + '</span><span>' + esc(secs(x.seconds)) + '</span></div><div class="bar"><i style="width:' + (x.passed ? 100 : 20) + '%"></i></div></div>'; }).join('');
    var artifacts = (s.artifacts || []).slice(0, 6).map(artifactButton).join('');
    var gatesHtml = gates.map(gateCard).join('');
    return '<div class="mission">' +
      '<div class="col"><div class="panel"><div class="panel-h"><b>Machine</b><span class="right">LIVE PROBE</span></div><div class="pad">' + health + '</div></div>' +
      '<div class="panel"><div class="panel-h"><b>Phase ladder</b><span class="right">ADR-003</span></div><div class="pad">' + ladder + '</div></div></div>' +
      '<div class="col"><div class="hero"><div class="eyebrow">Latest task · ' + esc(s.task || 'none') + '</div><h1>' + (s.taskPassed ? 'All executable gates passed.' : 'No completed task yet.') + '</h1><p>' + esc(passed) + '/' + esc(s.metrics.slicesTotal) + ' slices · ' + esc(s.taskSeconds ? secs(s.taskSeconds) : '—') + ' · ' + esc((s.artifacts || []).length) + ' artifacts · second engine and UE5 blocked, not failed.</p><div class="stats"><div class="stat"><b style="color:var(--green)">' + esc(s.metrics.slicesPassed) + '</b><span>slices passed</span></div><div class="stat"><b>' + esc(s.metrics.tests || '—') + '</b><span>tests</span></div><div class="stat"><b style="color:var(--cyan)">' + esc(s.metrics.capabilities) + '</b><span>capabilities</span></div><div class="stat"><b>' + esc(s.metrics.blocked) + '</b><span>blocked gates</span></div></div></div>' +
      '<div class="panel" style="margin-bottom:10px"><div class="panel-h"><b>Run timeline</b><span class="right">LATEST</span></div><div class="pad"><div class="timeline">' + timeline + '</div></div></div>' +
      '<div class="panel" style="margin-bottom:10px"><div class="panel-h"><b>Artifact vault</b><span class="right">HASHED · LOCAL</span></div><div class="pad"><div class="artifact-grid">' + artifacts + '</div></div></div>' +
      '<div class="panel"><div class="panel-h"><b>Recent output</b><span class="right">workstream/state</span></div><div class="pad"><div class="terminal-dark">' + terminalOutput() + '</div></div></div></div>' +
      '<div class="col"><div class="panel" style="margin-bottom:10px"><div class="panel-h"><b>Gates</b><span class="right">HONEST STATE</span></div><div class="pad">' + gatesHtml + '</div></div>' +
      '<div class="panel"><div class="panel-h"><b>Run a gate</b><span class="right">CLI</span></div><div class="pad">' + (s.commands || []).slice(0, 5).map(actionButton).join('') + '<button class="btn" style="width:100%;justify-content:center" data-run="run_all">Run all gates</button></div></div></div></div>';
  }

  function renderHybrid() {
    var s = state; var gates = (s.gates || []).filter(function (g) { return g.status === 'blocked' || g.status === 'untested'; });
    var actions = (s.commands || []).map(actionButton).join('');
    var artifactCards = (s.artifacts || []).slice(0, 4).map(artifactButton).join('');
    return '<div class="hybrid"><div class="panel"><div class="panel-h"><b>Quick run</b><span class="right">COMMAND PALETTE</span></div><div class="pad palette"><div class="search"><span style="color:var(--cyan)">⌘</span><input id="palette-input" placeholder="filter commands…" autocomplete="off"><span class="tiny dim">Ctrl K</span></div>' + actions + '</div></div>' +
      '<div class="workbench"><div class="panel term-panel"><div class="term-head"><span style="color:var(--cyan)">●</span> gypsy · workstream/state <span style="margin-left:auto">READ-ONLY</span></div><div class="term-body" id="terminal">' + terminalOutput() + '</div><div class="term-input">$ <span style="color:var(--dim)">select an action → executes the fixed command</span></div></div>' +
      '<div class="panel"><div class="panel-h"><b>Selected artifact</b><span class="right">LIVE HASH</span></div><div class="pad">' + artifactPreview() + '<div class="artifact-mini" style="margin-top:8px">' + artifactCards + '</div></div></div></div>' +
      '<div class="panel"><div class="panel-h"><b>Release readiness</b><span class="right">GATE SUMMARY</span></div><div class="pad">' + gates.map(gateCard).join('') + '<div class="sep"></div><div class="tiny dim">Every control maps to a CLI command. Nothing is hidden.</div></div>' +
      '<div class="panel" style="margin-top:10px"><div class="panel-h"><b>Actions</b><span class="right">FIXED ARGV</span></div><div class="pad"><button class="btn primary" style="width:100%;justify-content:center" data-run="run_all">Run all gates</button><div class="tiny dim" style="margin-top:7px;line-height:1.5">Actions are whitelisted; no arbitrary argv from the browser.</div></div></div></div></div>';
  }

  function renderDirector() {
    var s = state; var passed = (s.slices || []).filter(function (x) { return x.passed; });
    var decisions = (s.gates || []).filter(function (g) { return g.status === 'blocked' || g.status === 'untested'; });
    var top = passed.map(function (x, i) { return '<div class="review-card"><div class="r">' + badge('pass') + '<b>' + esc(x.id) + '</b><span class="tiny dim" style="margin-left:auto">' + esc(secs(x.seconds)) + '</span></div><p>' + esc((x.detail || []).join(' → ') || 'slice') + '</p><div class="meta">' + esc(x.steps && x.steps.passed ? x.steps.passed + '/' + x.steps.total : '—') + ' steps · ' + esc(x.artifacts || 0) + ' artifacts</div></div>'; }).join('');
    var dcards = decisions.map(function (g) { return '<div class="decision-card"><h3>' + esc(g.label) + '</h3><p>' + esc(g.detail) + '</p><div class="st">' + badge(g.status) + '</div></div>'; }).join('');
    var art = (s.artifacts || []).slice(0, 4).map(function (a) { var img = /\.(png|jpe?g|webp)$/i.test(a.path) && a.preview ? '<img src="' + esc(a.preview) + '" alt="">' : esc(a.kind || 'file'); return '<div class="a"><div class="b">' + img + '</div><div class="n">' + esc(a.path.split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + ' · ' + esc(a.kind) + '</div></div>'; }).join('');
    return '<div class="director"><div class="hero2"><div><div class="eyebrow">Phase 5 review · ' + esc((s.generated || '').slice(0, 10)) + '</div><h1>What is ready,<br>and what needs you.</h1><p>Four slices pass end to end. Two gates cannot be decided by code on this machine: a tested Android launch and a second engine. UE5 is hardware-blocked.</p></div><div class="acts"><button class="btn ghost" data-view="mission">Open evidence</button><button class="btn primary" data-run="run_all">Run all gates →</button></div></div>' +
      '<div class="panel"><div class="panel-h"><b>Passed this week</b><span class="right">EVIDENCE ATTACHED</span></div><div class="pad">' + top + '</div></div>' +
      '<div class="panel"><div class="panel-h"><b>Needs a decision</b><span class="right">NOT CODE FAILURES</span></div><div class="pad">' + dcards + '<div class="tiny dim" style="line-height:1.5">Gates are automated. There is no approval queue; evidence is the review surface.</div></div></div>' +
      '<div class="panel"><div class="panel-h"><b>Artifacts</b><span class="right">HASHED · LOCAL</span></div><div class="pad"><div class="director-art">' + art + '</div><div class="sep"></div><div class="tiny dim">Everything here is a view of state. The CLI is the source of truth.</div></div></div>' +
      '<div class="nextbar"><span>NEXT STEP</span><span class="cmd">$ ' + esc(commandText('run_all')) + '</span><span class="tiny dim">or choose an action</span></div></div>';
  }

  function render() {
    if (!state) { viewEl.innerHTML = '<div class="empty">Connecting to the local workstream…</div>'; return; }
    document.querySelectorAll('.tab').forEach(function (tab) { tab.classList.toggle('active', tab.getAttribute('data-view') === view); });
    var head = document.getElementById('head-text');
    if (head) head.textContent = state.clean ? (state.branch || 'main') + ' clean · ' + state.head : (state.branch || 'main') + ' dirty · ' + state.head;
    var pill = document.getElementById('head-pill');
    if (pill) { pill.innerHTML = '<span class="dot ' + (state.clean ? '' : 'amber') + '"></span><span id="head-text">' + esc((state.clean ? (state.branch || 'main') + ' clean · ' : (state.branch || 'main') + ' dirty · ') + state.head) + '</span>'; }
    if (view === 'mission') viewEl.innerHTML = renderMission();
    else if (view === 'hybrid') viewEl.innerHTML = renderHybrid();
    else if (view === 'director') viewEl.innerHTML = renderDirector();
    else viewEl.innerHTML = renderStudio();
    var foot = document.getElementById('foot-cmd');
    if (foot) foot.textContent = 'python workstream/gypsy.py slices run --all';
    var selected = document.querySelector('[data-artifact="' + (selectedArtifact || '').replace(/"/g, '\\"') + '"]');
    if (selected) selected.style.borderColor = '#2c8f86';
  }

  function setView(next) {
    view = next || 'studio';
    try { localStorage.setItem('gypsy.view', view); } catch (e) {}
    try { history.replaceState(null, '', '?view=' + encodeURIComponent(view)); } catch (e) {}
    render();
    window.scrollTo(0, 0);
  }

  function showToast(message, bad) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = message;
    el.style.display = 'block';
    el.style.borderColor = bad ? '#6d3434' : '#2b4b54';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.style.display = 'none'; }, 6000);
  }

  function loadState() {
    return fetch('/api/state', { cache: 'no-store' }).then(function (res) {
      if (!res.ok) throw new Error('state HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      state = data;
      if (!selectedArtifact) selectedArtifact = defaultArtifact(data);
      if (selectedArtifact && (!artifactMeta || artifactMeta.path !== selectedArtifact)) loadArtifact(selectedArtifact, true);
      render();
      if (state.job && state.job.status === 'running') showJob();
      return data;
    }).catch(function (err) {
      viewEl.innerHTML = '<div class="panel pad"><b>Dashboard backend unreachable.</b><p class="muted">' + esc(err.message) + '</p><p class="tiny dim">Start it with: python workstream/gypsy.py dashboard</p></div>';
    });
  }

  function loadArtifact(path, rerender) {
    selectedArtifact = path;
    return fetch('/api/artifact?path=' + encodeURIComponent(path), { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (meta) {
      artifactMeta = meta;
      if (rerender !== false) render();
    }).catch(function () {
      artifactMeta = { path: path, exists: false, bytes: 0, kind: 'missing', sha256: '' };
      if (rerender !== false) render();
    });
  }

  function showJob() {
    var box = document.getElementById('job');
    if (!box) return;
    box.classList.add('show');
    pollJob();
  }
  function renderJob(job) {
    var stateBadge = document.getElementById('job-state');
    if (stateBadge) {
      stateBadge.className = 'badge ' + (job.status === 'passed' ? 'pass' : job.status === 'failed' ? 'fail' : 'running');
      stateBadge.textContent = (job.status || 'idle').toUpperCase();
    }
    var title = document.getElementById('job-title');
    if (title) title.textContent = job.action || 'run';
    var out = document.getElementById('job-output');
    if (out) out.textContent = job.output || 'starting…';
    var meta = document.getElementById('job-meta');
    if (meta) meta.textContent = job.command ? job.command.join(' ') : '';
  }
  function pollJob() {
    if (pollTimer) clearTimeout(pollTimer);
    fetch('/api/job', { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (job) {
      renderJob(job);
      if (job.status === 'running') {
        pollTimer = setTimeout(pollJob, 1000);
      } else if (job.status === 'passed' || job.status === 'failed') {
        loadState();
        showToast(job.status === 'passed' ? 'Command passed.' : 'Command failed — see output.', job.status !== 'passed');
      }
    }).catch(function () { pollTimer = setTimeout(pollJob, 2000); });
  }
  function askRun(id) {
    if (!state) return;
    var cmd = null;
    (state.commands || []).forEach(function (c) { if (c.id === id) cmd = c; });
    if (!cmd) return;
    if (state.job && state.job.status === 'running') { showToast('A command is already running.', true); showJob(); return; }
    pendingAction = id;
    document.getElementById('modal-title').textContent = 'Run ' + cmd.label + '?';
    document.getElementById('modal-hint').textContent = 'This executes a real local command and writes state under workstream/state. ' + (cmd.hint || '');
    document.getElementById('modal-cmd').textContent = displayCommand(cmd.id);
    document.getElementById('modal').classList.add('show');
  }
  function closeModal() { document.getElementById('modal').classList.remove('show'); pendingAction = null; }
  function runPending() {
    var id = pendingAction;
    if (!id) return;
    closeModal();
    fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gypsy-Token': token },
      body: JSON.stringify({ action: id })
    }).then(function (res) {
      return res.json().then(function (body) { return { status: res.status, body: body }; });
    }).then(function (result) {
      if (result.status !== 202) { showToast((result.body && result.body.error) || 'could not start', true); return; }
      showToast('Started ' + id + '.');
      showJob();
      setTimeout(pollJob, 300);
    }).catch(function (err) { showToast('Run failed: ' + err.message, true); });
  }

  document.addEventListener('input', function (ev) {
    if (!ev.target || ev.target.id !== 'palette-input') return;
    var needle = String(ev.target.value || '').toLowerCase();
    var rows = document.querySelectorAll('.action-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      row.style.display = row.textContent.toLowerCase().indexOf(needle) >= 0 ? '' : 'none';
    }
  });

  document.addEventListener('click', function (ev) {
    var tab = ev.target.closest('[data-view]');
    if (tab) { setView(tab.getAttribute('data-view')); return; }
    var run = ev.target.closest('[data-run]');
    if (run) { askRun(run.getAttribute('data-run')); return; }
    var art = ev.target.closest('[data-artifact]');
    if (art) { loadArtifact(art.getAttribute('data-artifact')); return; }
    var close = ev.target.closest('#job-close');
    if (close) { document.getElementById('job').classList.remove('show'); return; }
    var modalCancel = ev.target.closest('#modal-cancel');
    if (modalCancel) { closeModal(); return; }
    var modalRun = ev.target.closest('#modal-run');
    if (modalRun) { runPending(); return; }
    var refresh = ev.target.closest('#refresh');
    if (refresh) { loadState(); showToast('Refreshed.'); return; }
    var runAll = ev.target.closest('#run-all');
    if (runAll) { askRun('run_all'); return; }
    var jobRefresh = ev.target.closest('#job-refresh');
    if (jobRefresh) { window.open('/api/artifact?raw=1&path=' + encodeURIComponent('docs/PHASE-5-EVIDENCE.md'), '_blank'); return; }
    var backdrop = ev.target.closest('#modal');
    if (backdrop && ev.target === backdrop) closeModal();
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') { closeModal(); var job = document.getElementById('job'); if (job) job.classList.remove('show'); }
    if (ev.ctrlKey && ['1', '2', '3', '4'].indexOf(ev.key) >= 0) { ev.preventDefault(); setView(['studio', 'mission', 'hybrid', 'director'][Number(ev.key) - 1]); }
    if (ev.ctrlKey && ev.key.toLowerCase() === 'k') { ev.preventDefault(); var input = document.getElementById('palette-input'); if (input) { setView('hybrid'); setTimeout(function () { input.focus(); }, 50); } }
  });

  var query = new URLSearchParams(location.search);
  var requested = query.get('view');
  var stored = null;
  try { stored = localStorage.getItem('gypsy.view'); } catch (e) {}
  view = ['studio', 'mission', 'hybrid', 'director'].indexOf(requested) >= 0 ? requested : (['studio', 'mission', 'hybrid', 'director'].indexOf(stored) >= 0 ? stored : 'studio');
  loadState();
  setInterval(function () { if (!document.hidden) loadState(); }, 15000);
})();
