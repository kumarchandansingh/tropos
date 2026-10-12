"""Embedded local product shell for the first Tropos web vertical slice."""

TROPOS_WEB_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tropos</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-2: #f9fafb;
      --text: #17191d;
      --muted: #68707c;
      --line: #e5e7eb;
      --accent: #2857d9;
      --accent-soft: #eef3ff;
      --success: #177245;
      --warn: #9a5b00;
      --danger: #b42318;
      --shadow: 0 12px 32px rgba(18, 24, 40, 0.08);
      --radius: 14px;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    button, input, textarea { font: inherit; }
    button { cursor: pointer; }

    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 248px 1fr;
    }

    .sidebar {
      background: #15171b;
      color: #f8fafc;
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 28px;
    }

    .brand {
      display: flex;
      gap: 10px;
      align-items: center;
      padding: 0 10px;
      font-weight: 750;
      letter-spacing: -0.02em;
    }
    .brand-mark {
      width: 30px;
      height: 30px;
      border-radius: 9px;
      background: linear-gradient(135deg, #6f8fff, #c7d2fe);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.22);
    }
    .nav-label {
      padding: 0 12px;
      color: #8f96a3;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .12em;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .nav {
      display: grid;
      gap: 4px;
    }
    .nav button {
      border: 0;
      background: transparent;
      color: #c9ced7;
      border-radius: 9px;
      text-align: left;
      padding: 10px 12px;
    }
    .nav button:hover { background: #20232a; color: #fff; }
    .nav button.active { background: #272b33; color: #fff; }
    .sidebar-foot {
      margin-top: auto;
      border-top: 1px solid #2a2e36;
      padding: 16px 10px 0;
      font-size: 12px;
      color: #969daa;
      line-height: 1.5;
    }

    .main {
      min-width: 0;
      padding: 32px 40px 56px;
    }
    .page {
      max-width: 1180px;
      margin: 0 auto;
    }
    .eyebrow {
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: 8px;
    }
    h1 {
      font-size: 30px;
      line-height: 1.15;
      margin: 0;
      letter-spacing: -0.035em;
    }
    .subtitle {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.55;
      max-width: 760px;
    }

    .topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 28px;
    }
    .runtime-pill {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .dot {
      width: 8px; height: 8px; border-radius: 50%; background: #a0a7b4;
    }
    .dot.ready { background: #2da56a; }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(310px, .8fr);
      gap: 18px;
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 1px 2px rgba(16,24,40,.03);
    }
    .card-head {
      padding: 20px 22px 14px;
      border-bottom: 1px solid var(--line);
    }
    .card-head h2 {
      margin: 0;
      font-size: 16px;
      letter-spacing: -0.015em;
    }
    .card-head p {
      margin: 6px 0 0;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
    }
    .card-body { padding: 22px; }

    .dropzone {
      border: 1.5px dashed #cfd5df;
      border-radius: 12px;
      padding: 30px 22px;
      text-align: center;
      background: var(--panel-2);
      transition: .16s ease;
    }
    .dropzone.drag { border-color: var(--accent); background: var(--accent-soft); }
    .dropzone strong { display: block; margin-bottom: 6px; }
    .dropzone p { margin: 0 0 16px; color: var(--muted); font-size: 13px; }
    .file-name {
      display: none;
      margin-top: 14px;
      font-size: 13px;
      color: var(--muted);
    }
    .button {
      border: 1px solid #cfd5df;
      background: #fff;
      color: var(--text);
      border-radius: 9px;
      padding: 9px 13px;
      font-weight: 650;
      font-size: 13px;
    }
    .button:hover { background: #f7f8fa; }
    .button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    .button.primary:hover { filter: brightness(.97); }
    .button:disabled { opacity: .45; cursor: not-allowed; }

    .status-box {
      border-radius: 11px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      padding: 16px;
    }
    .status-title {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }
    .status-title strong { font-size: 13px; }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 750;
      background: #eef0f3;
      color: #58606c;
    }
    .badge.success { background: #e9f7ef; color: var(--success); }
    .badge.warn { background: #fff4df; color: var(--warn); }
    .badge.danger { background: #feeceb; color: var(--danger); }
    .badge.info { background: var(--accent-soft); color: var(--accent); }

    .meta {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin: 0;
      font-size: 12px;
    }
    .meta dt { color: var(--muted); }
    .meta dd { margin: 0; overflow-wrap: anywhere; }

    .resolve-wrap {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 18px;
      align-items: start;
    }
    .composer textarea {
      width: 100%;
      min-height: 112px;
      resize: vertical;
      border: 1px solid #cfd5df;
      border-radius: 11px;
      padding: 14px;
      outline: none;
      line-height: 1.5;
      background: #fff;
    }
    .composer textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(40,87,217,.10);
    }
    .composer-actions {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-top: 10px;
    }
    .hint { color: var(--muted); font-size: 12px; }

    .answer {
      padding: 22px;
    }
    .answer-empty {
      color: var(--muted);
      text-align: center;
      padding: 48px 24px;
      font-size: 13px;
      line-height: 1.55;
    }
    .answer-text {
      margin: 0;
      font-size: 16px;
      line-height: 1.7;
    }
    .answer-meta {
      border-top: 1px solid var(--line);
      margin-top: 20px;
      padding-top: 14px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .side-stack { display: grid; gap: 18px; }
    .panel-list { display: grid; gap: 10px; }
    .evidence-item, .span-item {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      background: var(--panel-2);
    }
    .evidence-top, .span-top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      margin-bottom: 7px;
    }
    .evidence-item strong, .span-item strong { font-size: 12px; }
    .small { font-size: 11px; color: var(--muted); line-height: 1.45; overflow-wrap: anywhere; }
    .trace-button {
      border: 0;
      background: transparent;
      padding: 0;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .trace-button:hover { text-decoration: underline; }

    .notice {
      display: none;
      margin-bottom: 18px;
      border: 1px solid #f1c7c3;
      background: #fff5f4;
      color: #7a271a;
      border-radius: 10px;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.45;
    }

    .section { display: none; }
    .section.active { display: block; }

    .loading {
      display: inline-block;
      width: 14px; height: 14px;
      border-radius: 50%;
      border: 2px solid rgba(255,255,255,.45);
      border-top-color: #fff;
      animation: spin .7s linear infinite;
      vertical-align: -2px;
      margin-right: 6px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: static; padding: 16px; }
      .nav { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .sidebar-foot, .nav-label { display: none; }
      .main { padding: 24px 18px 40px; }
      .grid, .resolve-wrap { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><div class="brand-mark"></div><span>Tropos</span></div>
    <div>
      <div class="nav-label">Workspace</div>
      <nav class="nav">
        <button class="active" data-section="sources">Sources & Ingestion</button>
        <button data-section="resolve">Resolve</button>
      </nav>
    </div>
    <div class="sidebar-foot">
      Local product slice<br/>
      Governed knowledge · grounded answers
    </div>
  </aside>

  <main class="main">
    <div class="page">
      <div id="notice" class="notice"></div>

      <section id="sources" class="section active">
        <div class="topbar">
          <div>
            <div class="eyebrow">Knowledge operations</div>
            <h1>Sources & Ingestion</h1>
            <p class="subtitle">Add governed source material and see whether Tropos created new knowledge, detected no content change, or requires intervention.</p>
          </div>
          <div class="runtime-pill"><span id="runtime-dot" class="dot"></span><span id="runtime-text">Checking runtime…</span></div>
        </div>

        <div class="grid">
          <div class="card">
            <div class="card-head">
              <h2>Upload a file</h2>
              <p>Supported in this slice: TXT, Markdown, HTML and DOCX. Maximum 10 MB.</p>
            </div>
            <div class="card-body">
              <div id="dropzone" class="dropzone">
                <strong>Drop a knowledge file here</strong>
                <p>Tropos will parse, normalize, version, chunk and index it.</p>
                <input id="file-input" type="file" accept=".txt,.md,.markdown,.html,.htm,.xhtml,.docx" hidden />
                <button id="choose-file" class="button">Choose file</button>
                <div id="file-name" class="file-name"></div>
              </div>
              <div style="display:flex; justify-content:flex-end; margin-top:14px;">
                <button id="upload-file" class="button primary" disabled>Upload & ingest</button>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h2>Latest ingestion</h2>
              <p>The runtime outcome is shown directly; Tropos does not turn a no-change result into a fake new version.</p>
            </div>
            <div class="card-body">
              <div id="ingestion-empty" class="answer-empty" style="padding:28px 14px;">No file has been uploaded in this session.</div>
              <div id="ingestion-result" class="status-box" hidden>
                <div class="status-title">
                  <strong id="ingestion-filename">—</strong>
                  <span id="ingestion-badge" class="badge">—</span>
                </div>
                <dl class="meta">
                  <dt>Outcome</dt><dd id="ingestion-outcome">—</dd>
                  <dt>Reason</dt><dd id="ingestion-reason">—</dd>
                  <dt>Chunks</dt><dd id="ingestion-chunks">—</dd>
                  <dt>Knowledge ID</dt><dd id="ingestion-knowledge">—</dd>
                  <dt>Run ID</dt><dd id="ingestion-run">—</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="resolve" class="section">
        <div class="topbar">
          <div>
            <div class="eyebrow">Support workspace</div>
            <h1>Resolve</h1>
            <p class="subtitle">Ask against governed Tropos knowledge. The runtime either returns a grounded answer with evidence or explicitly abstains.</p>
          </div>
          <div class="runtime-pill"><span class="dot ready"></span><span>Grounded mode</span></div>
        </div>

        <div class="resolve-wrap">
          <div>
            <div class="card composer">
              <div class="card-head">
                <h2>Ask a question</h2>
                <p>No unrestricted world-knowledge fallback in this slice.</p>
              </div>
              <div class="card-body">
                <textarea id="query" placeholder="What should I do after rotating the device certificate?"></textarea>
                <div class="composer-actions">
                  <span class="hint">Uses permission-aware BM25 retrieval → sufficiency → grounded generation.</span>
                  <button id="ask" class="button primary">Resolve</button>
                </div>
              </div>
            </div>

            <div class="card" style="margin-top:18px;">
              <div class="card-head">
                <h2>Answer</h2>
                <p id="answer-caption">Waiting for a question.</p>
              </div>
              <div class="answer">
                <div id="answer-empty" class="answer-empty">Ask a question to see the runtime decision, grounded answer and citations.</div>
                <div id="answer-result" hidden>
                  <p id="answer-text" class="answer-text"></p>
                  <div id="answer-meta" class="answer-meta"></div>
                </div>
              </div>
            </div>
          </div>

          <div class="side-stack">
            <div class="card">
              <div class="card-head">
                <h2>Evidence</h2>
                <p>Only evidence admitted to generation appears here.</p>
              </div>
              <div class="card-body">
                <div id="evidence-empty" class="answer-empty" style="padding:20px 8px;">No evidence selected yet.</div>
                <div id="evidence-list" class="panel-list"></div>
              </div>
            </div>

            <div class="card">
              <div class="card-head">
                <h2>Decision & trace</h2>
                <p>Sufficiency remains visibly unvalidated until human calibration is complete.</p>
              </div>
              <div class="card-body">
                <div id="decision-empty" class="answer-empty" style="padding:20px 8px;">No runtime decision yet.</div>
                <div id="decision-result" hidden>
                  <div class="status-box">
                    <div class="status-title">
                      <strong>Evidence assessment</strong>
                      <span id="decision-label" class="badge">—</span>
                    </div>
                    <dl class="meta" style="grid-template-columns:110px 1fr;">
                      <dt>Validation</dt><dd id="decision-validation">—</dd>
                      <dt>Failure type</dt><dd id="decision-failure">—</dd>
                      <dt>Trace</dt><dd><button id="load-trace" class="trace-button">Open trace</button></dd>
                    </dl>
                  </div>
                  <div id="trace-list" class="panel-list" style="margin-top:12px;"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </main>
</div>

<script>
(() => {
  const state = { file: null, traceId: null };

  const el = id => document.getElementById(id);
  const showError = message => {
    el('notice').textContent = message;
    el('notice').style.display = 'block';
  };
  const clearError = () => { el('notice').style.display = 'none'; };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  document.querySelectorAll('.nav button').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('active', b === button));
      document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === button.dataset.section));
    });
  });

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || ('Request failed: ' + response.status));
    return data;
  }

  api('/api/health').then(data => {
    el('runtime-dot').classList.add('ready');
    el('runtime-text').textContent = data.model_configured
      ? data.model + ' · ' + data.retrieval
      : 'Model not configured';
  }).catch(() => { el('runtime-text').textContent = 'Runtime unavailable'; });

  const fileInput = el('file-input');
  const dropzone = el('dropzone');
  const choose = el('choose-file');
  const upload = el('upload-file');

  function selectFile(file) {
    state.file = file || null;
    el('file-name').style.display = file ? 'block' : 'none';
    el('file-name').textContent = file ? file.name + ' · ' + Math.max(1, Math.round(file.size / 1024)) + ' KB' : '';
    upload.disabled = !file;
  }

  choose.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => selectFile(fileInput.files[0]));
  ['dragenter','dragover'].forEach(name => dropzone.addEventListener(name, event => {
    event.preventDefault(); dropzone.classList.add('drag');
  }));
  ['dragleave','drop'].forEach(name => dropzone.addEventListener(name, event => {
    event.preventDefault(); dropzone.classList.remove('drag');
  }));
  dropzone.addEventListener('drop', event => selectFile(event.dataTransfer.files[0]));

  upload.addEventListener('click', async () => {
    if (!state.file) return;
    clearError();
    upload.disabled = true;
    const original = upload.textContent;
    upload.innerHTML = '<span class="loading"></span>Ingesting';
    try {
      const data = await api('/api/ingest?filename=' + encodeURIComponent(state.file.name), {
        method: 'POST',
        headers: {'Content-Type': state.file.type || 'application/octet-stream'},
        body: state.file
      });
      el('ingestion-empty').hidden = true;
      el('ingestion-result').hidden = false;
      el('ingestion-filename').textContent = data.filename;
      el('ingestion-outcome').textContent = data.outcome;
      el('ingestion-reason').textContent = data.reason;
      el('ingestion-chunks').textContent = data.chunks_written;
      el('ingestion-knowledge').textContent = data.knowledge_id;
      el('ingestion-run').textContent = data.run_id;
      const badge = el('ingestion-badge');
      badge.textContent = data.status.replaceAll('_', ' ');
      badge.className = 'badge ' + (data.status.startsWith('available') ? 'success' : 'warn');
    } catch (error) {
      showError(error.message);
    } finally {
      upload.disabled = false;
      upload.textContent = original;
    }
  });

  el('ask').addEventListener('click', async () => {
    const query = el('query').value.trim();
    if (!query) { showError('Enter a question first.'); return; }
    clearError();
    const button = el('ask');
    const original = button.textContent;
    button.disabled = true;
    button.innerHTML = '<span class="loading"></span>Resolving';
    try {
      const data = await api('/api/resolve', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({query})
      });
      state.traceId = data.trace_id;
      renderResolve(data);
    } catch (error) {
      showError(error.message);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  });

  function renderResolve(data) {
    el('answer-empty').hidden = true;
    el('answer-result').hidden = false;
    el('answer-caption').textContent = data.outcome === 'ANSWERED'
      ? 'Grounded answer returned.'
      : 'Tropos abstained rather than generating beyond the evidence.';
    el('answer-text').textContent = data.answer || ('Tropos abstained: ' + (data.abstention_reason || data.outcome));
    const meta = el('answer-meta');
    meta.innerHTML = '';
    [
      ['Outcome', data.outcome, data.outcome === 'ANSWERED' ? 'success' : 'warn'],
      ['Trace', data.trace_id, 'info']
    ].forEach(([label, value, cls]) => {
      const span = document.createElement('span');
      span.className = 'badge ' + cls;
      span.textContent = label + ': ' + value;
      meta.appendChild(span);
    });

    const evidence = data.evidence || [];
    el('evidence-empty').style.display = evidence.length ? 'none' : 'block';
    el('evidence-list').innerHTML = evidence.map(item => `
      <div class="evidence-item">
        <div class="evidence-top">
          <strong>${esc(item.alias)} · ${esc(item.title)}</strong>
          <span class="badge info">rank ${esc(item.rank ?? '—')}</span>
        </div>
        <div class="small">Score: ${esc(item.score ?? '—')}</div>
        <div class="small">${esc(item.locator)}</div>
      </div>`).join('');

    const decision = data.evidence_assessment;
    el('decision-empty').hidden = !!decision;
    el('decision-result').hidden = !decision;
    el('trace-list').innerHTML = '';
    if (decision) {
      const badge = el('decision-label');
      badge.textContent = decision.label;
      badge.className = 'badge ' + (decision.label === 'SUFFICIENT' ? 'success' : 'warn');
      el('decision-validation').textContent = decision.validation_status;
      el('decision-failure').textContent = decision.failure_type;
    }
  }

  el('load-trace').addEventListener('click', async () => {
    if (!state.traceId) return;
    clearError();
    try {
      const trace = await api('/api/traces/' + encodeURIComponent(state.traceId));
      el('trace-list').innerHTML = (trace.spans || []).map((span, index) => `
        <div class="span-item">
          <div class="span-top">
            <strong>${index + 1}. ${esc(span.name)}</strong>
            <span class="badge ${span.status === 'OK' ? 'success' : (span.status === 'ERROR' ? 'danger' : 'warn')}">${esc(span.status)}</span>
          </div>
          <div class="small">${esc(JSON.stringify(span.attributes))}</div>
        </div>`).join('');
    } catch (error) {
      showError(error.message);
    }
  });
})();
</script>
</body>
</html>
"""
