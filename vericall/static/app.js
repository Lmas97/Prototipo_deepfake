'use strict';
const $ = (id) => document.getElementById(id);
const state = { samples: [], selected: null, mode: 'samples', blob: null, running: false };
const live = {
  source: 'simulated', sample: null, session: null, active: false, stream: null, startedAt: 0,
  frames: [], latencies: [], failures: 0, clock: null, alert: false, sawFace: false, sawMultiple: false, last: null
};
const FRAME_INTERVAL_MS = 500;
const verdictText = {
  fake: 'Posible deepfake detectado', real: 'Predicción: video original', unknown: 'Evidencia insuficiente'
};
const actionText = {
  bloquear_y_escalar: 'Bloquear y escalar', revisar_canal_alterno: 'Verificar por otro canal',
  autorizar_pendiente_confirmacion: 'Autorizar: el analista confirma'
};
const releaseRule = {
  autorizar_pendiente_confirmacion: 'Riesgo bajo: el analista confirma y el pago sale.',
  revisar_canal_alterno: 'Antes de liberar, verifica la solicitud por un canal alterno, como el número registrado del directivo.',
  bloquear_y_escalar: 'Bloqueo automático. Solo el área de seguridad puede liberarlo, tras verificar por canal alterno y sin ser quien solicitó la evaluación.'
};
const sourceText = { live: 'Llamada en vivo', sample: 'Ejemplo', upload: 'Video cargado' };
const liveSourceText = { simulated: 'llamada simulada', file: 'video propio', camera: 'cámara web', screen: 'ventana compartida' };

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function error(message) { $('global-error').textContent = message; $('global-error').hidden = !message; }
async function api(url, options) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { throw new Error('El servidor devolvió una respuesta inesperada. Revisa que siga ejecutándose.'); }
  if (!response.ok) throw new Error(payload.error || 'No se pudo completar la solicitud.');
  return payload;
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const clock = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const money = value => `$ ${Number(value).toLocaleString('es-CO', {maximumFractionDigits: 2})}`;
const scoreColor = score => score === null ? '#d1dce1' : score >= .75 ? '#c75e5e' : score <= .25 ? '#16938c' : '#c1903b';
const scoreText = score => score === null ? 'Sin rostro' : `${(score * 100).toFixed(1)} / 100`;

// ---------- Modo de trabajo ----------
function setWorkspace(mode) {
  for (const [id, active] of [['mode-live', mode === 'live'], ['mode-recording', mode === 'recording']]) {
    $(id).classList.toggle('active', active); $(id).setAttribute('aria-selected', String(active));
  }
  $('live-workspace').hidden = mode !== 'live'; $('recording-workspace').hidden = mode !== 'recording';
  error('');
}
$('mode-live').addEventListener('click', () => setWorkspace('live'));
$('mode-recording').addEventListener('click', () => { if (live.active) endCall(); setWorkspace('recording'); });

// ---------- Gráfico de señal ----------
function drawTimeline(svg, frames, start, end, onSelect) {
  svg.replaceChildren();
  const ns = 'http://www.w3.org/2000/svg';
  function add(tag, attrs, content) {
    const el = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
    if (content !== undefined) el.textContent = content;
    svg.append(el); return el;
  }
  const x = t => 32 + (t - start) / Math.max(end - start, 0.01) * 666;
  const y = score => 128 - score * 112;
  for (const value of [0, .25, .5, .75, 1]) {
    add('line', {x1: 32, x2: 698, y1: y(value), y2: y(value), stroke: '#e4ecef', 'stroke-dasharray': '3 5'});
    add('text', {x: 22, y: y(value)+3, fill: '#899ca5', 'font-size': 10, 'text-anchor': 'end'}, String(value * 100));
  }
  let previous = null;
  for (const frame of frames) {
    if (frame.fake_score === null) { previous = null; continue; }
    if (previous) add('line', {x1: x(previous.timestamp), y1: y(previous.fake_score), x2: x(frame.timestamp), y2: y(frame.fake_score), stroke: '#b3c8ce', 'stroke-width': 2});
    previous = frame;
  }
  for (const frame of frames) {
    const score = frame.fake_score;
    const attrs = {cx: x(frame.timestamp), cy: score === null ? 136 : y(score), r: onSelect ? 4 : 3, fill: scoreColor(score)};
    if (onSelect) Object.assign(attrs, {tabindex: 0, role: 'button', 'aria-label': `Ver instante ${frame.timestamp} segundos`});
    const circle = add('circle', attrs);
    const title = document.createElementNS(ns, 'title'); title.textContent = `${frame.timestamp.toFixed(1)} s · ${scoreText(score)}`; circle.append(title);
    if (onSelect) {
      circle.addEventListener('click', () => onSelect(frame.timestamp));
      circle.addEventListener('keydown', e => { if (e.key === 'Enter') onSelect(frame.timestamp); });
    }
  }
  add('text', {x: 32, y: 155, fill: '#899ca5', 'font-size': 10}, onSelect ? '0 s' : clock(start));
  add('text', {x: 698, y: 155, fill: '#899ca5', 'font-size': 10, 'text-anchor': 'end'}, onSelect ? `${end.toFixed(1)} s` : clock(end));
}

// ---------- Recomendación y decisión humana (común a ambos modos) ----------
function decisionClass(action) {
  return action === 'bloquear_y_escalar' ? 'blocked' : action === 'autorizar_pendiente_confirmacion' ? 'accept' : '';
}
function resolutionSummary(resolution) {
  const released = resolution.outcome === 'release';
  const box = node('div', undefined, `resolution-done ${released ? 'released' : 'rejected'}`);
  box.append(node('strong', released ? '✓ Pago liberado' : '✕ Pago rechazado'));
  const minutes = clock(resolution.elapsed_seconds);
  box.append(node('p', `${resolution.actor} (${resolution.role_label}) · ${minutes} desde la recomendación · ${resolution.within_sla ? 'dentro' : 'fuera'} del objetivo de 15 min`, 'hint'));
  if (resolution.alternate_channel) box.append(node('p', `Canal alterno: ${resolution.alternate_channel}`, 'hint'));
  return box;
}
function resolutionForm(entry, area, onResolved) {
  const action = entry.decision.action;
  const form = $('resolution-template').content.firstElementChild.cloneNode(true);
  form.querySelector('.rule').textContent = releaseRule[action];
  if (action === 'bloquear_y_escalar') form.elements.role.value = 'seguridad';
  else form.elements.actor.value = entry.analyst || '';
  const created = new Date(entry.timestamp_utc).getTime();
  const sla = form.querySelector('.sla');
  let timer = null;
  const tick = () => {
    if (!form.isConnected && timer) return clearInterval(timer);
    const seconds = Math.max(0, (Date.now() - created) / 1000);
    sla.textContent = `Pago retenido hace ${clock(seconds)} · objetivo de liberación ≤ 15:00`;
    sla.classList.toggle('late', seconds > 900);
  };
  form.addEventListener('submit', event => event.preventDefault());
  for (const button of form.querySelectorAll('[data-outcome]')) {
    button.addEventListener('click', async () => {
      const data = new FormData(form); data.set('outcome', button.dataset.outcome);
      const problem = form.querySelector('.form-error'); problem.hidden = true;
      form.querySelectorAll('button').forEach(b => { b.disabled = true; });
      try {
        const resolution = await api(`/api/decisions/${entry.decision_id}/resolution`, {method: 'POST', body: data});
        clearInterval(timer);
        area.replaceChildren(resolutionSummary(resolution));
        if (onResolved) onResolved(resolution);
        loadHistory().catch(() => {});
      } catch (err) {
        problem.textContent = err.message; problem.hidden = false;
        form.querySelectorAll('button').forEach(b => { b.disabled = false; });
      }
    });
  }
  area.replaceChildren(form);
  tick(); timer = setInterval(tick, 1000);
}
function decisionCard(entry, onResolved) {
  const decision = entry.decision;
  const box = node('div', undefined, `payment-decision ${decisionClass(decision.action)}`);
  const top = node('div', undefined, 'decision-top');
  top.append(node('p', entry.source === 'live' ? `TRANSFERENCIA SOLICITADA EN LA LLAMADA · ${new Date(entry.timestamp_utc).toLocaleTimeString('es-CO')}` : 'RECOMENDACIÓN PARA LA TRANSFERENCIA', 'eyebrow'));
  const link = node('a', 'Exportar JSON ↓', 'secondary'); link.href = `/api/decisions/${entry.decision_id}`; top.append(link);
  const heading = node('div', undefined, 'decision-heading');
  heading.append(node('h3', actionText[decision.action]), node('strong', `${decision.score} / 100`));
  const inputs = decision.inputs;
  const context = node('p', `${money(inputs.amount)} · límite ${money(inputs.limit)}${inputs.new_beneficiary ? ' · cuenta nueva' : ''} · evaluó ${entry.analyst || 'sin nombre'}`, 'hint');
  const reasons = node('ul');
  reasons.append(...decision.reasons.map(reason => node('li', `${reason.text}${reason.points ? ` (+${reason.points})` : ''}`)));
  const d = entry.detection;
  if (d.decision_basis) reasons.append(node('li', d.decision_basis === 'recent_window' ? 'Se usó la señal de los últimos segundos porque era más desfavorable que la de toda la llamada.' : 'Se usó la señal acumulada de toda la llamada.'));
  const area = node('div', undefined, 'resolution-area');
  box.append(top, heading, context, reasons, node('p', 'Recomendación de demostración. No ejecuta pagos ni confirma por sí sola la identidad del solicitante.', 'hint'), area);
  if (entry.resolution) area.append(resolutionSummary(entry.resolution));
  else resolutionForm(entry, area, onResolved);
  return box;
}

// ---------- Llamada en vivo ----------
function setLiveSource(source) {
  if (live.active) return;
  live.source = source;
  document.querySelectorAll('[data-source]').forEach(button => {
    const active = button.dataset.source === source;
    button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-source-panel]').forEach(panel => { panel.hidden = panel.dataset.sourcePanel !== source; });
}
document.querySelectorAll('[data-source]').forEach(button => button.addEventListener('click', () => setLiveSource(button.dataset.source)));
function chooseLiveSample(id) {
  if (live.active) return;
  live.sample = state.samples.find(sample => sample.id === id);
  clearOwnVideo();
  document.querySelectorAll('#live-sample-grid .sample-choice').forEach(button => {
    const selected = button.dataset.sample === id;
    button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected));
  });
}
function addEvent(text, kind = '') {
  const list = $('call-events');
  if (list.querySelector('.muted')) list.replaceChildren();
  const item = node('li', undefined, kind);
  item.append(node('time', clock(live.startedAt ? (performance.now() - live.startedAt) / 1000 : 0)), document.createTextNode(text));
  list.prepend(item);
}
function resetLiveView() {
  live.frames = []; live.latencies = []; live.alert = false; live.sawFace = false; live.sawMultiple = false; live.last = null;
  $('call-events').replaceChildren(node('li', 'Sin eventos todavía.', 'muted'));
  $('live-score').textContent = '—'; $('live-meter').style.width = '0';
  $('live-badge').textContent = 'Reuniendo evidencia'; $('live-badge').className = 'badge neutral';
  $('live-status-text').textContent = 'Salida del modelo sin calibrar. Una señal baja no verifica la identidad.';
  $('live-frames').textContent = '0'; $('live-coverage').textContent = '—'; $('live-latency').textContent = '—';
  $('live-alert').hidden = true; $('call-stage').classList.remove('alerting');
  $('live-timeline').replaceChildren(); clearOverlay();
}
function clearOverlay() {
  const canvas = $('live-overlay'); canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
}
function drawFaces(faces) {
  const video = $('live-video'), canvas = $('live-overlay');
  const width = canvas.clientWidth, height = canvas.clientHeight, ratio = window.devicePixelRatio || 1;
  if (canvas.width !== width * ratio || canvas.height !== height * ratio) { canvas.width = width * ratio; canvas.height = height * ratio; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  if (!video.videoWidth) return;
  // El video usa object-fit: contain; se reproduce el mismo encuadre.
  const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
  const shownW = video.videoWidth * scale, shownH = video.videoHeight * scale;
  const offsetX = (width - shownW) / 2, offsetY = (height - shownH) / 2;
  ctx.font = '600 12px Inter, -apple-system, sans-serif'; ctx.lineWidth = 2;
  for (const face of faces) {
    const [bx, by, bw, bh] = face.box;
    const left = offsetX + bx * shownW, top = offsetY + by * shownH, color = scoreColor(face.fake_score);
    ctx.strokeStyle = color; ctx.strokeRect(left, top, bw * shownW, bh * shownH);
    const label = `${Math.round(face.fake_score * 100)}`;
    const labelWidth = ctx.measureText(label).width + 12;
    ctx.fillStyle = color; ctx.fillRect(left, Math.max(0, top - 20), labelWidth, 20);
    ctx.fillStyle = '#fff'; ctx.fillText(label, left + 6, Math.max(14, top - 6));
  }
}
function captureFrame() {
  const video = $('live-video');
  if (video.readyState < 2 || !video.videoWidth) return Promise.resolve(null);
  const maxSide = live.source === 'screen' ? 1600 : 960;
  const scale = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
  const canvas = live.canvas || (live.canvas = document.createElement('canvas'));
  canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
}
function showLiveState(result) {
  const recent = result.recent_window, call = result.call;
  live.frames.push(result.frame);
  $('live-frames').textContent = String(call.sampled_frames);
  $('live-coverage').textContent = `${Math.round(call.face_coverage * 100)} %`;
  const latency = live.latencies.slice(-10).reduce((a, b) => a + b, 0) / Math.min(live.latencies.length, 10);
  $('live-latency').textContent = `${Math.round(latency)} ms`;
  const score = recent.fake_score;
  $('live-score').textContent = recent.sufficient_face_evidence ? scoreText(score) : (score === null ? 'Sin rostro' : 'Reuniendo…');
  $('live-meter').style.width = `${(recent.sufficient_face_evidence ? score : 0) * 100}%`;
  $('live-meter').style.background = scoreColor(score);
  const badge = $('live-badge');
  const [label, kind, text] = !recent.sufficient_face_evidence
    ? ['Reuniendo evidencia', 'neutral', 'Se necesitan al menos 4 cuadros con rostro y cobertura del 50 % en la ventana reciente.']
    : recent.verdict === 'likely_manipulated' ? ['Posible deepfake', 'fake strong', 'Señal visual alta de manipulación facial en los últimos segundos.']
    : recent.verdict === 'inconclusive' ? ['Zona incierta', 'warn', 'La señal está entre 25 y 75: no permite concluir autenticidad. Un pago irá a revisión.']
    : ['Sin señales fuertes', 'real', 'Señal baja. No equivale a una identidad verificada.'];
  badge.textContent = label; badge.className = `badge ${kind}`;
  $('live-status-text').textContent = text;
  drawFaces(result.frame.faces);
  const end = Math.max(result.elapsed_seconds, 10), start = Math.max(0, end - 120);
  drawTimeline($('live-timeline'), live.frames.filter(frame => frame.timestamp >= start), start, end, null);
  if (!live.sawFace && result.frame.faces.length) { live.sawFace = true; addEvent('Primer rostro detectado; comienza la evaluación.'); }
  if (!live.sawMultiple && result.frame.faces.length > 1) { live.sawMultiple = true; addEvent('Aparecen varios rostros: el sistema no sabe cuál es el solicitante.', 'warn'); }
  if (result.alert !== live.alert) {
    live.alert = result.alert;
    $('live-alert').hidden = !result.alert; $('call-stage').classList.toggle('alerting', result.alert);
    addEvent(result.alert ? `Alerta: señal alta de manipulación (${scoreText(score)}).` : 'La señal reciente bajó de la zona de alerta.', result.alert ? 'danger' : '');
  }
  const gate = $('evidence-gate');
  gate.textContent = call.sufficient_face_evidence
    ? `Evidencia suficiente: ${call.face_frames} cuadros con rostro.`
    : `Reuniendo evidencia: ${call.face_frames}/4 cuadros con rostro. Si evalúas ahora, el pago irá a revisión.`;
  gate.classList.toggle('ready', call.sufficient_face_evidence);
}
async function liveLoop(sessionId) {
  while (live.active && live.session === sessionId) {
    const started = performance.now();
    try {
      const blob = await captureFrame();
      if (blob) {
        const data = new FormData(); data.append('frame', blob, 'frame.jpg');
        const sent = performance.now();
        const result = await api(`/api/live/sessions/${sessionId}/frames`, {method: 'POST', body: data});
        if (!live.active || live.session !== sessionId) return;
        live.latencies.push(performance.now() - sent); live.failures = 0;
        showLiveState(result); live.last = result;
      }
    } catch (err) {
      live.failures += 1;
      if (live.failures >= 3) { error(`Se detuvo el monitoreo: ${err.message}`); endCall(); return; }
    }
    await sleep(Math.max(0, FRAME_INTERVAL_MS - (performance.now() - started)));
  }
}
function clearOwnVideo() {
  if (live.own) URL.revokeObjectURL(live.own.url);
  live.own = null; $('live-file').value = ''; $('live-file-name').hidden = true;
}
async function sha256(file) {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
$('live-file').addEventListener('change', async () => {
  const file = $('live-file').files[0];
  if (!file) return;
  if (file.size > 300 * 1024 * 1024) { error('Usa un video de hasta 300 MB.'); $('live-file').value = ''; return; }
  const url = URL.createObjectURL(file);
  if (live.own) URL.revokeObjectURL(live.own.url);
  live.sample = null;
  document.querySelectorAll('#live-sample-grid .sample-choice').forEach(button => { button.classList.remove('selected'); button.setAttribute('aria-pressed', 'false'); });
  $('live-file-name').hidden = false; $('live-file-name').textContent = `${file.name} · calculando huella…`;
  live.own = {url, name: file.name, hash: null};
  const own = live.own;
  try { own.hash = await sha256(file); } catch { error('No se pudo leer el video.'); clearOwnVideo(); return; }
  if (live.own === own) $('live-file-name').textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB · SHA-256 ${own.hash.slice(0, 12)}…`;
});
async function openSource() {
  const video = $('live-video');
  video.srcObject = null; video.removeAttribute('src');
  if (live.source === 'simulated') {
    video.src = live.own ? live.own.url : live.sample.media_url; video.loop = true;
  } else {
    if (!navigator.mediaDevices) throw new Error('Este navegador no permite capturar video. Abre la aplicación en http://127.0.0.1:5000.');
    live.stream = live.source === 'camera'
      ? await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}}, audio: false})
      : await navigator.mediaDevices.getDisplayMedia({video: {frameRate: 10}, audio: false});
    live.stream.getVideoTracks()[0].addEventListener('ended', () => { if (live.active) { addEvent('Se dejó de compartir la fuente.'); endCall(); } });
    video.srcObject = live.stream;
  }
  await video.play();
}
async function connectCall() {
  error('');
  const data = new FormData();
  const source = live.source === 'simulated' && live.own ? 'file' : live.source;
  data.set('consent', 'yes'); data.set('source', source); data.set('caller', $('caller').value);
  if (source === 'simulated') data.set('sample_id', live.sample.id);
  if (source === 'file') data.set('video_sha256', live.own.hash);
  resetLiveView(); live.startedAt = 0;
  try {
    await openSource();
    const session = await api('/api/live/sessions', {method: 'POST', body: data});
    Object.assign(live, {session: session.session_id, active: true, startedAt: performance.now(), failures: 0});
    $('live-setup').disabled = true; $('live-start').hidden = true; $('live-end').hidden = false;
    $('live-transfer-fields').disabled = false;
    $('call-placeholder').hidden = true; $('call-hud').hidden = false; $('call-caller').hidden = false;
    $('call-caller-name').textContent = $('caller').value || 'Interlocutor sin identificar';
    live.clock = setInterval(() => { $('call-clock').textContent = clock((performance.now() - live.startedAt) / 1000); }, 500);
    const detail = source === 'simulated' ? ` · Persona ${live.sample.id.split('_')[1]}` : source === 'file' ? ` · ${live.own.name}` : '';
    addEvent(`Llamada conectada (${liveSourceText[source]}${detail}).`);
    liveLoop(session.session_id);
  } catch (err) {
    stopMedia();
    error(err.name === 'NotAllowedError' ? 'No se otorgó permiso para capturar video. Autoriza la cámara o la pantalla en el navegador.' : err.message);
  }
}
function stopMedia() {
  const video = $('live-video');
  video.pause();
  if (live.stream) { live.stream.getTracks().forEach(track => track.stop()); live.stream = null; }
  video.srcObject = null; video.removeAttribute('src'); video.load();
}
function endCall() {
  if (!live.active) return;
  const session = live.session;
  live.active = false; clearInterval(live.clock);
  addEvent('Llamada finalizada. Las imágenes no se guardaron.');
  stopMedia(); clearOverlay();
  live.alert = false; $('live-alert').hidden = true; $('call-stage').classList.remove('alerting');
  fetch(`/api/live/sessions/${session}/end`, {method: 'POST'}).catch(() => {});
  live.session = null;
  $('live-setup').disabled = false; $('live-start').hidden = false; $('live-end').hidden = true;
  $('live-transfer-fields').disabled = true;
  $('call-hud').hidden = true; $('call-caller').hidden = true; $('call-placeholder').hidden = false;
  $('evidence-gate').textContent = 'Inicia la llamada para reunir evidencia.'; $('evidence-gate').classList.remove('ready');
}
$('live-start').addEventListener('click', () => {
  if (!$('live-consent').checked) { error('Confirma que los participantes autorizaron el análisis de la llamada.'); return; }
  if (live.source === 'simulated') {
    if (!live.sample && !live.own) { error('Elige un video público o carga uno propio para simular la llamada.'); return; }
    if (live.own && !live.own.hash) { error('Espera a que termine de calcularse la huella del video.'); return; }
    $('incoming-name').textContent = $('caller').value || 'Interlocutor sin identificar';
    $('call-placeholder').hidden = true; $('incoming').hidden = false; $('live-start').disabled = true;
    return;
  }
  connectCall();
});
$('incoming-accept').addEventListener('click', () => { $('incoming').hidden = true; $('live-start').disabled = false; connectCall(); });
$('incoming-decline').addEventListener('click', () => { $('incoming').hidden = true; $('live-start').disabled = false; $('call-placeholder').hidden = false; });
$('live-end').addEventListener('click', endCall);
window.addEventListener('pagehide', () => { if (live.session) navigator.sendBeacon(`/api/live/sessions/${live.session}/end`); });
window.addEventListener('resize', () => { if (live.last) drawFaces(live.last.frame.faces); });
$('live-transfer-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!live.session) return; error('');
  const fields = $('live-transfer-fields'); fields.disabled = true;
  try {
    const entry = await api(`/api/live/sessions/${live.session}/transfer`, {method: 'POST', body: new FormData(event.target)});
    addEvent(`Transferencia de ${money(entry.decision.inputs.amount)} evaluada: ${actionText[entry.decision.action]} (${entry.decision.score}/100).`,
      entry.decision.action === 'bloquear_y_escalar' ? 'danger' : entry.decision.action === 'revisar_canal_alterno' ? 'warn' : 'ok');
    const card = node('section', undefined, 'panel'); card.append(decisionCard(entry, resolution => {
      addEvent(`Pago ${resolution.outcome === 'release' ? 'liberado' : 'rechazado'} por ${resolution.actor} (${resolution.role_label}).`, resolution.outcome === 'release' ? 'ok' : 'danger');
    }));
    $('live-decisions').prepend(card);
    card.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    await loadHistory();
  } catch (err) { error(err.message); }
  finally { fields.disabled = !live.active; }
});

// ---------- Análisis de grabaciones ----------
function resetResult() {
  $('result-panel').hidden = true; $('empty-result').hidden = false;
  $('progress-panel').hidden = true; error('');
}
function setPreview(url, label, type = 'neutral') {
  $('preview').src = url;
  $('preview-placeholder').hidden = true;
  $('reference-label').textContent = label;
  $('reference-label').className = `badge ${type}`;
}
function chooseSample(id) {
  if (state.running) return;
  state.selected = state.samples.find(sample => sample.id === id);
  document.querySelectorAll('#sample-grid .sample-choice').forEach(button => {
    const selected = button.dataset.sample === id;
    button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected));
  });
  resetResult();
  const label = state.selected.reference_label;
  setPreview(state.selected.media_url, label === 'fake' ? 'Referencia: manipulado' : 'Referencia: original', label);
  $('video-caption').textContent = 'Etiqueta proporcionada por el editor del dataset. El detector solo recibe los píxeles del video.';
}
function setMode(mode) {
  if (state.running) return;
  state.mode = mode;
  $('sample-section').hidden = mode !== 'samples'; $('upload-section').hidden = mode !== 'custom';
  for (const [id, active] of [['samples-tab', mode === 'samples'], ['upload-tab', mode === 'custom']]) {
    $(id).classList.toggle('active', active); $(id).setAttribute('aria-selected', String(active));
  }
  resetResult();
  if (mode === 'samples' && state.selected) chooseSample(state.selected.id);
  else if (state.blob) setPreview(state.blob, 'Video cargado');
  else {
    $('preview').removeAttribute('src'); $('preview').load(); $('preview-placeholder').hidden = false;
    $('reference-label').textContent = 'Video propio'; $('reference-label').className = 'badge neutral';
    $('video-caption').textContent = 'La vista previa depende del códec admitido por el navegador. Puedes analizar el archivo aunque no se reproduzca aquí.';
  }
}
$('samples-tab').addEventListener('click', () => setMode('samples'));
$('upload-tab').addEventListener('click', () => setMode('custom'));
$('video-file').addEventListener('change', () => {
  resetResult();
  const file = $('video-file').files[0];
  if (state.blob) URL.revokeObjectURL(state.blob);
  state.blob = null;
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) { error('El video supera los 100 MB admitidos.'); $('video-file').value = ''; return; }
  state.blob = URL.createObjectURL(file);
  setPreview(state.blob, 'Video cargado');
  $('filename').textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB. Se elimina del servidor al terminar.`;
});
$('preview').addEventListener('error', () => {
  if ($('preview').getAttribute('src')) $('video-caption').textContent = 'Este navegador no puede reproducir el códec. El servidor puede analizarlo si OpenCV lo admite.';
});

function seek(seconds) {
  const video = $('preview');
  if (video.readyState >= 1) { video.pause(); video.currentTime = seconds; }
}
function showResult(entry) {
  const d = entry.detection;
  $('empty-result').hidden = true; $('progress-panel').hidden = true; $('result-panel').hidden = false;
  $('verdict-title').textContent = verdictText[d.predicted_label];
  $('confidence-text').textContent = d.verdict === 'inconclusive' ? 'Resultado inconcluso para acreditar autenticidad: requiere revisión.' : d.verdict === 'likely_manipulated' ? 'Señal visual alta de manipulación facial.' : 'Señal visual baja. No equivale a una identidad verificada.';
  $('model-score').textContent = d.fake_score === null ? 'Sin puntuación' : `${(d.fake_score*100).toFixed(1)} / 100`;
  $('model-meter').style.width = `${(d.fake_score || 0)*100}%`;
  $('model-meter').style.background = scoreColor(d.fake_score);
  $('face-count').textContent = `${d.face_frames} / ${d.sampled_frames}`;
  $('coverage').textContent = `${(d.face_coverage*100).toFixed(0)} %`;
  $('elapsed').textContent = `${d.elapsed_seconds.toFixed(1)} s`;
  $('export-link').href = `/api/decisions/${entry.decision_id}`;
  const sample = state.samples.find(s => s.id === entry.sample_id);
  $('reference-comparison').hidden = !sample;
  if (sample) {
    const match = d.predicted_label === sample.reference_label;
    $('reference-comparison').className = `comparison ${match ? '' : 'mismatch'}`;
    $('reference-comparison').textContent = d.predicted_label === 'unknown'
      ? 'La muestra tiene etiqueta de referencia, pero la evidencia disponible no permitió clasificarla.'
      : match ? 'La clasificación coincide con la etiqueta del editor en este ejemplo. Esto no demuestra desempeño en otros videos.'
      : `La clasificación no coincide con la etiqueta del editor: ${sample.reference_label === 'fake' ? 'un deepfake no detectado' : 'un falso positivo'} en esta muestra.`;
  }
  drawTimeline($('timeline'), d.frames, 0, d.duration_seconds, seek);
  $('recording-decision').replaceChildren(decisionCard(entry));
  const technical = $('technical-data'); technical.replaceChildren();
  for (const [key, value] of [['Decisión', entry.decision_id], ['Fecha UTC', entry.timestamp_utc], ['SHA-256 video', entry.video_sha256], ['Modelo', d.model.id], ['Revisión', d.model.revision], ['Pipeline', d.pipeline_version], ['Reglas', entry.decision.rule_version], ['Video', `${d.width} × ${d.height} · ${d.fps} fps · ${d.duration_seconds} s`], ['Agregación', 'Media del máximo por rostro de cada instante'], ['Retención', 'Sin video ni recortes en la bitácora'], ['Sello en bitácora', entry.integrity ? `#${entry.integrity.seq} · ${entry.integrity.hash}` : '—']]) {
    technical.append(node('dt', key), node('dd', value));
  }
  const body = $('frame-table'); body.replaceChildren();
  for (const frame of d.frames) {
    const row = node('tr');
    row.append(node('td', `${frame.timestamp.toFixed(2)} s`), node('td', frame.faces.length), node('td', scoreText(frame.fake_score)));
    const cell = node('td'), button = node('button', 'Ver'); button.type = 'button'; button.addEventListener('click', () => seek(frame.timestamp)); cell.append(button); row.append(cell); body.append(row);
  }
}

$('analysis-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.running) return; error('');
  const data = new FormData(event.target);
  data.set('sample_id', state.mode === 'samples' && state.selected ? state.selected.id : 'custom');
  if (state.mode === 'custom') {
    const file = $('video-file').files[0]; if (!file) { error('Selecciona un video para analizar.'); return; }
    data.set('video', file);
  }
  state.running = true; $('form-fields').disabled = true;
  $('result-panel').hidden = true; $('empty-result').hidden = true; $('progress-panel').hidden = false;
  $('progress-bar').value = 0; $('progress-percent').textContent = '0 %'; $('progress-message').textContent = 'Enviando video';
  try {
    const submitted = await api('/api/analyses', { method: 'POST', body: data });
    let job;
    do {
      await sleep(700);
      job = await api(submitted.status_url);
      $('progress-message').textContent = job.message;
      $('progress-percent').textContent = `${job.progress} %`; $('progress-bar').value = job.progress;
    } while (job.status === 'queued' || job.status === 'running');
    if (job.status === 'failed') throw new Error(job.message);
    showResult(job.result); await loadHistory();
  } catch (err) {
    error(err.message); $('progress-panel').hidden = true; $('empty-result').hidden = false;
  } finally { state.running = false; $('form-fields').disabled = false; }
});

// ---------- Bitácora ----------
async function loadIntegrity() {
  const result = await api('/api/audit/verify');
  const status = $('integrity-status');
  status.classList.toggle('ready', result.valid); status.classList.toggle('broken', !result.valid);
  status.replaceChildren(node('i'), document.createTextNode(result.valid ? `Bitácora íntegra · ${result.records}` : 'Bitácora alterada'));
  $('integrity-detail').textContent = result.valid
    ? `Verificación actual: ${result.records} registros encadenados, sin alteraciones.`
    : `Verificación actual: la cadena se rompe en el registro #${result.first_invalid_seq}.`;
  $('integrity-detail').className = result.valid ? 'ok-text' : 'bad-text';
}
async function loadHistory() {
  const entries = await api('/api/history'); const body = $('history-body'); body.replaceChildren();
  loadIntegrity().catch(() => {});
  if (!entries.length) { const row = node('tr'), cell = node('td', 'Aún no hay decisiones. La primera aparecerá aquí.'); cell.colSpan = 6; row.append(cell); body.append(row); return; }
  for (const entry of entries) {
    const row = node('tr');
    const date = new Date(entry.timestamp_utc).toLocaleString('es-CO', {timeZone: 'America/Bogota', dateStyle: 'short', timeStyle: 'short'});
    const origin = entry.source === 'live' ? `${sourceText.live} · ${entry.caller || ''}` : entry.sample_id ? `${sourceText.sample} · ${entry.sample_id}` : sourceText.upload;
    const resolution = entry.resolution;
    const final = resolution ? `${resolution.outcome === 'release' ? 'Liberado' : 'Rechazado'} · ${resolution.actor} · ${clock(resolution.elapsed_seconds)}` : 'Pendiente';
    row.append(node('td', date), node('td', origin), node('td', entry.fake_score === null ? 'Sin evidencia' : scoreText(entry.fake_score)),
      node('td', actionText[entry.decision.action] || entry.decision.action), node('td', final, resolution ? '' : 'pending'));
    const cell = node('td'), link = node('a', 'JSON ↓'); link.href = `/api/decisions/${entry.decision_id}`; cell.append(link); row.append(cell); body.append(row);
  }
}
$('refresh-history').addEventListener('click', () => loadHistory().catch(err => error(err.message)));

function sampleButton(sample, onChoose) {
  const button = node('button', undefined, `sample-choice ${sample.reference_label}`); button.type = 'button'; button.dataset.sample = sample.id; button.disabled = !sample.available;
  button.append(node('strong', `Persona ${sample.id.split('_')[1]}`), node('span', sample.reference_label === 'fake' ? 'Versión manipulada' : 'Original'));
  button.setAttribute('aria-pressed', 'false'); button.addEventListener('click', () => onChoose(sample.id));
  return button;
}
async function initialize() {
  try {
    const [samples, health] = await Promise.all([api('/api/samples'), api('/health')]);
    state.samples = samples;
    $('model-status').replaceChildren(node('i'), document.createTextNode(health.model.available ? 'Modelo local instalado' : 'Modelo pendiente de instalar'));
    $('model-status').classList.toggle('ready', health.model.available);
    for (const sample of samples) {
      $('sample-grid').append(sampleButton(sample, chooseSample));
      $('live-sample-grid').append(sampleButton(sample, chooseLiveSample));
    }
    const first = samples.find(sample => sample.available);
    if (first) { chooseSample(first.id); chooseLiveSample((samples.find(s => s.available && s.reference_label === 'fake') || first).id); }
    else error('Faltan los videos públicos. Descárgalos con: python scripts/download_assets.py --only samples');
    if (!health.model.available) error('Faltan archivos del modelo. Instálalos con: python scripts/download_assets.py');
    await loadHistory();
  } catch (err) { error(err.message); }
}
initialize();
