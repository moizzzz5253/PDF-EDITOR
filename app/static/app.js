/* PDF//SCOPE front end. No build step, no dependencies: edit and reload.
   Sections: utils · api · scope · log · pipeline · inspector · faults · files · tools ·
   workbench · run+animate · compare · share · system · init */
'use strict';

// ------------------------------------------------------------------ utils
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(k));
  return el;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmtBytes = n => n == null ? '-' : n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : n < 1073741824 ? (n / 1048576).toFixed(2) + ' MB' : (n / 1073741824).toFixed(2) + ' GB';
const hms = t => new Date(t * 1000).toLocaleTimeString([], { hour12: false }) + '.' + String(Math.floor(t * 1000) % 1000).padStart(3, '0');
function compressPages(set) {
  const a = [...set].sort((x, y) => x - y), out = [];
  for (let i = 0; i < a.length;) {
    let j = i; while (a[j + 1] === a[j] + 1) j++;
    out.push(j > i ? `${a[i] + 1}-${a[j] + 1}` : `${a[i] + 1}`); i = j + 1;
  }
  return out.join(',');
}
function copy(text, label = 'copied') {
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).catch(() => {
    const t = h('textarea', {}, text); document.body.append(t); t.select(); document.execCommand('copy'); t.remove();
  }).finally(() => toast(label));
}
function toast(msg, cls = '') { const t = h('div', { class: 'toast ' + cls }, msg); $('#toast').append(t); setTimeout(() => t.remove(), 3800); }

const S = { ops: {}, order: [], nodes: [], integ: {}, files: [], cur: null, ver: null, sel: new Set(), op: null, tab: 'work', busy: false, logSince: 0, faults: [], cmp: null, lastAnchor: null };
const curRec = () => S.files.find(f => f.id === S.cur);
const verRec = (rec = curRec(), n = S.ver) => rec && rec.versions.find(v => v.n === n);

// ------------------------------------------------------------------ api
async function api(path, { method = 'GET', json, form, quiet = false } = {}) {
  let res;
  try {
    res = await fetch(path, { method, headers: json ? { 'Content-Type': 'application/json' } : {}, body: json ? JSON.stringify(json) : form });
  } catch (e) {
    setLink(false);
    const payload = { code: 'E_NETWORK', title: 'Cannot reach the server', cause: `fetch(${method} ${path}) failed before any response: ${e.message}. The Python server is probably not running, crashed, or the address/port changed.`,
      fix: 'Check the terminal running "python run.py" for a crash message, restart it, then reload.', exc_type: e.name, exc_message: e.message, where: { file: 'browser', line: 0, func: 'fetch', code: `${method} ${path}` }, frames: [], traceback: e.stack || '' };
    if (!quiet) showFault(payload);
    throw Object.assign(new Error(payload.title), { payload: { error: payload }, handled: !quiet });
  }
  setLink(true);
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json() : null;
  if (!res.ok || (data && data.ok === false)) {
    const err = data && data.error ? data.error : { code: 'E_HTTP_' + res.status, title: `HTTP ${res.status} ${res.statusText}`, cause: `Server answered ${res.status} with a non-JSON body for ${method} ${path}. A proxy or crashed worker is the usual cause.`, fix: 'Look at the server terminal output.', frames: [], traceback: '' };
    if (!quiet) showFault(err, data && data.trace);
    throw Object.assign(new Error(err.title), { payload: data || { error: err }, handled: !quiet });
  }
  return data;
}
function setLink(ok) { $('#srvLed').className = 'led ' + (ok ? 'ok' : 'bad'); $('#srvTxt').textContent = ok ? 'LINK UP' : 'LINK DOWN'; }
window.addEventListener('error', e => { reportClient(e.message, `${e.filename}:${e.lineno}`, e.error && e.error.stack); });
window.addEventListener('unhandledrejection', e => { if (e.reason && e.reason.handled) return; reportClient(e.reason && e.reason.message || String(e.reason), 'promise', e.reason && e.reason.stack); });
function reportClient(message, source, stack) {
  showFault({ code: 'E_BROWSER', title: 'Browser-side script error', cause: `${message} (at ${source}). This is a bug in the dashboard JavaScript, not in the server.`, fix: 'Copy the diagnostic and check the line in app.js.', exc_type: 'JS', exc_message: message, where: { file: 'static/app.js', line: source.split(':').pop(), func: '', code: '' }, frames: [], traceback: stack || '' });
  fetch('/api/client-error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, source }) }).catch(() => { });
}

// ------------------------------------------------------------------ scope (oscilloscope)
const scope = (() => {
  const cv = $('#scope'), g = cv.getContext('2d');
  const st = { amp: .06, base: .06, color: '61,255,176', t: 0, mode: 'idle', hist: [] };
  function resize() { cv.width = cv.clientWidth * devicePixelRatio; cv.height = cv.clientHeight * devicePixelRatio; }
  new ResizeObserver(resize).observe(cv);
  function frame() {
    const W = cv.width, H = cv.height; st.t += .09;
    g.fillStyle = 'rgba(3,7,6,.22)'; g.fillRect(0, 0, W, H);
    g.strokeStyle = 'rgba(61,255,176,.09)'; g.lineWidth = 1; g.beginPath();
    for (let i = 1; i < 10; i++) { g.moveTo(W * i / 10, 0); g.lineTo(W * i / 10, H); } for (let i = 1; i < 6; i++) { g.moveTo(0, H * i / 6); g.lineTo(W, H * i / 6); }
    g.stroke();
    st.amp += (st.base - st.amp) * .04;
    g.strokeStyle = `rgb(${st.color})`; g.shadowColor = `rgb(${st.color})`; g.shadowBlur = 8; g.lineWidth = 2 * devicePixelRatio; g.beginPath();
    for (let x = 0; x <= W; x += 3) {
      const p = x / W; let y;
      if (st.mode === 'flat') y = 0;
      else if (st.mode === 'busy') y = Math.sin(p * 90 + st.t * 4) * .5 + (Math.random() - .5) * .6;
      else y = Math.sin(p * 14 + st.t) * .6 + Math.sin(p * 37 - st.t * 1.7) * .25 + (Math.random() - .5) * .15;
      const yy = H / 2 + y * st.amp * H * (st.mode === 'flat' ? 0 : 1);
      x ? g.lineTo(x, yy) : g.moveTo(x, yy);
    }
    g.stroke(); g.shadowBlur = 0;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  return {
    ping(ms) { st.amp = clamp(.12 + Math.log10(1 + ms) * .13, .12, .46); st.color = '61,255,176'; st.mode = 'idle'; },
    busy(on) { st.mode = on ? 'busy' : 'idle'; st.base = on ? .2 : .06; st.color = on ? '255,179,64' : '61,255,176'; },
    fault() { st.mode = 'flat'; st.color = '255,77,94'; st.base = .06; setTimeout(() => { st.mode = 'idle'; st.amp = .5; st.color = '255,77,94'; setTimeout(() => st.color = '61,255,176', 1500); }, 700); },
    info(t) { $('#scopeInfo').textContent = t; },
  };
})();

// ------------------------------------------------------------------ log console
function logLine(e) {
  const box = $('#log'); const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
  const lv = e.level || 'info';
  box.append(h('div', { class: lv + (e.kind === 'step' ? ' step' : ''), 'data-lv': lv },
    h('span', { class: 't' }, hms(e.t || Date.now() / 1000) + ' '), h('span', { class: 'k' }, `[${e.kind}] `), e.msg, e.ms != null ? `  (${e.ms} ms)` : ''));
  while (box.children.length > 400) box.firstChild.remove();
  if (stick) box.scrollTop = box.scrollHeight;
  applyLogFilter();
}
function applyLogFilter() { const only = $('#logErr').checked; $$('#log > div').forEach(d => d.style.display = only && d.dataset.lv !== 'error' ? 'none' : ''); }
async function pollLogs() {
  try {
    const ev = await fetch('/api/logs?since=' + S.logSince).then(r => r.json());
    for (const e of ev) { S.logSince = Math.max(S.logSince, e.id); logLine(e); }
  } catch (e) { setLink(false); }
}

// ------------------------------------------------------------------ pipeline
const NODE_HELP = {
  INPUT: 'Request arrives: the browser sends the form (file id, parameters, uploads). Server saves uploads to disk with a size cap.',
  VALIDATE: 'Cheap checks before expensive work: is it really a PDF (magic bytes), are the page numbers in range, is the tool installed.',
  PARSE: 'PyMuPDF reads the PDF index (xref table) and builds the page tree in memory.',
  TRANSFORM: 'The actual edit: delete / insert / crop / render / convert happens here.',
  ENCODE: 'Pixels or text turned into a storable format (JPEG, PNG...).',
  WRITE: 'Result serialised to disk as a NEW version. Old versions are never overwritten.',
  VERIFY: 'Output re-opened and checked (page count) so a corrupt result is caught immediately.',
};
const pipe = {
  build() {
    const box = $('#pipe'); box.innerHTML = '';
    S.nodes.forEach((n, i) => {
      if (i) box.append(h('div', { class: 'wire', 'data-w': i }));
      box.append(h('div', { class: 'node', 'data-n': n, onclick: () => inspectNode(n) }, h('i', { class: 'led' }), h('div', { class: 'nm' }, n), h('div', { class: 'ms' }, '')));
    });
  },
  reset() { $$('.node').forEach(n => { n.className = 'node'; $('.ms', n).textContent = ''; }); $$('.wire').forEach(w => w.className = 'wire'); },
  begin(label) { this.reset(); $('#pipeInfo').textContent = `${label}: request sent...`; const n = $('.node[data-n=INPUT]'); n.classList.add('active'); $$('.wire').forEach(w => w.classList.add('flow')); scope.busy(true); },
  async play(trace, total, failed) {
    this.reset(); scope.busy(false);
    const order = S.nodes, seen = new Set(), acc = {};
    for (const s of trace) {
      const n = $(`.node[data-n=${s.node}]`); if (!n) continue;
      const idx = order.indexOf(s.node);
      $$('.wire').forEach(w => { if (+w.dataset.w <= idx) w.classList.add('lit'); });
      n.classList.remove('done'); n.classList.add('active');
      const row = $(`.step[data-i="${trace.indexOf(s)}"]`); if (row) { row.classList.add('playing'); row.scrollIntoView({ block: 'nearest' }); }
      scope.ping(s.ms || 1);
      await sleep(clamp((s.ms || 1) * 1.5, 150, 480));
      acc[s.node] = (acc[s.node] || 0) + (s.ms || 0);
      n.classList.remove('active'); n.classList.add(s.status === 'error' ? 'error' : 'done'); $('.ms', n).textContent = acc[s.node].toFixed(1) + ' ms';
      if (row) row.classList.remove('playing');
      seen.add(s.node);
      if (s.status === 'error') { $$('.wire').forEach(w => { if (+w.dataset.w > idx) { w.classList.remove('lit'); w.classList.add('dead'); } }); break; }
    }
    S.nodes.forEach(n => { if (!seen.has(n)) $(`.node[data-n=${n}]`).classList.add('bypass'); });
    $('#pipeInfo').textContent = failed ? `FAULT after ${trace.length} step(s)` : `done in ${total} ms (replay of the server's recorded step timings)`;
    if (failed) scope.fault();
  },
  quick(label, ok = true) { // for non-operation calls: a fast sweep
    this.reset(); $('#pipeInfo').textContent = label; $$('.node').forEach((n, i) => setTimeout(() => n.classList.add(ok ? 'done' : 'error'), i * 40)); scope.ping(8);
  },
};
function inspectNode(n) {
  const box = $('#insp');
  const steps = $$('.step', box).filter(s => s.dataset.node === n);
  if (steps.length) { steps.forEach(s => s.classList.add('open')); steps[0].scrollIntoView({ block: 'nearest' }); }
  logLine({ level: 'info', kind: 'help', t: Date.now() / 1000, msg: `${n}: ${NODE_HELP[n]}` });
}

// ------------------------------------------------------------------ step inspector
function showTrace(trace) {
  const box = $('#insp'); box.innerHTML = '';
  if (!trace || !trace.length) { renderNodeInfo(); return; }
  trace.forEach((s, i) => {
    const row = h('div', { class: 'step ' + s.status, 'data-i': i, 'data-node': s.node, onclick: () => row.classList.toggle('open') },
      h('div', { class: 't' }, h('span', { class: 'n' }, s.node), s.title, h('em', {}, s.ms != null ? s.ms + ' ms' : '')),
      h('div', { class: 'ex' }, s.explain, s.detail ? h('div', { class: 'dt' }, '→ ' + s.detail) : null, s.call ? h('code', {}, s.call) : null));
    box.append(row);
    logLine({ level: s.status === 'error' ? 'error' : 'info', kind: 'step', t: Date.now() / 1000, msg: `${s.node.padEnd(9)} ${s.title}${s.detail ? ' → ' + s.detail : ''}`, ms: s.ms });
  });
}
function renderNodeInfo() {
  const box = $('#insp'); box.innerHTML = '';
  box.append(h('div', { class: 'nodeinfo' }, h('div', {}, 'Every command passes through these stages. Run a tool and each stage lights up with its real timing. Click a stage above to read what it does.'), ...S.nodes.map(n => h('div', {}, h('b', {}, n + ' '), NODE_HELP[n]))));
}

// ------------------------------------------------------------------ faults
function showFault(e, trace) {
  S.faults.push(e); $('#faultN').textContent = S.faults.length; $('#faultBadge').classList.add('has');
  scope.fault();
  const w = e.where, box = $('#fault'); box.hidden = false; box.innerHTML = ''; box.style.animation = 'none'; void box.offsetWidth; box.style.animation = '';
  const diag = () => `PDF//SCOPE diagnostic\ncode: ${e.code}\ntitle: ${e.title}\ncause: ${e.cause}\nfix: ${e.fix}\nwhere: ${w ? `${w.file}:${w.line} in ${w.func}()  ${w.code}` : '-'}\nfailed step: ${e.failed_step || '-'}  call: ${e.failed_call || '-'}\n${e.exc_type}: ${e.exc_message}\n\n${e.traceback || ''}`;
  box.append(
    h('div', { class: 'fhead' }, '⚠ FAULT', h('span', { class: 'code' }, e.code), h('button', { class: 'btn sm close', onclick: () => box.hidden = true }, 'DISMISS')),
    h('div', { class: 'ttl' }, e.title),
    h('div', { class: 'kv' },
      h('div', {}, 'ROOT CAUSE'), h('div', {}, e.cause),
      h('div', {}, 'HOW TO FIX'), h('div', { class: 'fix' }, e.fix),
      e.failed_step ? [h('div', {}, 'FAILED AT'), h('div', {}, e.failed_step, e.failed_call ? h('pre', {}, e.failed_call) : null)] : null,
      w ? [h('div', {}, 'RAISED IN'), h('pre', {}, `${w.file}:${w.line}  ${w.func}()\n${w.code || ''}`)] : null,
      e.frames && e.frames.length ? [h('div', {}, 'CALL STACK'), h('div', { class: 'frames' }, ...e.frames.map((f, i) => h('div', { class: (f.app ? 'app ' : '') + (i === e.frames.length - 1 ? 'last' : '') }, `${i ? '↳ ' : ''}${f.file}:${f.line} ${f.func}()${f.code ? '  — ' + f.code : ''}`)))] : null),
    h('details', {}, h('summary', {}, `raw: ${e.exc_type}: ${e.exc_message}`), h('pre', {}, e.traceback || '(none)')),
    h('div', { class: 'acts' }, h('button', { class: 'btn', onclick: () => copy(diag(), 'diagnostic copied') }, 'COPY DIAGNOSTIC')));
  box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  if (trace) showTrace(trace);
}
$('#faultBadge').onclick = () => { if (S.faults.length) { const e = S.faults[S.faults.length - 1]; S.faults.pop(); showFault(e); } };

// ------------------------------------------------------------------ files
async function loadFiles(selectId) {
  S.files = await api('/api/files');
  if (selectId) S.cur = selectId;
  if (!S.files.find(f => f.id === S.cur)) S.cur = S.files[0] ? S.files[0].id : null;
  const rec = curRec();
  if (rec && (!S.ver || !verRec(rec, S.ver) || selectId)) S.ver = rec.current;
  if (!rec) S.ver = null;
  renderFiles(); renderTools(); renderStage(); renderForm();
}
function renderFiles(freshId) {
  const ul = $('#fileList'); ul.innerHTML = ''; $('#filesCount').textContent = S.files.length;
  if (!S.files.length) ul.append(h('li', { style: 'cursor:default;grid-template-columns:1fr' }, h('span', { class: 'fmeta', style: 'grid-column:1' }, 'No files yet. Drop one above.')));
  for (const f of S.files) {
    const v = f.versions.find(v => v.n === f.current);
    const li = h('li', { class: (f.id === S.cur ? 'on ' : '') + (f.id === freshId ? 'fresh' : ''), onclick: () => { S.cur = f.id; S.ver = f.current; S.sel.clear(); renderFiles(); renderStage(); renderForm(); renderTools(); if (S.tab !== 'work' && S.tab !== 'compare') showTab(S.tab); if (S.tab === 'share') renderShare(); if (S.tab === 'compare') initCompare(); } },
      h('span', { class: 'kind k-' + f.kind }, f.kind.toUpperCase()), h('span', { class: 'fname', title: f.name }, f.name),
      h('span', {}, h('button', { class: 'iconbtn', title: 'Rename', onclick: ev => { ev.stopPropagation(); startRename(f, li); } }, '✎'), h('button', { class: 'iconbtn del', title: 'Delete', onclick: ev => { ev.stopPropagation(); delFile(f); } }, '✕')),
      h('span', { class: 'fmeta' }, `${fmtBytes(v.size)}${v.pages != null ? ' · ' + v.pages + ' pg' : ''} · ${f.versions.length} ver · id ${f.id}`));
    ul.append(li);
  }
}
function startRename(f, li) {
  const inp = h('input', { type: 'text', value: f.name });
  const go = async () => { if (inp.value === f.name) return renderFiles(); try { await api(`/api/files/${f.id}`, { method: 'PATCH', json: { name: inp.value } }); pipe.quick('rename: metadata updated (file on disk untouched)'); toast('renamed'); await loadFiles(); if (S.tab === 'share') renderShare(); } catch (e) { inp.focus(); } };
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); if (e.key === 'Escape') renderFiles(); });
  li.onclick = null; li.append(h('div', { class: 'rename' }, inp, h('button', { class: 'btn sm', onclick: ev => { ev.stopPropagation(); go(); } }, 'OK')));
  inp.focus(); inp.select();
}
async function delFile(f) { if (!confirm(`Delete "${f.name}" and all ${f.versions.length} version(s)?`)) return; await api(`/api/files/${f.id}`, { method: 'DELETE' }); pipe.quick('delete: folder removed from workspace'); await loadFiles(); }
async function upload(fileList) {
  const files = [...fileList]; if (!files.length) return;
  const drop = $('#drop'); drop.classList.add('busy'); scope.busy(true); pipe.begin('upload');
  try {
    const fd = new FormData(); files.forEach(f => fd.append('file', f));
    const recs = await api('/api/files', { method: 'POST', form: fd });
    scope.busy(false); pipe.quick(`upload: ${recs.length} file(s) stored, type sniffed from content`);
    S.sel.clear(); await loadFiles(recs[0].id); renderFiles(recs[0].id); toast(`${recs.length} file(s) received`);
  } catch (e) { scope.busy(false); pipe.quick('upload failed', false); } finally { drop.classList.remove('busy'); refreshSystem(); }
}

// ------------------------------------------------------------------ tools
const ICON = { remove_pages: '✂', add_pages: '＋', crop_pages: '⌗', extract_pages: '⇱', pdf_to_image: '▣', image_to_pdf: '▤', docx_to_pdf: 'W' };
function renderTools() {
  const box = $('#toolList'); box.innerHTML = ''; const kind = curRec() && curRec().kind; let g = null;
  for (const id of S.order) {
    const o = S.ops[id];
    if (o.group !== g) { g = o.group; box.append(h('div', { class: 'grp' }, g)); }
    const incompat = kind && o.source !== 'none' && !o.accepts.includes(kind) && o.source === 'required';
    box.append(h('button', { class: 'tool' + (S.op === id && S.tab === 'work' ? ' on' : '') + (incompat ? ' incompat' : ''), title: incompat ? `Needs ${o.accepts.join('/').toUpperCase()}; selected file is ${kind.toUpperCase()}` : o.desc, onclick: () => { const was = S.op; S.op = id; showTab('work'); renderTools(); renderForm(); if (was !== id && [was, id].includes('reorder_pages')) renderStage(); } },
      h('i', {}, ICON[id] || '◆'), h('span', {}, o.label)));
  }
  $$('#toolsPanel > .tool').forEach(b => b.classList.toggle('on', S.tab === b.dataset.tab));
}
$$('#toolsPanel > .tool').forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showTab(t) {
  S.tab = t; $('#fault').hidden = true; $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t)); $$('.tab').forEach(x => x.classList.toggle('on', x.id === 'tab-' + t));
  if (t === 'compare') initCompare(); if (t === 'share') renderShare(); renderTools();
}
$$('#tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ------------------------------------------------------------------ workbench: versions + pages
function renderStage() {
  const rec = curRec(), pg = $('#pages'), vs = $('#versions'); pg.innerHTML = ''; vs.innerHTML = '';
  if (!rec) { $('#stageTitle').textContent = 'NO FILE SELECTED'; $('#stageInfo').textContent = ''; pg.append(h('div', { class: 'empty' }, 'Upload a PDF, Word file or image to begin. Every edit creates a new version, so nothing is lost.')); return; }
  const v = verRec(); $('#stageTitle').textContent = rec.name; $('#stageInfo').textContent = `${fmtBytes(v.size)} · ${v.pages != null ? v.pages + ' pages · ' : ''}v${v.n} of ${rec.versions.length} · md5 ${v.md5.slice(0, 8)}`;
  rec.versions.forEach((x, i) => {
    if (i) vs.append(h('span', { class: 'arrow' }, '→'));
    const prev = rec.versions[i - 1], d = prev ? x.size - prev.size : 0;
    vs.append(h('div', { class: 'ver' + (x.n === S.ver ? ' on' : ''), title: x.note || '', onclick: async () => { S.ver = x.n; S.sel.clear(); await api(`/api/files/${rec.id}/current`, { method: 'POST', json: { v: x.n } }); rec.current = x.n; renderFiles(); renderStage(); renderForm(); } },
      `v${x.n} ${x.op}`, h('small', {}, `${fmtBytes(x.size)}${x.pages != null ? ' · ' + x.pages + 'p' : ''}`, prev ? h('span', { class: d > 0 ? 'd' : 'dn' }, ` ${d > 0 ? '+' : ''}${fmtBytes(Math.abs(d)).replace(/^/, d < 0 ? '-' : '')}`) : null)));
  });
  vs.append(h('a', { class: 'btn sm', style: 'margin-left:auto;text-decoration:none', href: `/api/files/${rec.id}/download?v=${S.ver}` }, '⬇ DOWNLOAD v' + S.ver));
  if (rec.versions.length > 1) vs.append(h('button', { class: 'btn sm', onclick: () => { S.cmp = null; showTab('compare'); } }, '⇄ OLD vs NEW'));
  if (rec.kind === 'pdf') renderPdfPages(rec, v);
  else if (rec.kind === 'zip') renderZip(rec, v);
  else if (rec.kind === 'image') pg.append(h('img', { src: `/api/files/${rec.id}/v/${v.n}/raw`, style: 'grid-column:1/-1;max-width:100%;max-height:420px;justify-self:center' }));
  else pg.append(h('div', { class: 'bigkind' }, h('b', {}, rec.kind.toUpperCase()), rec.kind === 'docx' ? 'No page preview for Word files. Use CONVERT → Word to PDF, then edit the PDF.' : 'No preview for this file type.'));
}
function renderPdfPages(rec, v, opts = {}) {
  const pg = $('#pages'), reorder = S.op === 'reorder_pages';
  const tools = reorder
    ? h('div', { class: 'pgtools' }, 'Drag pages into the new order ·', h('button', { class: 'btn sm', onclick: () => { arrangePages(null); readOrder(); } }, 'RESET'), h('button', { class: 'btn sm', onclick: () => { arrangePages(Array.from({ length: v.pages }, (_, i) => v.pages - 1 - i)); readOrder(); } }, 'REVERSE'), h('span', { id: 'selInfo' }), h('span', { style: 'margin-left:auto' }, 'double-click = zoom'))
    : h('div', { class: 'pgtools' }, 'Click to select · shift-click for a range ·', h('button', { class: 'btn sm', onclick: () => { S.sel = new Set(Array.from({ length: v.pages }, (_, i) => i)); syncSel(); } }, 'ALL'), h('button', { class: 'btn sm', onclick: () => { S.sel.clear(); syncSel(); } }, 'NONE'), h('button', { class: 'btn sm', onclick: () => { S.sel = new Set(Array.from({ length: v.pages }, (_, i) => i).filter(i => !S.sel.has(i))); syncSel(); } }, 'INVERT'), h('span', { id: 'selInfo' }), h('span', { style: 'margin-left:auto' }, 'double-click = zoom'));
  pg.before(tools); const old = $('.pgtools'); if (old && old !== tools) old.remove();
  for (let i = 0; i < v.pages; i++) {
    const el = h('div', { class: 'pg' + (reorder ? ' drag' : S.sel.has(i) ? ' sel' : ''), 'data-i': i, onclick: reorder ? null : ev => pageClick(ev, i), ondblclick: () => zoom(`/api/files/${rec.id}/v/${v.n}/page/${i}.png?dpi=110`) },
      h('img', { loading: 'lazy', draggable: 'false', src: `/api/files/${rec.id}/v/${v.n}/page/${i}.png?dpi=45`, alt: 'page ' + (i + 1) }), h('span', { class: 'num' }, i + 1));
    if (reorder) pageDrag(el);
    pg.append(el);
  }
  // A fresh render shows the file's real order, so the order field starts empty too
  if (reorder) readOrder(); else syncSel(true);
}
// Reorder by dragging (pointer events, so mouse, touch and pen all work): the thumbnail
// moves live among the others, and the order field mirrors the result
function pageDrag(el) {
  el.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    // Listen on window, not with pointer capture: moving el in the DOM releases capture
    const sx = e.clientX, sy = e.clientY; let started = false;
    const move = ev => {
      if (!started) { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return; started = true; el.classList.add('dragging'); }
      const over = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('#pages .pg');
      if (!over || over === el) return;
      const r = over.getBoundingClientRect(), ref = ev.clientX > r.left + r.width / 2 ? over.nextSibling : over;
      if (ref !== el && ref !== el.nextSibling) over.parentNode.insertBefore(el, ref);
    };
    const up = () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up);
      if (started) { el.classList.remove('dragging'); readOrder(); }
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up);
  });
}
function arrangePages(order) { // order = zero-based page indexes; null = the file's own order
  const pg = $('#pages'), els = $$('#pages .pg'), byI = new Map(els.map(el => [+el.dataset.i, el]));
  (order || [...byI.keys()].sort((a, b) => a - b)).forEach(i => pg.append(byI.get(i)));
}
function readOrder(fill = true) {
  const els = $$('#pages .pg'), order = els.map(el => +el.dataset.i), same = order.every((x, k) => x === k);
  els.forEach((el, k) => el.classList.toggle('moved', +el.dataset.i !== k));
  const info = $('#selInfo'); if (info) info.textContent = same ? '' : ` new order: ${order.map(x => x + 1).join(', ')}`;
  const f = $('#opForm [data-p=order]'); if (fill && f) f.value = same ? '' : order.map(x => x + 1).join(',');
}
function orderSync(el) { // typed order -> thumbnails, once it is a complete order
  const n = $$('#pages .pg').length, raw = el.value.trim().toLowerCase(); if (!n) return;
  let order = null;
  if (raw === 'reverse') order = Array.from({ length: n }, (_, i) => n - 1 - i);
  else if (raw) { order = raw.split(/[,\s]+/).filter(Boolean).map(t => +t - 1); if (order.length !== n || [...order].sort((a, b) => a - b).some((x, k) => x !== k)) return; }
  arrangePages(order); readOrder(false);
}
function renderZip(rec, v) {
  api(`/api/files/${rec.id}/v/${v.n}/entries`).then(es => { const pg = $('#pages'); es.forEach(e => pg.append(h('div', { class: 'pg', title: e.name, ondblclick: () => zoom(`/api/files/${rec.id}/v/${v.n}/entry?name=${encodeURIComponent(e.name)}`) }, h('img', { loading: 'lazy', src: `/api/files/${rec.id}/v/${v.n}/entry?name=${encodeURIComponent(e.name)}` }), h('span', { class: 'num' }, e.name.replace(/^.*-p/, 'p'))))); });
}
function pageClick(ev, i) {
  if (ev.shiftKey && S.lastAnchor != null) { const [a, b] = [S.lastAnchor, i].sort((x, y) => x - y); for (let k = a; k <= b; k++) S.sel.add(k); }
  else { S.sel.has(i) ? S.sel.delete(i) : S.sel.add(i); S.lastAnchor = i; }
  syncSel();
}
function syncSel(noFill) {
  $$('#pages .pg').forEach(el => el.classList.toggle('sel', S.sel.has(+el.dataset.i)));
  const info = $('#selInfo'); if (info) info.textContent = S.sel.size ? ` selected: ${compressPages(S.sel)}` : '';
  if (!noFill) fillPagesField();
}
function fillPagesField() { const f = $('#opForm [data-p=pages]'); if (f && S.sel.size) { f.value = compressPages(S.sel); f.dispatchEvent(new Event('input')); } }
function zoom(src) { const lb = $('#lightbox'); lb.innerHTML = ''; lb.append(h('img', { src })); lb.hidden = false; lb.onclick = () => lb.hidden = true; }

// ------------------------------------------------------------------ workbench: op form
function renderForm() {
  const box = $('#opForm'); box.innerHTML = '';
  const o = S.ops[S.op]; if (!o) { box.append(h('h3', {}, h('span', {}, 'COMMAND')), h('div', { class: 'desc', style: 'margin:0 12px' }, 'Pick a tool on the left.')); return; }
  box.append(h('h3', {}, h('span', {}, 'COMMAND'), h('em', {}, o.id)), h('div', { class: 'fh', style: 'margin:0 12px' }, h('b', {}, o.label)), h('div', { class: 'desc', style: 'margin:0 12px 6px' }, o.desc));
  const rec = curRec();
  if (o.source === 'required' && !rec) box.append(h('div', { class: 'hint err' }, 'No file selected. Choose one in the FILES list.'));
  else if (rec && o.source !== 'none' && !o.accepts.includes(rec.kind)) box.append(h('div', { class: o.source === 'required' ? 'hint err' : 'hint' }, `Selected file is ${rec.kind.toUpperCase()}; this tool takes ${o.accepts.join('/').toUpperCase()}.` + (o.source === 'required' ? ' It will be rejected - the fault card will explain.' : ' It will be ignored; use the upload field.')));
  const fields = {};
  for (const p of o.params) {
    const f = h('div', { class: 'field', 'data-field': p.name });
    f.append(h('label', {}, p.label + (p.required ? ' *' : '')));
    let el;
    if (p.type === 'select') {
      el = h('div', { class: 'seg', 'data-p': p.name, 'data-val': p.default }, ...p.options.map(opt => h('button', { type: 'button', class: opt === p.default ? 'on' : '' }, opt)));
      el.onclick = ev => { const b = ev.target.closest('button'); if (!b) return; $$('button', el).forEach(x => x.classList.toggle('on', x === b)); el.dataset.val = b.textContent; updateShow(); };
    } else if (p.type === 'file') {
      el = h('div', { 'data-p': p.name, 'data-type': 'file' }, h('input', { type: 'file', accept: p.accept || '', multiple: !!p.multiple }));
      if (p.ws) { const sel = h('select', { 'data-ws': p.name }, h('option', { value: '' }, '- or pick from workspace -'), ...S.files.filter(x => x.kind === 'pdf' && x.id !== S.cur).map(x => h('option', { value: x.id }, x.name))); el.append(h('div', { style: 'height:5px' }), sel); }
    } else {
      el = h('input', { type: p.type === 'int' || p.type === 'float' ? 'number' : 'text', 'data-p': p.name, value: p.default ?? '', min: p.min, max: p.max, step: p.type === 'float' ? '0.5' : '1', placeholder: p.type === 'pages' ? 'e.g. 1,3,5-8 or all' : '' });
      if (p.type === 'pages') el.addEventListener('input', () => pageHint(el, rec));
      if (S.op === 'crop_pages' && ['top', 'right', 'bottom', 'left'].includes(p.name)) el.addEventListener('input', () => cropSync());
      if (S.op === 'reorder_pages' && p.name === 'order') el.addEventListener('input', () => orderSync(el));
    }
    f.append(el); if (p.help) f.append(h('div', { class: 'help' }, p.help)); box.append(f); fields[p.name] = { p, f };
  }
  const updateShow = () => { for (const { p, f } of Object.values(fields)) { if (!p.show_if) continue; f.style.display = Object.entries(p.show_if).every(([k, v]) => { const cur = readForm()[k]; return Array.isArray(v) ? v.includes(cur) : cur === v; }) ? '' : 'none'; } };
  if (S.op === 'crop_pages') box.insertBefore(cropWidget(rec), fields.unit.f);
  box.append(h('button', { class: 'btn-go', id: 'go', onclick: runOp }, 'EXECUTE'));
  updateShow(); fillPagesField();
}
function pageHint(el, rec) {
  let hint = el.parentElement.querySelector('.hint'); if (!hint) { hint = h('div', { class: 'hint' }); el.parentElement.append(hint); }
  const v = verRec(); if (!v || v.pages == null) return hint.remove();
  try { const n = parseSpec(el.value, v.pages); hint.className = 'hint'; hint.textContent = n.length ? `→ ${n.length} page(s): ${n.slice(0, 12).map(x => x + 1).join(', ')}${n.length > 12 ? '…' : ''}` : ''; } catch (e) { hint.className = 'hint err'; hint.textContent = e.message; }
}
function parseSpec(spec, n) { // mirror of server parse_pages, for instant feedback only (the server stays the authority)
  spec = (spec || '').trim().toLowerCase(); if (!spec || spec === 'all') return Array.from({ length: n }, (_, i) => i);
  const out = [];
  for (const tok of spec.split(/[,\s;]+/).filter(Boolean)) {
    const m = tok.match(/^(\d+|last)?(-)?(\d+|last)?$/); if (!m || !(m[1] || m[3])) throw new Error(`can't read '${tok}'`);
    const val = x => x === 'last' ? n : +x, lo = m[2] ? (m[1] ? val(m[1]) : 1) : val(m[1]), hi = m[2] ? (m[3] ? val(m[3]) : n) : lo;
    for (const p of [lo, hi]) if (p < 1 || p > n) throw new Error(`page ${p} is outside 1-${n}`);
    for (let k = Math.min(lo, hi); k <= Math.max(lo, hi); k++) out.push(k - 1);
  }
  return [...new Set(out)];
}
function readForm() {
  const o = {};
  $$('#opForm [data-p]').forEach(el => { const n = el.dataset.p; if (el.dataset.type === 'file') return; o[n] = el.classList.contains('seg') ? el.dataset.val : el.type === 'number' ? (el.value === '' ? null : +el.value) : el.value; });
  $$('#opForm select[data-ws]').forEach(s => { if (s.value) o[s.dataset.ws + '_ws'] = s.value; });
  return o;
}
function cropWidget(rec) {
  const v = verRec(); const wrap = h('div', { class: 'cropw' });
  if (!rec || rec.kind !== 'pdf') return h('div');
  const page = S.sel.size ? Math.min(...S.sel) : 0;
  const img = h('img', { src: `/api/files/${rec.id}/v/${v.n}/page/${page}.png?dpi=60` });
  const frame = h('div', { class: 'frame' }, ...['t', 'r', 'b', 'l'].map(k => h('div', { class: 'h ' + k, 'data-h': k })));
  wrap.append(img, frame, h('div', { class: 'help', style: 'position:absolute;left:6px;top:4px;font-size:10px;color:var(--cyan)' }, 'drag the green handles'));
  const m = { t: 0, r: 0, b: 0, l: 0 };
  const draw = () => { frame.style.inset = `${m.t}% ${m.r}% ${m.b}% ${m.l}%`; };
  wrap.cropSync = () => { const g = k => +($(`#opForm [data-p=${k}]`)?.value || 0); if ($('#opForm [data-p=unit]')?.dataset.val === 'percent') { m.t = g('top'); m.r = g('right'); m.b = g('bottom'); m.l = g('left'); draw(); } };
  frame.addEventListener('pointerdown', ev => {
    const k = ev.target.dataset.h; if (!k) return; ev.preventDefault(); frame.setPointerCapture(ev.pointerId);
    const move = e => {
      const r = wrap.getBoundingClientRect(), px = clamp((e.clientX - r.left) / r.width * 100, 0, 100), py = clamp((e.clientY - r.top) / r.height * 100, 0, 100);
      if (k === 't') m.t = clamp(py, 0, 100 - m.b - 5); if (k === 'b') m.b = clamp(100 - py, 0, 100 - m.t - 5); if (k === 'l') m.l = clamp(px, 0, 100 - m.r - 5); if (k === 'r') m.r = clamp(100 - px, 0, 100 - m.l - 5);
      draw();
      const unit = $('#opForm [data-p=unit]'); if (unit) { unit.dataset.val = 'percent'; $$('button', unit).forEach(b => b.classList.toggle('on', b.textContent === 'percent')); }
      for (const [kk, name] of [['t', 'top'], ['r', 'right'], ['b', 'bottom'], ['l', 'left']]) { const inp = $(`#opForm [data-p=${name}]`); if (inp) inp.value = m[kk].toFixed(1); }
    };
    const up = () => { frame.removeEventListener('pointermove', move); frame.removeEventListener('pointerup', up); };
    frame.addEventListener('pointermove', move); frame.addEventListener('pointerup', up);
  });
  draw(); wrap.id = 'cropw'; return wrap;
}
function cropSync() { const w = $('#cropw'); if (w && w.cropSync) w.cropSync(); }

// ------------------------------------------------------------------ run + animate
async function runOp() {
  const o = S.ops[S.op]; if (!o || S.busy) return;
  const params = readForm(), fd = new FormData(), rec = curRec();
  if (rec && o.source !== 'none') { fd.append('file_id', rec.id); fd.append('version', S.ver); }
  fd.append('params', JSON.stringify(params));
  $$('#opForm [data-type=file] input[type=file]').forEach(inp => [...inp.files].forEach(f => fd.append(inp.parentElement.dataset.p, f)));
  $('#fault').hidden = true; S.busy = true; $('#go').disabled = true; $('#go').textContent = 'EXECUTING…'; pipe.begin(o.label); showTrace(null); $('#insp').innerHTML = '<div class="nodeinfo">waiting for the server… (request sent, the stages light up as soon as it answers)</div>';
  const before = rec && verRec();
  try {
    const r = await api(`/api/ops/${o.id}`, { method: 'POST', form: fd, quiet: true });
    showTrace(r.trace); await pipe.play(r.trace, r.total_ms, false);
    await animateEdit(r, before);
    toast(`${r.message} · ${r.total_ms} ms`);
  } catch (e) {
    const d = e.payload; scope.busy(false);
    if (d && d.trace) { showTrace(d.trace); await pipe.play(d.trace, d.total_ms, true); }
    else pipe.quick('failed before reaching the server', false);
    showFault(d.error, null);
  } finally {
    S.busy = false; const go = $('#go'); if (go) { go.disabled = false; go.textContent = 'EXECUTE'; } refreshSystem(); pollLogs();
  }
}
async function animateEdit(r, before) {
  const pm = r.page_map, grid = $('#pages');
  if (r.mode === 'version') {
    // Phase 1: act on the OLD pages that are still on screen
    if (r.removed && r.removed.length) { r.removed.forEach(i => grid.querySelector(`.pg[data-i="${i}"]`)?.classList.add('exit-remove')); await sleep(900); }
    const crops = (pm || []).filter(x => x.state === 'cropped');
    if (crops.length) { crops.forEach(x => { const el = grid.querySelector(`.pg[data-i="${x.from}"]`); if (el && x.inset) { el.style.setProperty('--t', x.inset[0] + '%'); el.style.setProperty('--r', x.inset[1] + '%'); el.style.setProperty('--b', x.inset[2] + '%'); el.style.setProperty('--l', x.inset[3] + '%'); el.classList.add('crop-anim'); } }); await sleep(1300); }
    // Phase 2: swap in the new version; new pages fly in
    S.sel.clear(); S.cur = r.file.id; S.ver = r.to_version; S.files = S.files.map(f => f.id === r.file.id ? r.file : f); S.lastAnchor = null;
    renderFiles(); renderStage(); renderTools();
    $$('#pages .pg').forEach((el, i) => { const m = pm && pm[i]; el.classList.add(m && m.state === 'new' ? 'enter-new' : 'settle'); });
    const form = $('#opForm [data-p=pages]'); if (form && S.op !== 'crop_pages') form.value = '';
    pageHintRefresh();
  } else {
    if (r.highlight && S.cur) { r.highlight.forEach(i => $(`#pages .pg[data-i="${i}"]`)?.classList.add('extract-flash')); await sleep(700); }
    await loadFiles(r.file.id); renderFiles(r.file.id);
    $$('#pages .pg').forEach((el, i) => { el.classList.add('enter-new'); el.style.animationDelay = Math.min(i * 60, 600) + 'ms'; });
  }
}
function pageHintRefresh() { const f = $('#opForm [data-p=pages]'); if (f) f.dispatchEvent(new Event('input')); const cw = $('#cropw'); if (cw) { const img = cw.querySelector('img'), rec = curRec(), v = verRec(); if (img && v) img.src = `/api/files/${rec.id}/v/${v.n}/page/0.png?dpi=60`; } }

// ------------------------------------------------------------------ compare
function pdfVersions() { const out = []; for (const f of S.files) if (f.kind === 'pdf') for (const v of f.versions) out.push({ key: `${f.id}:${v.n}`, fid: f.id, v: v.n, label: `${f.name} · v${v.n} ${v.op} (${v.pages}p, ${fmtBytes(v.size)})` }); return out; }
function initCompare() {
  const root = $('#tab-compare'); root.innerHTML = '';
  const opts = pdfVersions(), rec = curRec();
  const panel = h('div', { class: 'panel' }, h('h3', {}, h('span', {}, 'COMPARE · OLD vs NEW'), h('em', {}, 'server aligns pages by content, then pixel-diffs matches')));
  if (opts.length < 2) { panel.append(h('div', { class: 'empty', style: 'margin:20px' }, 'Need two PDF versions. Edit a PDF (remove / add / crop) and you get v2 automatically, or upload two PDFs.')); root.append(panel); return; }
  let defA = opts[0], defB = opts[0];
  if (rec && rec.kind === 'pdf') { const cur = rec.versions.find(v => v.n === S.ver), prev = rec.versions[rec.versions.indexOf(cur) - 1] || rec.versions[0]; defA = opts.find(o => o.key === `${rec.id}:${prev.n}`); defB = opts.find(o => o.key === `${rec.id}:${cur.n}`); }
  const mk = (id, def) => h('select', { id }, ...opts.map(o => h('option', { value: o.key, selected: o.key === def.key }, o.label)));
  const sa = mk('cmpA', defA), sb = mk('cmpB', defB);
  const run = () => runCompare();
  sa.onchange = sb.onchange = run;
  panel.append(h('div', { class: 'cmpsel' }, h('div', { class: 'field', style: 'margin:0' }, h('label', {}, 'OLD (A)'), sa), h('div', { class: 'field', style: 'margin:0' }, h('label', {}, 'NEW (B)'), sb), h('button', { class: 'btn', onclick: () => { const t = sa.value; sa.value = sb.value; sb.value = t; run(); } }, '⇄ swap')), h('div', { id: 'cmpOut' }));
  root.append(panel); run();
}
async function runCompare() {
  const [fa, va] = $('#cmpA').value.split(':'), [fb, vb] = $('#cmpB').value.split(':'), out = $('#cmpOut'); out.innerHTML = '';
  out.append(h('div', { class: 'hint', style: 'margin:12px' }, 'comparing…')); pipe.begin('compare'); 
  let r; try { r = await api(`/api/compare?fa=${fa}&va=${va}&fb=${fb}&vb=${vb}`); } catch (e) { out.innerHTML = ''; pipe.quick('compare failed', false); return; }
  pipe.quick(`compare: ${r.rows.length} aligned rows in ${r.ms} ms (difflib on page hashes + 50-DPI pixel diff)`); scope.ping(r.ms);
  out.innerHTML = '';
  const d = (x, y) => y - x, sgn = n => (n > 0 ? '+' : '') + n;
  out.append(
    h('div', { class: 'stats' }, ...['same', 'changed', 'added', 'removed'].map(k => h('div', { class: 'stat ' + k }, h('small', {}, k.toUpperCase()), h('b', {}, r.counts[k])))),
    h('table', { class: 't' }, h('tr', {}, h('th', {}), h('th', {}, 'OLD'), h('th', {}, 'NEW'), h('th', {}, 'Δ')),
      h('tr', {}, h('td', {}, 'pages'), h('td', {}, r.a.pages), h('td', {}, r.b.pages), h('td', {}, sgn(d(r.a.pages, r.b.pages)))),
      h('tr', {}, h('td', {}, 'size'), h('td', {}, fmtBytes(r.a.size)), h('td', {}, fmtBytes(r.b.size)), h('td', {}, (d(r.a.size, r.b.size) > 0 ? '+' : '-') + fmtBytes(Math.abs(d(r.a.size, r.b.size))))),
      h('tr', {}, h('td', {}, 'page 1 size'), h('td', {}, r.a.page_size), h('td', {}, r.b.page_size), h('td', {}, r.a.page_size === r.b.page_size ? 'same' : 'DIFFERENT'))));
  const rows = h('div', { class: 'rows' }), view = h('div', {});
  r.rows.forEach((row, i) => rows.append(h('div', { class: 'rowc ' + row.status, 'data-i': i, onclick: () => pick(i) }, h('span', {}, `${row.a != null ? 'A' + (row.a + 1) : '—'} → ${row.b != null ? 'B' + (row.b + 1) : '—'}`), h('span', {}, row.status + (row.pixel_pct ? ' ' + row.pixel_pct + '%' : '')))));
  out.append(h('div', { class: 'cmpbody' }, rows, view));
  const img = (f, v, p) => p == null ? h('div', { class: 'none' }, 'no page') : h('img', { src: `/api/files/${f}/v/${v}/page/${p}.png?dpi=70` });
  async function pick(i) {
    $$('.rowc', rows).forEach(x => x.classList.toggle('on', +x.dataset.i === i)); const row = r.rows[i]; let blink = false;
    const diffSrc = row.a != null && row.b != null ? `/api/compare/diff.png?fa=${fa}&va=${va}&pa=${row.a}&fb=${fb}&vb=${vb}&pb=${row.b}` : null;
    const third = h('div', { class: 'pane' });
    const setThird = () => { third.innerHTML = ''; third.className = 'pane' + (blink ? ' blink' : ''); third.append(h('h4', {}, blink ? 'BLINK A/B' : 'DIFF  red=old only  green=new only', h('a', { href: '#', onclick: e => { e.preventDefault(); blink = !blink; setThird(); } }, blink ? 'show diff' : 'show blink')));
      if (blink) { third.append(img(fa, va, row.a), img(fb, vb, row.b)); } else third.append(diffSrc ? h('img', { src: diffSrc }) : h('div', { class: 'none' }, row.status === 'added' ? 'page only exists in NEW' : 'page only exists in OLD')); };
    setThird(); view.innerHTML = '';
    view.append(h('div', { class: 'panes' }, h('div', { class: 'pane' }, h('h4', {}, 'OLD ' + (row.a != null ? 'p' + (row.a + 1) : '')), img(fa, va, row.a)), h('div', { class: 'pane' }, h('h4', {}, 'NEW ' + (row.b != null ? 'p' + (row.b + 1) : '')), img(fb, vb, row.b)), third));
    const td = h('div', { class: 'tdiff' }, 'loading text diff…'); view.append(td);
    const t = await api(`/api/compare/text?fa=${fa}&va=${va}&fb=${fb}&vb=${vb}&pa=${row.a ?? -1}&pb=${row.b ?? -1}`, { quiet: true }).catch(() => null);
    td.innerHTML = ''; if (!t || !t.lines.length) td.append('no text differences' + (row.status === 'changed' ? ' (change is visual only: image, colour or layout)' : ''));
    else t.lines.forEach(l => td.append(h('div', { class: l[0] === '+' && !l.startsWith('+++') ? 'p' : l[0] === '-' && !l.startsWith('---') ? 'm' : l[0] === '@' ? 'h' : '' }, l)));
  }
  const first = r.rows.findIndex(x => x.status !== 'same'); if (r.rows.length) pick(first < 0 ? 0 : first);
}

// ------------------------------------------------------------------ share
function renderShare() {
  const root = $('#tab-share'); root.innerHTML = ''; const rec = curRec();
  const p = h('div', { class: 'panel' }, h('h3', {}, h('span', {}, 'RENAME & SHARE'), h('em', {}, rec ? `${rec.name} · v${S.ver}` : '')));
  if (!rec) { p.append(h('div', { class: 'empty', style: 'margin:20px' }, 'Select a file first.')); root.append(p); return; }
  const nm = h('input', { type: 'text', value: rec.name });
  const doRename = async () => { try { await api(`/api/files/${rec.id}`, { method: 'PATCH', json: { name: nm.value } }); pipe.quick('rename: display name changed in meta.json'); toast('renamed'); await loadFiles(); renderShare(); } catch (e) { } };
  nm.onkeydown = e => { if (e.key === 'Enter') doRename(); };
  const out = h('div', { id: 'shareOut' });
  p.append(h('div', { class: 'sharebox' },
    h('div', { class: 'field', style: 'margin:0' }, h('label', {}, '1 · FILE NAME (kept extension is added automatically)'), h('div', { class: 'urlbox' }, nm, h('button', { class: 'btn', onclick: doRename }, 'RENAME'))),
    h('div', { class: 'hint', style: 'margin:0' }, 'Backend: only the display name in meta.json changes. The file on disk stays <id>/vN.pdf, so two files with the same name can never collide.'),
    h('div', { class: 'field', style: 'margin:0' }, h('label', {}, '2 · SEND'), h('div', { class: 'plat' },
      h('button', { class: 'btn', onclick: () => makeLink() }, '🔗 Create link'),
      h('button', { class: 'btn wa', onclick: () => makeLink('whatsapp') }, 'WhatsApp'), h('button', { class: 'btn tg', onclick: () => makeLink('telegram') }, 'Telegram'), h('button', { class: 'btn gm', onclick: () => makeLink('gmail') }, 'Gmail'), h('button', { class: 'btn', onclick: () => makeLink('mailto') }, 'Mail app'),
      navigator.canShare ? h('button', { class: 'btn', onclick: nativeShare }, '📱 Share file (device menu)') : null)),
    h('div', { class: 'field', style: 'margin:0' }, h('label', {}, '3 · CLOUD'), h('div', { class: 'plat' },
      ...[['gdrive', 'Google Drive'], ['onedrive', 'OneDrive']].map(([k, n]) => h('button', { class: 'btn' + (S.integ[k]?.configured ? '' : ' notcfg'), onclick: () => cloud(k) }, n + (S.integ[k]?.configured ? '' : ' (not configured)'))))),
    out,
    h('div', { class: 'hint', style: 'margin:0' }, 'Backend: "Create link" stores a random token → (session, file, version) with an expiry. WhatsApp/Telegram/Gmail buttons just open those apps with the link pre-filled; they do not upload anything themselves. Links only work for other people if the server is reachable from the internet.')));
  root.append(p);
  async function makeLink(plat) {
    let r; try { r = await api(`/api/files/${rec.id}/share`, { method: 'POST', json: { v: S.ver } }); } catch (e) { return; }
    pipe.quick('share: token minted, expires ' + new Date(r.expires * 1000).toLocaleString());
    out.innerHTML = ''; out.append(h('div', { class: 'urlbox' }, h('input', { type: 'text', value: r.url, readonly: true, onclick: e => e.target.select() }), h('button', { class: 'btn', onclick: () => copy(r.url, 'link copied') }, 'COPY')), h('div', { class: 'hint' + (r.reachable ? '' : ' err'), style: 'margin:6px 0' }, r.warning || `Valid until ${new Date(r.expires * 1000).toLocaleString()}`));
    if (plat) window.open(r.links[plat], '_blank', 'noopener');
  }
  async function nativeShare() {
    try { const blob = await fetch(`/api/files/${rec.id}/download?v=${S.ver}`).then(r => r.blob()); const f = new File([blob], rec.name, { type: blob.type }); if (!navigator.canShare({ files: [f] })) throw new Error('This browser cannot share files. Use the link buttons.'); await navigator.share({ files: [f], title: rec.name }); }
    catch (e) { if (e.name !== 'AbortError') showFault({ code: 'E_WEBSHARE', title: 'Device share menu unavailable', cause: e.message + ' The Web Share API with files works on phones and some desktop browsers over HTTPS or localhost only.', fix: 'Use Create link instead.', frames: [], traceback: e.stack || '' }); }
  }
  async function cloud(k) { try { await api(`/api/files/${rec.id}/export/${k}`, { method: 'POST' }); } catch (e) { } }
}

// ------------------------------------------------------------------ system
let sysData = null;
async function refreshSystem() {
  try { sysData = await fetch('/api/system').then(r => r.json()); } catch (e) { return setLink(false); }
  const s = sysData; $('#sid').textContent = s.session_id.slice(0, 8); $('#ver').textContent = `signal-flow PDF workbench · v${s.app_version}`;
  const rows = [['working dir', s.cwd], ['app dir', s.app_dir], ['workspace', s.workspace], ['session dir', s.session_dir], ['session usage', fmtBytes(s.session_bytes)], ['disk free', `${fmtBytes(s.disk_free)} / ${fmtBytes(s.disk_total)}`],
    ['python', s.python], ['PyMuPDF', `${s.pymupdf} (MuPDF ${s.mupdf})`], ['LibreOffice', s.libreoffice || 'NOT INSTALLED'], ['platform', s.platform], ['pid · threads', `${s.pid} · ${s.threads}`], ['memory (RSS)', s.rss_mb + ' MB'], ['cpu', s.cpu_pct + ' %'],
    ['uptime', Math.floor(s.uptime_s / 60) + ' min ' + s.uptime_s % 60 + ' s'], ['requests · avg', `${s.requests} · ${s.avg_ms} ms`], ['max upload', s.limits.max_upload_mb + ' MB'], ['session TTL', s.limits.session_ttl_h + ' h'], ['share link TTL', s.limits.share_ttl_h + ' h']];
  const dl = $('#sys'); dl.innerHTML = '';
  rows.forEach(([k, v]) => { dl.append(h('dt', {}, k), h('dd', { title: 'click to copy', onclick: () => copy(String(v), k + ' copied') }, String(v))); });
  const used = (s.disk_total - s.disk_free) / s.disk_total * 100; dl.append(h('dt', {}, 'disk used'), h('dd', {}, h('div', { class: 'bar' }, h('i', { style: `width:${used.toFixed(1)}%` }))));
}

// ------------------------------------------------------------------ init
async function init() {
  const meta = await api('/api/ops'); S.nodes = meta.nodes; S.integ = meta.integrations;
  const order = ['CONVERT', 'PAGES']; S.ops = {}; meta.ops.forEach(o => S.ops[o.id] = o);
  S.order = meta.ops.slice().sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group)).map(o => o.id);
  S.op = 'remove_pages';
  pipe.build(); renderNodeInfo(); await refreshSystem(); await loadFiles(); showTab('work');
  const drop = $('#drop'), inp = $('#upInput');
  drop.onclick = e => { if (e.target !== inp) inp.click(); }; inp.onchange = () => { upload(inp.files); inp.value = ''; };
  ['dragover', 'dragenter'].forEach(ev => window.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => window.addEventListener(ev, e => { e.preventDefault(); if (ev === 'drop' || e.target === document.documentElement) drop.classList.remove('over'); if (ev === 'drop' && e.dataTransfer) upload(e.dataTransfer.files); }));
  $('#logErr').onchange = applyLogFilter;
  setInterval(pollLogs, 1500); setInterval(refreshSystem, 15000); pollLogs();
}
init();
