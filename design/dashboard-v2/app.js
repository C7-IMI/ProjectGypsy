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
  function iconButton(label, id, primary) {
    return '<button class="btn small ' + (primary ? 'primary' : 'ghost') + '" data-run="' + esc(id) + '" title="' + esc(commandFor(id)) + '">' + esc(label) + '</button>';
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
    if (!entry) return '<div class="loading">No artifact selected.</div>';
    var isImage = /\.(png|jpe?g|webp)$/i.test(entry.path || '');
    var meta = artifactMeta && artifactMeta.path === entry.path ? artifactMeta : entry;
    var hash = meta.sha256 || entry.sha256 || '';
    var image = isImage ? '<img src="' + esc(previewUrl(entry.path)) + '" alt="">' : '<span class="cap">' + esc(meta.kind || 'file') + '</span>';
    return '<div class="art" style="height:' + (compact ? '112' : '132') + 'px">' + image + '</div>' +
      '<div class="kv"><div class="k">path</div><div class="v">' + esc(entry.path) + '</div>' +
      '<div class="k">size</div><div class="v">' + esc(bytes(entry.bytes)) + '</div>' +
      '<div class="k">sha256</div><div class="v" title="' + esc(hash) + '">' + esc((hash || '—').slice(0, 12)) + '…' + esc((hash || '').slice(-6)) + '</div>' +
      '<div class="k">kind</div><div class="v">' + esc(entry.kind || 'file') + '</div></div>' +
      '<div class="artfoot"><button class="btn small ghost" data-artifact="' + esc(entry.path) + '">Refresh</button><button class="btn small" data-copy="' + esc(hash) + '">Copy hash</button></div>';
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
      '<div style="margin-top:7px;font-size:8.5px;color:#627986;line-height:1.45">No approval queue. Gates are automated; evidence is the review surface.</div>';
  }
  function railMarkup() {
    return '<aside class="rail">' +
      '<div class="label">Workspace</div><button class="nav active" data-view="overview"><span class="i"></span>Overview</button>' +
      '<button class="nav" data-view="run"><span class="i"></span>Runs<span class="count">' + ((state.runs || []).length) + '</span></button>' +
      '<button class="nav" data-scroll="pipeline"><span class="i"></span>Slices<span class="count">' + (state.metrics.slicesTotal || 0) + '</span></button>' +
      '<button class="nav" data-scroll="artifacts"><span class="i"></span>Artifacts<span class="count">' + (state.artifacts || []).length + '</span></button>' +
      '<div class="label">Quality</div><button class="nav" data-view="run"><span class="i"></span>Gates<span class="count">' + (state.metrics.blocked || 0) + '</span></button>' +
      '<button class="nav" data-scroll="pipeline"><span class="i"></span>Toolpacks<span class="count">4</span></button>' +
      '<a class="nav" href="/classic" style="text-decoration:none"><span class="i"></span>Classic views</a>' +
      '<div class="spacer"></div><div class="palette"><div class="k"><span>COMMAND PALETTE</span><span>⌘ K</span></div><div class="v">slices run --all</div></div>' +
      '<div style="font-size:9px;color:#526a77;line-height:1.5;padding:8px 4px 0">The CLI is the source of truth.<br>Every UI action is a named command.</div></aside>';
  }
  function nextActionMarkup() {
    var gate = (state.gates || []).filter(function (g) { return g.status === 'untested'; })[0];
    if (!gate) gate = (state.gates || []).filter(function (g) { return g.status === 'blocked'; })[0];
    if (!gate) return '';
    var action = gate.id === 'device' ? 'How to unblock' : 'Open evidence';
    return '<div class="next"><div class="icon">!</div><div class="txt"><div class="eyebrow">Next best action</div><h3>' + esc(gate.label) + ' needs attention</h3><p>' + esc(gate.detail) + '</p></div><div class="actions"><button class="btn small ghost">' + esc(action) + '</button>' + (gate.id === 'device' ? '<button class="btn small">Connect device</button>' : '') + '</div></div>';
  }
  function metricCard(label, value, sub, badgeText) {
    return '<div class="metric"><div class="top"><span>' + esc(label) + '</span><span class="status pass">' + esc(badgeText || '') + '</span></div><div class="v">' + esc(value) + '</div><div class="s">' + esc(sub) + '</div></div>';
  }
  function stageMarkup(item) {
    var status = item.passed ? 'passed' : 'failed';
    var stepText = item.steps && typeof item.steps === 'object' ? (item.steps.passed + '/' + item.steps.total + ' steps') : (typeof item.steps === 'number' ? item.steps + ' steps' : '— steps');
    return '<div class="stage clickable" data-run-id="' + esc(item.statePath || '') + '" data-stage-id="' + esc(item.id) + '"><div class="r">' + dot(status) + '<span class="n">' + esc(item.id) + '</span><span class="time">' + esc(secs(item.seconds)) + '</span></div><div class="sub">' + esc((item.detail || []).join(' → ') || 'slice') + '</div><div class="bar"><i></i></div><div class="foot"><span>' + esc(stepText) + '</span><span>' + esc(item.artifacts || 0) + ' artifacts</span></div></div>';
  }
  function runRow(run) {
    return '<tr data-run-id="' + esc(run.id) + '"><td class="runname">' + esc(String(run.title || '').slice(0, 22)) + '</td><td>' + esc(run.kind === 'toolpack' ? 'toolpack' : 'all gates') + '</td><td><span class="status ' + (run.passed ? 'pass' : 'fail') + '">● ' + statusText(run.status) + '</span></td><td class="t-mono">' + esc(secs(run.durationSeconds)) + '</td><td class="t-mono">' + esc(shortTime(run.startedAt)) + '</td><td class="t-mono">' + esc(run.artifactCount || 0) + '</td><td class="rowactions">Open →</td></tr>';
  }
  function renderOverview() {
    shell.className = 'body';
    var s = state;
    var next = nextActionMarkup();
    var pipeline = (s.slices || []).map(stageMarkup).join('');
    var runs = (s.runs || []).filter(function (r) { return !searchQuery || ((r.title || '') + ' ' + (r.kind || '')).toLowerCase().indexOf(searchQuery.toLowerCase()) >= 0; }).slice(0, 6);
    var rows = runs.map(runRow).join('');
    var artifactCards = (s.artifacts || []).slice(0, 4).map(function (a) {
      var isImage = /\.(png|jpe?g|webp)$/i.test(a.path || '');
      return '<div class="ev clickable" data-artifact="' + esc(a.path) + '"><div class="thumb">' + (isImage ? '<img src="' + esc(previewUrl(a.path)) + '" alt="">' : esc(a.kind || 'file')) + '</div><div class="n">' + esc(a.path.split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + '</div></div>';
    }).join('');
    shell.innerHTML = railMarkup() +
      '<main class="main"><div class="head"><div><h1>Workspace overview</h1><p>' + esc(s.metrics.slicesTotal) + ' slices · last run ' + (s.taskPassed ? 'passed' : 'not complete') + ' · ' + esc((s.metrics.blocked || 0) + (s.metrics.untested || 0)) + ' gates need attention</p></div><div class="actions"><button class="btn ghost" data-view="run">View last run</button><button class="btn primary" data-run="run_all">Run all</button></div></div>' +
      next +
      '<div class="metrics">' + metricCard('Slices passed', (s.metrics.slicesPassed || 0) + ' / ' + (s.metrics.slicesTotal || 0), 'latest task', '● PASS') + metricCard('Tests', s.metrics.tests || '—', 'workstream suite', '● PASS') + metricCard('Capabilities', s.metrics.capabilities || '—', 'manifests valid', '') + metricCard('Blocking defects', '0', ((s.metrics.blocked || 0) + (s.metrics.untested || 0)) + ' gates need attention', '') + '</div>' +
      '<div class="section" id="overview-pipeline"><div class="section-h"><h2>Pipeline</h2><span class="sub">left to right · click a stage to inspect</span><span class="right">' + ((s.slices || []).every(function (x) { return x.passed; }) ? 'All declared slices passed' : 'Some slices need attention') + '</span></div><div class="pipeline">' + pipeline + '</div></div>' +
      '<div class="runs"><div class="runs-h"><b>Recent runs</b><span>last ' + runs.length + '</span><div class="run-filters" style="margin-left:auto"><span class="filter on">All</span><span class="filter">Passed</span><span class="filter">Failed</span></div></div><table class="run-table"><thead><tr><th>Run</th><th>Scope</th><th>Status</th><th>Duration</th><th>Started</th><th>Artifacts</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<div class="bottomgrid" id="overview-artifacts"><div class="runs"><div class="runs-h"><b>Recent artifacts</b><span>hashed · local</span></div><div class="evidence-grid">' + artifactCards + '</div></div>' +
      '<div class="runs"><div class="runs-h"><b>Readiness checklist</b><span>6 checks</span></div><div class="checklist">' +
      '<div class="check"><span class="d"></span><span class="k">Workstream checks</span><span class="v">6/6 PASS</span></div>' +
      '<div class="check"><span class="d"></span><span class="k">Android debug package</span><span class="v">PASS</span></div>' +
      '<div class="check"><span class="d"></span><span class="k">Second engine · LeftBehind</span><span class="v">PASS</span></div>' +
      '<div class="check"><span class="d amber"></span><span class="k">Device launch</span><span class="v">UNTESTED</span></div>' +
      '<div class="check"><span class="d red"></span><span class="k">Phase 6 · UE5</span><span class="v">BLOCKED</span></div></div></div></div>' +
      '</main><aside class="right"><div class="rpanel"><div class="rpanel-h"><b>Selected artifact</b><span class="right">LIVE HASH</span></div><div class="rpad">' + artifactPanel() + '</div></div><div class="rpanel"><div class="rpanel-h"><b>Gates</b><span class="right">HONEST STATE</span></div><div class="rpad">' + gatesMarkup() + '</div></div></aside>';
  }
  function nextRunActionId(stepId) {
    if (!detail) return 'run_all';
    var title = String(detail.title || '').toLowerCase();
    var step = String(stepId || '').toLowerCase();
    if (title.indexOf('leftbehind') >= 0 && ['build','demo','capture'].indexOf(step) >= 0) return 'leftbehind_' + step;
    if (title.indexOf('leftbehind') >= 0) return 'leftbehind';
    return 'run_all';
  }
  function renderRun() {
    shell.className = 'body detail-body';
    if (!detail) { shell.innerHTML = '<div class="loading">Select a run from the overview.</div>'; return; }
    var steps = detail.steps || [];
    var stepHtml = steps.map(function (step, index) {
      return '<div class="step ' + (index === 0 ? 'active' : '') + '"><div class="track"><span class="circle">' + (step.status === 'passed' ? '✓' : '!') + '</span>' + (index < steps.length - 1 ? '<span class="line"></span>' : '') + '</div><div class="sbody"><b>' + esc(step.id) + '</b><div class="s">' + esc(step.status) + '</div><div class="time">' + esc(secs(step.seconds)) + ' · ' + statusText(step.status) + '</div></div></div>';
    }).join('');
    var log = steps.map(function (step) { return '[step] ' + step.id + ' · ' + step.status + '\n' + (step.output || step.error || ''); }).join('\n');
    var validators = (detail.validators || []).map(function (v) {
      return '<tr><td class="runname">' + esc(v.id) + '</td><td>' + esc(v.artifact || v.target || '') + '</td><td><span class="status ' + (v.passed ? 'pass' : 'fail') + '">● ' + (v.passed ? 'PASS' : 'FAIL') + '</span></td><td class="t-mono">' + esc(v.kind || '') + '</td></tr>';
    }).join('');
    var artifactRows = (detail.artifacts || []).slice(0, 5).map(function (a) {
      return '<div class="ditem"><div class="n">' + esc((a.path || '').split('/').pop()) + '</div><div class="s">' + esc(bytes(a.bytes)) + '</div></div>';
    }).join('');
    var primaryAction = String(detail.title || '').toLowerCase().indexOf('leftbehind') >= 0 ? 'leftbehind' : 'run_all';
    var actions = steps.map(function (step) {
      var actionId = nextRunActionId(step.id);
      return '<button class="btn small" data-run="' + esc(actionId) + '">Retry ' + esc(step.id) + '</button>';
    }).slice(0, 3).join('');
    shell.innerHTML = '<aside class="steprail"><div class="runmeta"><div class="k">Run</div><div class="v">' + esc(detail.title) + '</div><div style="height:6px"></div><div class="k">started / duration</div><div class="v">' + esc(shortTime(detail.startedAt)) + ' · ' + esc(secs(detail.durationSeconds)) + '</div><div style="height:6px"></div><div class="k">kind</div><div class="v">' + esc(detail.kind) + '</div></div><div style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:#546b79;margin:2px 2px 0">Steps</div><div class="steps">' + stepHtml + '</div><div style="margin-top:auto;border-top:1px solid #1a2c36;padding-top:9px;font-size:8.5px;color:#5d7481;line-height:1.5">A failed step stops later steps. Retry only the failed step from the run inspector.</div></aside>' +
      '<main class="detailmain"><div class="detailhead"><div><h1>' + esc(detail.title) + '</h1><p>' + esc(detail.command) + '</p></div><div class="actions"><button class="btn small ghost" data-view="overview">← Runs</button><button class="btn small" data-run="' + esc(primaryAction) + '">Re-run</button></div></div>' +
      '<div class="runsummary"><div class="sum"><div class="k">Status</div><div class="v" style="color:' + (detail.passed ? 'var(--green)' : 'var(--red)') + '">' + statusText(detail.status) + '</div><div class="s">' + (detail.passed ? 'exit 0' : 'needs attention') + '</div></div><div class="sum"><div class="k">Steps</div><div class="v">' + steps.length + '</div><div class="s">' + steps.filter(function (x) { return x.status === 'passed'; }).length + ' passed</div></div><div class="sum"><div class="k">Artifacts</div><div class="v">' + (detail.artifacts || []).length + '</div><div class="s">hashed</div></div><div class="sum"><div class="k">Validators</div><div class="v" style="color:var(--green)">' + (detail.validators || []).length + '</div><div class="s">all checked</div></div></div>' +
      '<div class="tabs"><b>Logs</b><span>Overview</span><span>Artifacts</span></div><div class="logbox"><div class="loghead"><span style="color:var(--green)">●</span> ' + esc(detail.title) + ' <span class="right">READ ONLY</span></div><div class="log">' + esc(log) + '</div></div>' +
      '<div class="recovery"><div class="recover"><b>If a step fails</b><p>Read the failed step output, then retry only that step. Later steps are skipped, not silently passed.</p><button class="btn small ghost" data-run="' + esc(primaryAction) + '">Retry run</button></div><div class="recover"><b>Reproduce locally</b><p>Every action shows its argv before running. Copy the command or run it from the terminal.</p><button class="btn small ghost">Copy command</button></div></div>' +
      (validators ? '<div class="runs validators"><div class="runs-h"><b>Validator evidence</b><span>this run</span></div><table><thead><tr><th>Check</th><th>Artifact</th><th>Result</th><th>Kind</th></tr></thead><tbody>' + validators + '</tbody></table></div>' : '') +
      '</main><aside class="detailright"><div class="rpanel"><div class="rpanel-h"><b>Step artifacts</b><span class="right">HASHED</span></div><div class="rpad">' + artifactPanel(true) + '</div></div><div class="rpanel"><div class="rpanel-h"><b>Step actions</b><span class="right">WHITELISTED</span></div><div class="rpad" style="display:flex;flex-direction:column;gap:5px">' + actions + '<button class="btn small ghost" data-run="run_all">Re-run all gates</button><div style="font-size:8.5px;color:#627986;line-height:1.45;margin-top:3px">Re-running writes a new state record; it never edits the old one.</div></div></div><div class="rpanel"><div class="rpanel-h"><b>Artifacts</b><span class="right">' + (detail.artifacts || []).length + '</span></div><div class="rpad"><div class="diffgrid">' + artifactRows + '</div></div></div></aside>';
  }
  function render() {
    if (!state) return;
    document.querySelectorAll('.tab').forEach(function (tab) { tab.classList.toggle('active', tab.getAttribute('data-view') === view); });
    if (view === 'run') renderRun(); else renderOverview();
  }
  function loadState() {
    return fetch('/api/state', { cache: 'no-store' }).then(function (res) { if (!res.ok) throw new Error('state HTTP ' + res.status); return res.json(); }).then(function (data) {
      state = data;
      if (!selectedArtifact) selectedArtifact = defaultArtifact();
      if (selectedArtifact && (!artifactMeta || artifactMeta.path !== selectedArtifact)) loadArtifact(selectedArtifact, true);
      if (view === 'run' && !detail) {
        var first = (state.runs || [])[0];
        if (first) return loadRun(first.id).then(render);
      }
      render();
    }).catch(function (err) { shell.innerHTML = '<div class="err">Dashboard backend unreachable: ' + esc(err.message) + '</div>'; });
  }
  function loadRun(id) {
    selectedRunId = id;
    return fetch('/api/run?id=' + encodeURIComponent(id), { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (data) {
      detail = data;
      selectedArtifact = defaultArtifact();
      render();
    }).catch(function (err) { shell.innerHTML = '<div class="err">Could not load run: ' + esc(err.message) + '</div>'; });
  }
  function openRun(id) {
    view = 'run';
    detail = null;
    loadRun(id).then(function () { render(); });
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
  }
  function runPending() {
    var action = pendingAction;
    if (!action) return;
    document.getElementById('modal').classList.remove('show');
    pendingAction = null;
    fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Gypsy-Token': token }, body: JSON.stringify({ action: action }) }).then(function (res) { return res.json().then(function (body) { return { status: res.status, body: body }; }); }).then(function (result) {
      if (result.status !== 202) { showToast((result.body && result.body.error) || 'Could not start', true); return; }
      showJob(); setTimeout(pollJob, 300);
    }).catch(function (err) { showToast('Run failed: ' + err.message, true); });
  }
  function showJob() { document.getElementById('job').classList.add('show'); pollJob(); }
  function pollJob() {
    if (pollTimer) clearTimeout(pollTimer);
    fetch('/api/job', { cache: 'no-store' }).then(function (res) { return res.json(); }).then(function (job) {
      document.getElementById('job-state').textContent = (job.status || 'idle').toUpperCase();
      document.getElementById('job-state').className = 'status ' + (job.status === 'passed' ? 'pass' : job.status === 'failed' ? 'fail' : 'warn');
      document.getElementById('job-title').textContent = job.action || 'run';
      document.getElementById('job-output').textContent = job.output || 'starting…';
      document.getElementById('job-meta').textContent = job.command ? job.command.join(' ') : '';
      if (job.status === 'running') pollTimer = setTimeout(pollJob, 1000);
      else if (job.status === 'passed' || job.status === 'failed') {
        loadState();
        if (view === 'run' && selectedRunId) loadRun(selectedRunId);
        showToast(job.status === 'passed' ? 'Command passed.' : 'Command failed — see output.', job.status !== 'passed');
      }
    }).catch(function () { pollTimer = setTimeout(pollJob, 2000); });
  }
  function showToast(message, bad) {
    var el = document.getElementById('toast'); el.textContent = message; el.style.display = 'block'; el.style.borderColor = bad ? '#6d3434' : '#2b4b54';
    if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.style.display = 'none'; }, 6000);
  }
  function setView(next) {
    view = next;
    if (view === 'run' && !selectedRunId) {
      var first = state && state.runs && state.runs[0]; if (first) selectedRunId = first.id;
    }
    if (view === 'run' && selectedRunId) loadRun(selectedRunId); else render();
    try { history.replaceState(null, '', '?view=' + view); } catch (e) {}
  }
  document.addEventListener('click', function (ev) {
    var tab = ev.target.closest('[data-view]'); if (tab) { ev.preventDefault(); setView(tab.getAttribute('data-view')); return; }
    var stage = ev.target.closest('[data-stage-id]'); if (stage && !stage.getAttribute('data-run-id')) { var stageId = stage.getAttribute('data-stage-id'); var match = (state.runs || []).filter(function (r) { return String(r.title || '').toLowerCase().indexOf(stageId.toLowerCase()) >= 0; })[0]; if (match) { openRun(match.id); } else { showToast('No recorded run for this stage yet.', false); } return; }
    var runId = ev.target.closest('[data-run-id]'); if (runId) { openRun(runId.getAttribute('data-run-id')); return; }
    var run = ev.target.closest('[data-run]'); if (run) { showModal(run.getAttribute('data-run')); return; }
    var art = ev.target.closest('[data-artifact]'); if (art) { loadArtifact(art.getAttribute('data-artifact')); return; }
    var help = ev.target.closest('[data-help]'); if (help) { var kind = help.getAttribute('data-help'); showToast(kind === 'device-connect' ? 'No device or emulator is attached. Install an Android emulator or connect a device, then re-run mobile.' : 'Device launch is untested. The APK is signed and ready; attach a device or emulator to run it.', false); return; }
    var scroll = ev.target.closest('[data-scroll]'); if (scroll) { if (view !== 'overview') { setView('overview'); } setTimeout(function () { var target = document.getElementById('overview-' + scroll.getAttribute('data-scroll')); if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 60); return; }
    var copy = ev.target.closest('[data-copy]'); if (copy) { var text = copy.getAttribute('data-copy') || ''; if (text && navigator.clipboard) { navigator.clipboard.writeText(text).then(function () { showToast('Copied.', false); }).catch(function () { showToast('Copy failed; select the text manually.', true); }); } else { showToast(text || 'Nothing to copy.', !text); } return; }
    if (ev.target.closest('#modal-cancel') || ev.target.id === 'modal') { document.getElementById('modal').classList.remove('show'); return; }
    if (ev.target.closest('#modal-run')) { runPending(); return; }
    if (ev.target.closest('#job-close')) { document.getElementById('job').classList.remove('show'); return; }
    if (ev.target.closest('#refresh')) { loadState(); return; }
    if (ev.target.closest('#run-all')) { showModal('run_all'); return; }
  });
  var searchInput = document.getElementById('search');
  if (searchInput) searchInput.addEventListener('input', function () { searchQuery = searchInput.value.trim(); if (view === 'overview') render(); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') { document.getElementById('modal').classList.remove('show'); document.getElementById('job').classList.remove('show'); }
    if (ev.ctrlKey && ev.key.toLowerCase() === 'k') { ev.preventDefault(); var input = document.getElementById('search'); if (input) input.focus(); }
  });
  var query = new URLSearchParams(location.search);
  view = query.get('view') === 'run' ? 'run' : 'overview';
  loadState();
  setInterval(function () { if (!document.hidden) loadState(); }, 15000);
})();
