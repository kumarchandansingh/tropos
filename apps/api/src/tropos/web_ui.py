"""Embedded local product shell for Tropos operations UX."""

# ruff: noqa: E501

TROPOS_WEB_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tropos</title>
  <style>
    :root {
      --bg:#f4f6f8; --panel:#fff; --panel-2:#f9fafb; --text:#17191d; --muted:#68707c;
      --line:#e3e7ed; --line-strong:#ccd3dd; --accent:#2857d9; --accent-soft:#eef3ff;
      --success:#177245; --success-soft:#e9f7ef; --warn:#9a5b00; --warn-soft:#fff4df;
      --danger:#b42318; --danger-soft:#fff0ee; --dark:#15171b; --shadow:0 1px 2px rgba(16,24,40,.04);
      --radius:12px;
    }
    *{box-sizing:border-box} body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}
    button,input,textarea,select{font:inherit} button{cursor:pointer}.shell{min-height:100vh;display:grid;grid-template-columns:232px 1fr}
    .sidebar{background:var(--dark);color:#f8fafc;padding:22px 14px;display:flex;flex-direction:column;gap:24px}
    .brand{display:flex;align-items:center;gap:10px;padding:0 8px;font-weight:760}.brand-mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,#6688ff,#d7ddff)}
    .nav-label{padding:0 10px 7px;color:#8f96a3;font-size:10px;text-transform:uppercase;letter-spacing:.12em;font-weight:750}.nav{display:grid;gap:4px}
    .nav button{border:0;background:transparent;color:#c8ced7;border-radius:8px;text-align:left;padding:10px 11px;font-size:13px}.nav button:hover{background:#20232a;color:#fff}.nav button.active{background:#2a2e36;color:#fff}
    .sidebar-foot{margin-top:auto;border-top:1px solid #2a2e36;padding:14px 10px 0;color:#949ba7;font-size:11px;line-height:1.5}
    .main{min-width:0;padding:28px 34px 48px}.page{max-width:1440px;margin:0 auto}.section{display:none}.section.active{display:block}
    .topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:22px}.eyebrow{font-size:10px;color:var(--muted);font-weight:750;text-transform:uppercase;letter-spacing:.1em;margin-bottom:7px}
    h1{font-size:29px;line-height:1.15;margin:0;letter-spacing:-.03em}.subtitle{margin:7px 0 0;color:var(--muted);font-size:13px;line-height:1.5;max-width:780px}
    .runtime-pill{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:8px 11px;color:var(--muted);font-size:11px;white-space:nowrap}.dot{width:7px;height:7px;border-radius:50%;background:#a0a7b4}.dot.ready{background:#2da56a}
    .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.card-head{padding:16px 18px 13px;border-bottom:1px solid var(--line)}.card-head h2{margin:0;font-size:15px;letter-spacing:-.015em}.card-head p{margin:5px 0 0;font-size:12px;color:var(--muted);line-height:1.45}.card-body{padding:18px}
    .grid-2{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr);gap:16px;align-items:start}.resolve-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(380px,.65fr);gap:16px;align-items:start}.stack{display:grid;gap:16px}
    .dropzone{border:1.5px dashed var(--line-strong);border-radius:11px;padding:28px 20px;text-align:center;background:var(--panel-2);transition:.14s}.dropzone.drag{border-color:var(--accent);background:var(--accent-soft)}.dropzone strong{display:block;margin-bottom:5px}.dropzone p{margin:0 0 14px;color:var(--muted);font-size:12px}.file-name{display:none;margin-top:12px;color:var(--muted);font-size:12px}
    .button{border:1px solid var(--line-strong);background:#fff;color:var(--text);border-radius:8px;padding:8px 12px;font-weight:650;font-size:12px}.button:hover{background:#f7f8fa}.button.primary{border-color:var(--accent);background:var(--accent);color:#fff}.button.primary:hover{filter:brightness(.97)}.button:disabled{opacity:.48;cursor:not-allowed}
    .toolbar{display:flex;gap:10px;justify-content:space-between;align-items:center;flex-wrap:wrap}.toolbar-right{display:flex;gap:8px;align-items:center}.select{border:1px solid var(--line-strong);background:#fff;border-radius:8px;padding:7px 9px;font-size:12px;color:var(--text)}
    .status-card{border:1px solid var(--line);border-radius:10px;background:var(--panel-2);padding:14px}.status-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.status-title{font-size:13px;font-weight:720}.status-message{font-size:12px;color:var(--muted);line-height:1.5;margin-top:3px}
    .badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:760;background:#eef0f3;color:#58606c;white-space:nowrap}.badge.success{background:var(--success-soft);color:var(--success)}.badge.warn{background:var(--warn-soft);color:var(--warn)}.badge.danger{background:var(--danger-soft);color:var(--danger)}.badge.info{background:var(--accent-soft);color:var(--accent)}
    .meta{display:grid;grid-template-columns:120px 1fr;gap:7px 12px;margin:0;font-size:11px}.meta dt{color:var(--muted)}.meta dd{margin:0;overflow-wrap:anywhere}
    .activity{display:grid;gap:8px;margin-top:12px}.activity-row{display:grid;grid-template-columns:minmax(160px,1.5fr) 170px 110px 1fr;gap:10px;align-items:center;border-top:1px solid var(--line);padding-top:9px;font-size:11px}.activity-row:first-child{border-top:0;padding-top:0}.muted{color:var(--muted)}
    .inline-error{display:none;border:1px solid #efc3be;background:var(--danger-soft);border-radius:10px;padding:14px;margin-bottom:14px}.inline-error.show{display:block}.inline-error-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:6px}.inline-error strong{font-size:12px}.inline-error p{margin:0;color:#7a271a;font-size:12px;line-height:1.5}.error-meta{margin-top:8px;color:#9d3b30;font-size:10px}.retry{margin-top:10px}
    textarea{width:100%;min-height:108px;resize:vertical;border:1px solid var(--line-strong);border-radius:10px;padding:13px;outline:none;line-height:1.5;background:#fff}textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(40,87,217,.1)}.composer-actions{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:10px}.hint{font-size:11px;color:var(--muted)}
    .answer-empty{color:var(--muted);text-align:center;padding:36px 20px;font-size:12px;line-height:1.5}.answer-text{margin:0;font-size:15px;line-height:1.68}.answer-meta{border-top:1px solid var(--line);margin-top:16px;padding-top:12px;display:flex;gap:7px;flex-wrap:wrap}
    .explain{margin-top:14px;border:1px solid var(--line);background:var(--panel-2);border-radius:9px;padding:12px}.explain h3{font-size:11px;margin:0 0 6px}.explain p,.explain li{font-size:11px;color:var(--muted);line-height:1.5}.explain ul{margin:7px 0 0;padding-left:18px}
    .panel-list{display:grid;gap:9px}.evidence-item,.span-item{border:1px solid var(--line);border-radius:9px;padding:11px;background:var(--panel-2)}.evidence-top,.span-top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:6px}.evidence-item strong,.span-item strong{font-size:11px}.small{font-size:10px;color:var(--muted);line-height:1.45;overflow-wrap:anywhere}.trace-button{border:0;background:transparent;padding:0;color:var(--accent);font-size:11px;font-weight:700}.trace-button:hover{text-decoration:underline}
    .summary-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:16px}.metric{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}.metric-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.metric-value{margin-top:7px;font-size:21px;font-weight:760;letter-spacing:-.03em}.metric-note{margin-top:3px;font-size:10px;color:var(--muted)}
    .table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse;font-size:11px}.table th{text-align:left;color:var(--muted);font-weight:700;border-bottom:1px solid var(--line);padding:10px 9px;white-space:nowrap}.table td{border-bottom:1px solid var(--line);padding:10px 9px;vertical-align:middle}.table tbody tr:hover{background:#fafbfc}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}.row-button{border:0;background:none;color:var(--accent);padding:0;text-align:left}
    .obs-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(380px,.65fr);gap:16px;align-items:start}.detail-empty{padding:36px 18px;text-align:center;color:var(--muted);font-size:12px}.detail-block{border-top:1px solid var(--line);padding:13px 0}.detail-block:first-child{border-top:0;padding-top:0}.detail-block h3{font-size:11px;margin:0 0 8px}.kv{display:grid;grid-template-columns:125px 1fr;gap:6px 10px;font-size:10px}.kv div:nth-child(odd){color:var(--muted)}.kv div:nth-child(even){overflow-wrap:anywhere}
    .loading{display:inline-block;width:13px;height:13px;border-radius:50%;border:2px solid rgba(255,255,255,.45);border-top-color:#fff;animation:spin .7s linear infinite;vertical-align:-2px;margin-right:6px}@keyframes spin{to{transform:rotate(360deg)}}
    @media(max-width:1100px){.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-2,.resolve-grid,.obs-layout{grid-template-columns:1fr}}@media(max-width:780px){.shell{grid-template-columns:1fr}.sidebar{padding:14px}.nav{grid-template-columns:repeat(3,1fr)}.nav-label,.sidebar-foot{display:none}.main{padding:20px 14px 36px}.summary-grid{grid-template-columns:1fr 1fr}.activity-row{grid-template-columns:1fr 1fr}}
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
        <button data-section="observability">Observability</button>
      </nav>
    </div>
    <div class="sidebar-foot">Local runtime<br/>Governed knowledge · grounded answers · traceable execution</div>
  </aside>

  <main class="main"><div class="page">
    <section id="sources" class="section active">
      <div class="topbar">
        <div><div class="eyebrow">Knowledge operations</div><h1>Sources & Ingestion</h1><p class="subtitle">Add governed source material, understand exactly what changed, and keep failed or duplicate operations visible.</p></div>
        <div class="runtime-pill"><span id="runtime-dot" class="dot"></span><span id="runtime-text">Checking runtime…</span></div>
      </div>
      <div class="grid-2">
        <div class="stack">
          <div class="card">
            <div class="card-head"><h2>Upload knowledge</h2><p>TXT, Markdown, HTML and DOCX · maximum 10 MB · local tenant for this slice.</p></div>
            <div class="card-body">
              <div id="ingest-error" class="inline-error"></div>
              <div id="dropzone" class="dropzone">
                <strong>Drop a knowledge file here</strong><p>Tropos parses, normalizes, versions, chunks and indexes it.</p>
                <input id="file-input" type="file" accept=".txt,.md,.markdown,.html,.htm,.xhtml,.docx" hidden />
                <button id="choose-file" class="button">Choose file</button><div id="file-name" class="file-name"></div>
              </div>
              <div style="display:flex;justify-content:flex-end;margin-top:12px"><button id="upload-file" class="button primary" disabled>Upload & ingest</button></div>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><h2>Session activity</h2><p>Every upload attempt in this browser session stays visible, including no-change and failed operations.</p></div>
            <div class="card-body"><div id="activity-empty" class="answer-empty" style="padding:22px 12px">No ingestion activity in this session.</div><div id="activity" class="activity"></div></div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h2>Latest ingestion</h2><p>Canonical outcome, not a generic “upload succeeded.”</p></div>
          <div class="card-body">
            <div id="ingestion-empty" class="answer-empty" style="padding:28px 12px">No file has been processed in this session.</div>
            <div id="ingestion-result" class="status-card" hidden>
              <div class="status-top"><div><div id="ingestion-filename" class="status-title">—</div><div id="ingestion-message" class="status-message">—</div></div><span id="ingestion-badge" class="badge">—</span></div>
              <dl class="meta"><dt>Outcome</dt><dd id="ingestion-outcome">—</dd><dt>Reason</dt><dd id="ingestion-reason">—</dd><dt>Chunks written</dt><dd id="ingestion-chunks">—</dd><dt>Knowledge ID</dt><dd id="ingestion-knowledge">—</dd><dt>Run ID</dt><dd id="ingestion-run">—</dd></dl>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="resolve" class="section">
      <div class="topbar">
        <div><div class="eyebrow">Support workspace</div><h1>Resolve</h1><p class="subtitle">Ask only against governed Tropos knowledge. The runtime answers with evidence, abstains explicitly, or shows a recoverable runtime failure.</p></div>
        <div class="runtime-pill"><span class="dot ready"></span><span>Grounded mode</span></div>
      </div>
      <div class="resolve-grid">
        <div class="stack">
          <div class="card">
            <div class="card-head"><h2>Ask a question</h2><p>No unrestricted world-knowledge fallback.</p></div>
            <div class="card-body">
              <div id="resolve-error" class="inline-error"></div>
              <textarea id="query" placeholder="Ask a question about the governed knowledge…"></textarea>
              <div class="composer-actions"><span class="hint">BM25 retrieval → gate → sufficiency → grounded generation.</span><button id="ask" class="button primary">Resolve</button></div>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><h2>Answer</h2><p id="answer-caption">Waiting for a question.</p></div>
            <div class="card-body">
              <div id="answer-empty" class="answer-empty">Ask a question to see the runtime outcome, evidence and citations.</div>
              <div id="answer-result" hidden><p id="answer-text" class="answer-text"></p><div id="answer-explain" class="explain" hidden></div><div id="answer-meta" class="answer-meta"></div></div>
            </div>
          </div>
        </div>
        <div class="stack">
          <div class="card"><div class="card-head"><h2>Evidence</h2><p>Only evidence admitted to the Resolve path appears here.</p></div><div class="card-body"><div id="evidence-empty" class="answer-empty" style="padding:20px 8px">No evidence selected yet.</div><div id="evidence-list" class="panel-list"></div></div></div>
          <div class="card"><div class="card-head"><h2>Decision</h2><p>Quality state stays explicit; UNVALIDATED is not converted into a confidence score.</p></div><div class="card-body"><div id="decision-empty" class="answer-empty" style="padding:20px 8px">No runtime decision yet.</div><div id="decision-result" hidden><div class="status-card"><div class="status-top"><strong>Evidence assessment</strong><span id="decision-label" class="badge">—</span></div><dl class="meta" style="grid-template-columns:110px 1fr"><dt>Validation</dt><dd id="decision-validation">—</dd><dt>Failure type</dt><dd id="decision-failure">—</dd><dt>Trace</dt><dd><button id="open-observability" class="trace-button">Inspect in Observability</button></dd></dl></div></div></div></div>
        </div>
      </div>
    </section>

    <section id="observability" class="section">
      <div class="topbar">
        <div><div class="eyebrow">Runtime operations</div><h1>Observability</h1><p class="subtitle">Inspect recent Resolve executions, failure/abstention patterns, model usage, retrieval decisions and trace lineage without storing raw queries or evidence text.</p></div>
        <div class="toolbar-right"><button id="refresh-observability" class="button">Refresh</button></div>
      </div>
      <div id="obs-error" class="inline-error"></div>
      <div class="summary-grid">
        <div class="metric"><div class="metric-label">Traces</div><div id="m-traces" class="metric-value">—</div><div class="metric-note">Persisted local runs</div></div>
        <div class="metric"><div class="metric-label">Answered</div><div id="m-answered" class="metric-value">—</div><div id="m-rate" class="metric-note">Answer rate —</div></div>
        <div class="metric"><div class="metric-label">Abstained</div><div id="m-abstained" class="metric-value">—</div><div class="metric-note">Retrieval + evidence insufficiency</div></div>
        <div class="metric"><div class="metric-label">Runtime failed</div><div id="m-failed" class="metric-value">—</div><div class="metric-note">Execution failures</div></div>
        <div class="metric"><div class="metric-label">Model latency</div><div id="m-latency" class="metric-value">—</div><div id="m-tokens" class="metric-note">Tokens —</div></div>
      </div>
      <div class="obs-layout">
        <div class="card">
          <div class="card-head"><div class="toolbar"><div><h2>Recent traces</h2><p>Failure-first operational list. Select a row to inspect the full functional path.</p></div><select id="trace-filter" class="select"><option value="ALL">All outcomes</option><option value="RUNTIME_FAILED">Runtime failed</option><option value="EVIDENCE_INSUFFICIENT">Evidence insufficient</option><option value="RETRIEVAL_ABSTAINED">Retrieval abstained</option><option value="ANSWERED">Answered</option></select></div></div>
          <div class="card-body" style="padding:0"><div class="table-wrap"><table class="table"><thead><tr><th>Outcome</th><th>Trace</th><th>Recorded</th><th>Retrieval</th><th>Gate</th><th>Sufficiency</th><th>Model</th><th>Latency</th></tr></thead><tbody id="trace-rows"></tbody></table></div><div id="trace-empty" class="answer-empty">No traces recorded yet.</div></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>Trace detail</h2><p>Progressive disclosure of execution stages and captured runtime metadata.</p></div>
          <div class="card-body"><div id="trace-detail-empty" class="detail-empty">Select a trace from the table.</div><div id="trace-detail" hidden></div></div>
        </div>
      </div>
    </section>
  </div></main>
</div>

<script>
(() => {
  const state={file:null,traceId:null,activity:[],observability:null};
  const el=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusClass=value=>value==='ANSWERED'||value==='SUFFICIENT'||String(value).startsWith('available')?'success':value==='RUNTIME_FAILED'?'danger':value?'warn':'';
  const friendlyOutcome=value=>({VERSION_CREATED:'New version created',NO_CHANGE:'No content change',GOVERNANCE_REFRESHED:'Access updated',REBASELINE_REQUIRED:'Action required',ANSWERED:'Answered',EVIDENCE_INSUFFICIENT:'Evidence insufficient',RETRIEVAL_ABSTAINED:'Retrieval abstained',RUNTIME_FAILED:'Runtime failed'}[value]||String(value||'Unknown').replaceAll('_',' ').toLowerCase().replace(/^./,m=>m.toUpperCase()));

  document.querySelectorAll('.nav button').forEach(button=>button.addEventListener('click',()=>activate(button.dataset.section)));
  function activate(section){document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('active',b.dataset.section===section));document.querySelectorAll('.section').forEach(s=>s.classList.toggle('active',s.id===section));if(section==='observability')loadObservability();}

  async function api(url,options={}){const response=await fetch(url,options);const data=await response.json().catch(()=>({}));if(!response.ok){const e=data.error||{};const error=new Error(e.message||data.detail||('Request failed: '+response.status));error.info={code:e.code||('HTTP_'+response.status),stage:e.stage||'request',retryable:!!e.retryable,status:response.status};throw error;}return data;}
  function renderError(target,title,error,retry){const box=el(target),info=error.info||{};box.innerHTML='<div class="inline-error-head"><strong>'+esc(title)+'</strong><span class="badge danger">ERROR</span></div><p>'+esc(error.message)+'</p><div class="error-meta">Stage: '+esc(info.stage||'unknown')+' · Code: '+esc(info.code||'UNKNOWN')+(info.status?' · HTTP '+esc(info.status):'')+'</div>'+(retry?'<div class="retry"><button class="button" id="'+target+'-retry">Retry</button></div>':'');box.classList.add('show');if(retry)el(target+'-retry').onclick=retry;}
  function clearError(target){el(target).classList.remove('show');el(target).innerHTML='';}

  api('/api/health').then(data=>{el('runtime-dot').classList.add('ready');el('runtime-text').textContent=data.model_configured?data.model+' · '+data.retrieval:'Model not configured';}).catch(()=>{el('runtime-text').textContent='Runtime unavailable';});

  const fileInput=el('file-input'),dropzone=el('dropzone'),upload=el('upload-file');
  el('choose-file').onclick=()=>fileInput.click();fileInput.onchange=()=>selectFile(fileInput.files[0]);
  ['dragenter','dragover'].forEach(name=>dropzone.addEventListener(name,e=>{e.preventDefault();dropzone.classList.add('drag')}));['dragleave','drop'].forEach(name=>dropzone.addEventListener(name,e=>{e.preventDefault();dropzone.classList.remove('drag')}));dropzone.addEventListener('drop',e=>selectFile(e.dataTransfer.files[0]));
  function selectFile(file){state.file=file||null;el('file-name').style.display=file?'block':'none';el('file-name').textContent=file?file.name+' · '+Math.max(1,Math.round(file.size/1024))+' KB':'';upload.disabled=!file;}

  upload.onclick=()=>ingestSelected();
  async function ingestSelected(){if(!state.file)return;clearError('ingest-error');upload.disabled=true;const original=upload.textContent;upload.innerHTML='<span class="loading"></span>Ingesting';try{const data=await api('/api/ingest?filename='+encodeURIComponent(state.file.name),{method:'POST',headers:{'Content-Type':state.file.type||'application/octet-stream'},body:state.file});renderIngestion(data);state.activity.unshift({ok:true,...data});renderActivity();}catch(error){state.activity.unshift({ok:false,filename:state.file.name,error:error.message,info:error.info});renderActivity();renderError('ingest-error','Ingestion failed',error,()=>ingestSelected());}finally{upload.disabled=false;upload.textContent=original;}}

  function ingestionMessage(data){if(data.replayed)return 'Already ingested. Existing knowledge version retained; no duplicate processing was performed.';if(data.outcome==='NO_CHANGE')return 'No canonical content change. Existing knowledge version retained.';if(data.outcome==='GOVERNANCE_REFRESHED')return 'Content unchanged; access metadata was refreshed.';if(data.outcome==='REBASELINE_REQUIRED')return 'The source requires rebaseline before it can be treated as current.';return 'New canonical knowledge version created and indexed.';}
  function renderIngestion(data){el('ingestion-empty').hidden=true;el('ingestion-result').hidden=false;el('ingestion-filename').textContent=data.filename;el('ingestion-message').textContent=ingestionMessage(data);el('ingestion-outcome').textContent=data.replayed?'IDEMPOTENT_REPLAY':data.outcome;el('ingestion-reason').textContent=data.reason;el('ingestion-chunks').textContent=data.chunks_written;el('ingestion-knowledge').textContent=data.knowledge_id;el('ingestion-run').textContent=data.run_id;const badge=el('ingestion-badge');badge.textContent=data.replayed?'Already ingested':friendlyOutcome(data.outcome);badge.className='badge '+(data.outcome==='VERSION_CREATED'||data.outcome==='NO_CHANGE'||data.outcome==='GOVERNANCE_REFRESHED'?'success':'warn');}
  function renderActivity(){el('activity-empty').style.display=state.activity.length?'none':'block';el('activity').innerHTML=state.activity.map(item=>'<div class="activity-row"><strong>'+esc(item.filename)+'</strong><span>'+esc(item.ok?(item.replayed?'Already ingested':friendlyOutcome(item.outcome)):'Failed')+'</span><span class="badge '+(item.ok?'success':'danger')+'">'+(item.ok?(item.replayed?'REPLAY':'DONE'):'ERROR')+'</span><span class="muted">'+esc(item.ok?(item.replayed?'Existing version retained · run '+item.run_id:(item.outcome==='NO_CHANGE'?'Existing version retained':item.run_id)):(item.error||''))+'</span></div>').join('');}

  el('ask').onclick=()=>resolveQuestion();
  async function resolveQuestion(){const query=el('query').value.trim();if(!query){renderError('resolve-error','Question required',Object.assign(new Error('Enter a question first.'),{info:{code:'EMPTY_QUERY',stage:'resolve',retryable:false}}));return;}clearError('resolve-error');const button=el('ask'),original=button.textContent;button.disabled=true;button.innerHTML='<span class="loading"></span>Resolving';try{const data=await api('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query})});state.traceId=data.trace_id;renderResolve(data);}catch(error){renderError('resolve-error','Resolve failed',error,()=>resolveQuestion());el('answer-caption').textContent='Runtime failure. No answer was generated.';}finally{button.disabled=false;button.textContent=original;}}
  function renderResolve(data){el('answer-empty').hidden=true;el('answer-result').hidden=false;el('answer-caption').textContent=data.outcome==='ANSWERED'?'Grounded answer returned.':'Tropos abstained rather than generating beyond the evidence.';el('answer-text').textContent=data.answer||(data.outcome==='EVIDENCE_INSUFFICIENT'?'I could not answer this from the available governed evidence.':'No eligible evidence passed the retrieval gate.');const explain=el('answer-explain'),decision=data.evidence_assessment;if(decision&&data.outcome!=='ANSWERED'){const missing=decision.missing_facts||[];explain.hidden=false;explain.innerHTML='<h3>Why Tropos abstained</h3><p>'+esc(decision.rationale||friendlyOutcome(data.outcome))+'</p>'+(missing.length?'<ul>'+missing.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'');}else explain.hidden=true;const meta=el('answer-meta');meta.innerHTML='';[['Outcome',friendlyOutcome(data.outcome),statusClass(data.outcome)],['Trace',data.trace_id,'info']].forEach(([label,value,cls])=>{const span=document.createElement('span');span.className='badge '+cls;span.textContent=label+': '+value;meta.appendChild(span);});const evidence=data.evidence||[];el('evidence-empty').style.display=evidence.length?'none':'block';el('evidence-list').innerHTML=evidence.map(item=>'<div class="evidence-item"><div class="evidence-top"><strong>'+esc(item.alias)+' · '+esc(item.title)+'</strong><span class="badge info">rank '+esc(item.rank??'—')+'</span></div><div class="small">Score: '+esc(item.score??'—')+'</div><div class="small">'+esc(item.locator)+'</div></div>').join('');el('decision-empty').hidden=!!decision;el('decision-result').hidden=!decision;if(decision){const badge=el('decision-label');badge.textContent=decision.label;badge.className='badge '+statusClass(decision.label);el('decision-validation').textContent=decision.validation_status;el('decision-failure').textContent=decision.failure_type;}}
  el('open-observability').onclick=()=>{activate('observability');if(state.traceId)setTimeout(()=>loadTrace(state.traceId),150);};

  el('refresh-observability').onclick=()=>loadObservability();el('trace-filter').onchange=()=>renderTraceRows();
  async function loadObservability(){clearError('obs-error');try{const data=await api('/api/observability');state.observability=data;renderObservability(data);}catch(error){renderError('obs-error','Observability unavailable',error,()=>loadObservability());}}
  function renderObservability(data){const s=data.summary||{};el('m-traces').textContent=s.trace_count??0;el('m-answered').textContent=s.answered??0;el('m-abstained').textContent=s.abstained??0;el('m-failed').textContent=s.failed??0;el('m-rate').textContent='Answer rate '+(s.answer_rate==null?'—':Math.round(s.answer_rate*100)+'%');el('m-latency').textContent=s.average_model_latency_ms==null?'—':Math.round(s.average_model_latency_ms)+' ms';el('m-tokens').textContent='Tokens '+(s.input_tokens??0)+' in / '+(s.output_tokens??0)+' out · Cost not captured';renderTraceRows();}
  function renderTraceRows(){const traces=(state.observability&&state.observability.traces)||[],filter=el('trace-filter').value,filtered=traces.filter(t=>filter==='ALL'||t.outcome===filter);el('trace-empty').style.display=filtered.length?'none':'block';el('trace-rows').innerHTML=filtered.map(t=>'<tr><td><span class="badge '+statusClass(t.outcome)+'">'+esc(friendlyOutcome(t.outcome))+'</span></td><td><button class="row-button mono" data-trace="'+esc(t.trace_id)+'">'+esc(String(t.trace_id||'').replace('trace_','').slice(0,10))+'…</button></td><td>'+esc(formatTime(t.recorded_at))+'</td><td>'+esc(t.retrieval_strategy||'—')+' · '+esc(t.result_count??'—')+'</td><td>'+esc(t.gate_status||'—')+'</td><td>'+esc(t.sufficiency||'—')+'</td><td>'+esc(t.model||'—')+'</td><td>'+esc(t.model_latency_ms==null?'—':Math.round(t.model_latency_ms)+' ms')+'</td></tr>').join('');document.querySelectorAll('[data-trace]').forEach(b=>b.onclick=()=>loadTrace(b.dataset.trace));}
  function formatTime(value){if(!value)return 'Legacy trace';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString();}
  async function loadTrace(traceId){try{const trace=await api('/api/traces/'+encodeURIComponent(traceId));renderTraceDetail(trace);}catch(error){renderError('obs-error','Trace could not be loaded',error);}}
  function renderTraceDetail(trace){el('trace-detail-empty').hidden=true;el('trace-detail').hidden=false;const blocks=[{title:'Identity',pairs:[['Trace ID',trace.trace_id],['Request ID',trace.request_id],['Outcome',friendlyOutcome(trace.outcome)],['Recorded',formatTime(trace.recorded_at)]]}];(trace.spans||[]).forEach(span=>blocks.push({title:span.name,pairs:[['Status',span.status],...Object.entries(span.attributes||{})]}));blocks.push({title:'Not captured',pairs:[['Cost','Not captured'],['Raw query/evidence','Intentionally not recorded in local trace'] ]});el('trace-detail').innerHTML=blocks.map(block=>'<div class="detail-block"><h3>'+esc(block.title)+'</h3><div class="kv">'+block.pairs.map(([k,v])=>'<div>'+esc(k)+'</div><div>'+esc(Array.isArray(v)?v.join(', '):(v??'—'))+'</div>').join('')+'</div></div>').join('');}
})();
</script>
</body>
</html>
"""
