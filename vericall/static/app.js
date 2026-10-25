'use strict';
const $ = (id) => document.getElementById(id);
const state = { samples: [], selected: null, mode: 'samples', blob: null, running: false };
const verdictText = {
  fake: 'Posible deepfake detectado', real: 'Predicción: video original', unknown: 'Evidencia insuficiente'
};
const actionText = {
  bloquear_y_escalar: 'Bloquear y escalar', revisar_canal_alterno: 'Verificar por otro canal',
  autorizar_pendiente_confirmacion: 'Pendiente de confirmar por el analista'
};
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
  document.querySelectorAll('.sample-choice').forEach(button => {
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
function drawTimeline(detection) {
  const svg = $('timeline'); svg.replaceChildren();
  const ns = 'http://www.w3.org/2000/svg';
  function add(tag, attrs, content) {
    const el = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
    if (content !== undefined) el.textContent = content;
    svg.append(el); return el;
  }
  const x = t => 32 + t / Math.max(detection.duration_seconds, 0.01) * 666;
  const y = score => 128 - score * 112;
  for (const value of [0, .25, .5, .75, 1]) {
    add('line', {x1: 32, x2: 698, y1: y(value), y2: y(value), stroke: '#e4ecef', 'stroke-dasharray': '3 5'});
    add('text', {x: 22, y: y(value)+3, fill: '#899ca5', 'font-size': 10, 'text-anchor': 'end'}, String(value * 100));
  }
  let previous = null;
  for (const frame of detection.frames) {
    if (frame.fake_score === null) { previous = null; continue; }
    if (previous) add('line', {x1: x(previous.timestamp), y1: y(previous.fake_score), x2: x(frame.timestamp), y2: y(frame.fake_score), stroke: '#b3c8ce', 'stroke-width': 2});
    previous = frame;
  }
  for (const frame of detection.frames) {
    const score = frame.fake_score;
    const color = score === null ? '#d1dce1' : score >= .75 ? '#c75e5e' : score <= .25 ? '#16938c' : '#c1903b';
    const circle = add('circle', {cx: x(frame.timestamp), cy: score === null ? 136 : y(score), r: 4, fill: color, tabindex: 0, role: 'button', 'aria-label': `Ver instante ${frame.timestamp} segundos`});
    const title = document.createElementNS(ns, 'title'); title.textContent = `${frame.timestamp}s · ${score === null ? 'Sin rostro' : (score*100).toFixed(1)+'/100'}`; circle.append(title);
    circle.addEventListener('click', () => seek(frame.timestamp));
    circle.addEventListener('keydown', e => { if (e.key === 'Enter') seek(frame.timestamp); });
  }
  add('text', {x: 32, y: 155, fill: '#899ca5', 'font-size': 10}, '0 s');
  add('text', {x: 698, y: 155, fill: '#899ca5', 'font-size': 10, 'text-anchor': 'end'}, `${detection.duration_seconds.toFixed(1)} s`);
}
function showResult(entry) {
  const d = entry.detection, decision = entry.decision;
  $('empty-result').hidden = true; $('progress-panel').hidden = true; $('result-panel').hidden = false;
  $('verdict-title').textContent = verdictText[d.predicted_label];
  $('confidence-text').textContent = d.verdict === 'inconclusive' ? 'Resultado inconcluso para acreditar autenticidad: requiere revisión.' : d.verdict === 'likely_manipulated' ? 'Señal visual alta de manipulación facial.' : 'Señal visual baja. No equivale a una identidad verificada.';
  $('model-score').textContent = d.fake_score === null ? 'Sin puntuación' : `${(d.fake_score*100).toFixed(1)} / 100`;
  $('model-meter').style.width = `${(d.fake_score || 0)*100}%`;
  $('model-meter').style.background = d.fake_score >= .75 ? '#c75e5e' : d.fake_score > .25 ? '#c1903b' : '#16938c';
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
  drawTimeline(d);
  $('action-title').textContent = actionText[decision.action];
  $('risk-score').textContent = `${decision.score} / 100`;
  $('payment-decision').className = `payment-decision ${decision.action === 'bloquear_y_escalar' ? 'blocked' : decision.action === 'autorizar_pendiente_confirmacion' ? 'accept' : ''}`;
  $('reasons').replaceChildren(...decision.reasons.map(reason => node('li', `${reason.text}${reason.points ? ` (+${reason.points})` : ''}`)));
  const technical = $('technical-data'); technical.replaceChildren();
  for (const [key, value] of [['Decisión', entry.decision_id], ['Fecha UTC', entry.timestamp_utc], ['SHA-256 video', entry.video_sha256], ['Modelo', d.model.id], ['Revisión', d.model.revision], ['Pipeline', d.pipeline_version], ['Reglas', decision.rule_version], ['Video', `${d.width} × ${d.height} · ${d.fps} fps · ${d.duration_seconds} s`], ['Agregación', 'Media del máximo por rostro de cada instante'], ['Retención', 'Sin video ni recortes en la bitácora']]) {
    technical.append(node('dt', key), node('dd', value));
  }
  const body = $('frame-table'); body.replaceChildren();
  for (const frame of d.frames) {
    const row = node('tr');
    row.append(node('td', `${frame.timestamp.toFixed(2)} s`), node('td', frame.faces.length), node('td', frame.fake_score === null ? 'Sin rostro' : `${(frame.fake_score*100).toFixed(1)} / 100`));
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
      await new Promise(resolve => setTimeout(resolve, 700));
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

async function loadHistory() {
  const entries = await api('/api/history'); const body = $('history-body'); body.replaceChildren();
  if (!entries.length) { const row = node('tr'), cell = node('td', 'Aún no hay análisis. El primer resultado aparecerá aquí.'); cell.colSpan = 5; row.append(cell); body.append(row); return; }
  for (const entry of entries) {
    const row = node('tr');
    const date = new Date(entry.timestamp_utc).toLocaleString('es-CO', {timeZone: 'America/Bogota', dateStyle: 'short', timeStyle: 'short'});
    row.append(node('td', date), node('td', entry.sample_id || 'Video cargado'), node('td', entry.fake_score === null ? 'Sin evidencia' : `${(entry.fake_score*100).toFixed(1)} / 100`), node('td', actionText[entry.decision.action]));
    const cell = node('td'), link = node('a', 'JSON ↓'); link.href = `/api/decisions/${entry.decision_id}`; cell.append(link); row.append(cell); body.append(row);
  }
}
$('refresh-history').addEventListener('click', () => loadHistory().catch(err => error(err.message)));
async function initialize() {
  try {
    const [samples, health] = await Promise.all([api('/api/samples'), api('/health')]);
    state.samples = samples;
    $('model-status').replaceChildren(node('i'), document.createTextNode(health.model.available ? 'Modelo local instalado' : 'Modelo pendiente de instalar'));
    $('model-status').classList.toggle('ready', health.model.available);
    for (const sample of samples) {
      const button = node('button', undefined, `sample-choice ${sample.reference_label}`); button.type = 'button'; button.dataset.sample = sample.id; button.disabled = !sample.available;
      button.append(node('strong', `Persona ${sample.id.split('_')[1]}`), node('span', sample.reference_label === 'fake' ? 'Versión manipulada' : 'Original'));
      button.setAttribute('aria-pressed', 'false'); button.addEventListener('click', () => chooseSample(sample.id)); $('sample-grid').append(button);
    }
    const first = samples.find(sample => sample.available);
    if (first) chooseSample(first.id);
    else error('Faltan los videos públicos. Descárgalos con: python scripts/download_assets.py --only samples');
    if (!health.model.available) error('Faltan archivos del modelo. Instálalos con: python scripts/download_assets.py');
    await loadHistory();
  } catch (err) { error(err.message); }
}
initialize();
