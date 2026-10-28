const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const video = $('#sequence-video');
const overlay = $('#pose-canvas');
const ctx = overlay.getContext('2d');
const chart = $('#trace-chart');
const chartCtx = chart.getContext('2d');
const slider = $('#frame-slider');
const COLORS = { FBF: '#19dcb4', PCH: '#62abff', GT: '#ff7669' };
let manifest, clip, payload, frameIndex = 0, selectedTool = 'both', chartMaximum = 100;
let loadingVersion = 0;

async function loadJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`无法载入 ${path} (${response.status})`);
  return response.json();
}

function toolsToShow() { return selectedTool === 'both' ? ['FBF', 'PCH'] : [selectedTool]; }
function format(value) { return value == null ? '—' : value.toFixed(1); }

function drawOverlay() {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (!payload) return;
  const frame = payload.frames[frameIndex];
  for (const tool of toolsToShow()) {
    const record = frame.instruments[tool];
    const category = payload.categories[tool];
    const points = record.predicted_xy;
    if ($('#show-trails').checked && $('#show-prediction').checked) {
      const tips = tool === 'FBF' ? [3, 4] : [5];
      for (const pointIndex of tips) {
        for (let i = Math.max(1, frameIndex - 15); i <= frameIndex; i++) {
          const previous = payload.frames[i - 1], current = payload.frames[i];
          if (current.source_frame !== previous.source_frame + 1) continue;
          const a = previous.instruments[tool].predicted_xy[pointIndex];
          const b = current.instruments[tool].predicted_xy[pointIndex];
          ctx.globalAlpha = 0.15 + 0.55 * (1 - (frameIndex - i) / 15);
          ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b);
          ctx.strokeStyle = COLORS[tool]; ctx.lineWidth = 3; ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
    }
    if ($('#show-boxes').checked) {
      ctx.setLineDash([8, 6]); ctx.lineWidth = 2; ctx.strokeStyle = COLORS[tool];
      ctx.strokeRect(...record.bbox); ctx.setLineDash([]);
    }
    if ($('#show-prediction').checked) {
      ctx.lineWidth = 2.6; ctx.lineJoin = 'round'; ctx.strokeStyle = COLORS[tool];
      for (const [start, end] of category.skeleton) {
        ctx.beginPath(); ctx.moveTo(...points[start - 1]); ctx.lineTo(...points[end - 1]); ctx.stroke();
      }
      points.forEach(([x, y], i) => {
        ctx.beginPath(); ctx.arc(x, y, 4.8, 0, Math.PI * 2); ctx.fillStyle = COLORS[tool]; ctx.fill();
        ctx.strokeStyle = '#112c20'; ctx.lineWidth = 1; ctx.stroke();
        if ($('#show-labels').checked) {
          ctx.font = '15px Arial'; ctx.lineWidth = 3; ctx.strokeStyle = '#0b1c16';
          ctx.strokeText(category.keypoints[i], x + 9, y - 9);
          ctx.fillStyle = COLORS[tool]; ctx.fillText(category.keypoints[i], x + 9, y - 9);
        }
      });
    }
    if ($('#show-gt').checked) {
      for (const [x, y, visible] of record.ground_truth_xyv) {
        if (!visible) continue;
        ctx.lineWidth = 2.2;
        ctx.strokeStyle = visible === 2 ? COLORS.GT : '#edc76a';
        ctx.beginPath();
        if (visible === 2) {
          ctx.moveTo(x - 6, y); ctx.lineTo(x + 6, y); ctx.moveTo(x, y - 6); ctx.lineTo(x, y + 6);
        } else { ctx.arc(x, y, 5, 0, Math.PI * 2); }
        ctx.stroke();
      }
    }
  }
}

function drawChart() {
  if (!payload) return;
  const w = chart.width, h = chart.height, left = 37, right = 12, top = 12, bottom = 20;
  chartCtx.clearRect(0, 0, w, h);
  chartMaximum = Math.ceil(Math.max(10, ...payload.frames.flatMap(f => toolsToShow().map(t => f.instruments[t].mean_visible_error_px || 0))) / 10) * 10;
  chartCtx.font = '11px Arial'; chartCtx.lineWidth = 1;
  for (const value of [0, chartMaximum / 2, chartMaximum]) {
    const y = h - bottom - value / chartMaximum * (h - top - bottom);
    chartCtx.strokeStyle = '#31483c'; chartCtx.beginPath(); chartCtx.moveTo(left, y); chartCtx.lineTo(w - right, y); chartCtx.stroke();
    chartCtx.fillStyle = '#90a894'; chartCtx.textAlign = 'right'; chartCtx.fillText(`${Math.round(value)}`, left - 9, y + 4);
  }
  for (const tool of toolsToShow()) {
    chartCtx.strokeStyle = COLORS[tool]; chartCtx.lineWidth = 1.7; chartCtx.beginPath();
    let started = false;
    payload.frames.forEach((f, i) => {
      const value = f.instruments[tool].mean_visible_error_px;
      if (value == null) { started = false; return; }
      const x = left + i / (payload.frames.length - 1) * (w - left - right);
      const y = h - bottom - value / chartMaximum * (h - top - bottom);
      started ? chartCtx.lineTo(x, y) : chartCtx.moveTo(x, y); started = true;
    });
    chartCtx.stroke();
  }
  const position = left + frameIndex / (payload.frames.length - 1) * (w - left - right);
  chartCtx.strokeStyle = '#d6ef9c'; chartCtx.setLineDash([3, 4]); chartCtx.beginPath();
  chartCtx.moveTo(position, top); chartCtx.lineTo(position, h - bottom); chartCtx.stroke(); chartCtx.setLineDash([]);
  chartCtx.fillStyle = '#9caf9d'; chartCtx.textAlign = 'left'; chartCtx.fillText('001', left, h - 3);
  chartCtx.textAlign = 'right'; chartCtx.fillText(String(payload.frames.length), w - right, h - 3);
}

function updateFrame(index) {
  if (!payload) return;
  frameIndex = Math.max(0, Math.min(payload.frames.length - 1, index));
  slider.value = frameIndex;
  const frame = payload.frames[frameIndex];
  $('#frame-counter').textContent = `${String(frameIndex + 1).padStart(3, '0')} / ${payload.frames.length}`;
  $('#source-frame').textContent = String(frame.source_frame).padStart(6, '0');
  $('#stage-frame').textContent = `FRAME ${String(frame.source_frame).padStart(6, '0')}`;
  $('#fbf-error').textContent = format(frame.instruments.FBF.mean_visible_error_px);
  $('#pch-error').textContent = format(frame.instruments.PCH.mean_visible_error_px);
  const records = toolsToShow().map(tool => frame.instruments[tool]).filter(r => r.visible_count > 0);
  const count = records.reduce((sum, r) => sum + r.visible_count, 0);
  const average = count ? records.reduce((sum, r) => sum + r.mean_visible_error_px * r.visible_count, 0) / count : null;
  $('#current-error').innerHTML = `${format(average)} <small>px</small>`;
  drawOverlay(); drawChart();
}

function seek(index) {
  if (!payload) return;
  video.pause();
  const target = Math.max(0, Math.min(payload.frames.length - 1, index));
  video.currentTime = (target + 0.2) / manifest.playback_fps;
  updateFrame(target);
}

async function setClip(id) {
  const version = ++loadingVersion;
  video.pause(); payload = null; $('#play-button').disabled = true;
  $('#stage-status').textContent = '载入片段…'; $('#viewer-error').hidden = true;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  const nextClip = manifest.clips.find(c => c.id === id);
  if (!nextClip) return;
  $$('.clip-tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.clip === id)));
  try {
    const nextPayload = await loadJSON(nextClip.data);
    if (version !== loadingVersion) return;
    clip = nextClip; payload = nextPayload;
    slider.max = payload.frames.length - 1;
    video.src = clip.raw_video; video.poster = clip.poster; video.load();
    $('#download-clip').href = clip.overlay_video;
    $('#stage-status').textContent = `${clip.label} · 逐帧预测`;
    $('#play-button').disabled = false;
    updateFrame(0);
  } catch (error) { showError(error); }
}

function showError(error) {
  $('#viewer-error').hidden = false;
  $('#viewer-error').textContent = `${error.message}。请刷新页面重试，或从 GitHub 下载离线版本。`;
  console.error(error);
}

$('#play-button').addEventListener('click', async () => {
  if (!payload) return;
  if (video.paused) {
    if (video.ended || video.currentTime >= video.duration - 0.05) video.currentTime = 0;
    try { await video.play(); } catch (error) { showError(error); }
  } else video.pause();
});
video.addEventListener('play', () => { $('#play-button').textContent = 'Ⅱ'; $('#play-button').setAttribute('aria-label', '暂停片段'); });
video.addEventListener('pause', () => { $('#play-button').textContent = '▶'; $('#play-button').setAttribute('aria-label', '播放片段'); });
video.addEventListener('ended', () => { $('#play-button').textContent = '▶'; });
video.addEventListener('loadedmetadata', () => {
  video.playbackRate = Number($('#playback-rate').value);
  video.currentTime = 0.001;
});
video.addEventListener('error', () => { if (video.currentSrc) showError(new Error('视频未能载入')); });
video.addEventListener('seeked', () => updateFrame(Math.floor(video.currentTime * (manifest?.playback_fps || 12))));
function tick() {
  if (payload && !video.paused) updateFrame(Math.floor(video.currentTime * manifest.playback_fps));
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
slider.addEventListener('input', () => seek(Number(slider.value)));
slider.addEventListener('keydown', event => { if (!payload) return; if (event.key === 'Home') seek(0); if (event.key === 'End') seek(payload.frames.length - 1); });
$('#prev-frame').addEventListener('click', () => seek(frameIndex - 1));
$('#next-frame').addEventListener('click', () => seek(frameIndex + 1));
$('#playback-rate').addEventListener('change', event => { video.playbackRate = Number(event.target.value); });
$$('.overlay-options input').forEach(input => input.addEventListener('change', drawOverlay));
$$('.clip-tabs button').forEach(button => button.addEventListener('click', () => setClip(button.dataset.clip)));
$$('.instrument-options button').forEach(button => button.addEventListener('click', () => {
  selectedTool = button.dataset.tool;
  $$('.instrument-options button').forEach(b => { b.classList.toggle('selected', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  updateFrame(frameIndex);
}));
chart.addEventListener('click', event => {
  if (!payload) return;
  const box = chart.getBoundingClientRect();
  const x = (event.clientX - box.left) / box.width * chart.width;
  seek(Math.round((x - 37) / (chart.width - 49) * (payload.frames.length - 1)));
});
$('#video-stage').addEventListener('dblclick', () => $('#play-button').click());

const charts = {
  learning_curves: ['训练损失、验证误差和 PCK 随 epoch 变化的曲线', '第 27 epoch 获得最佳验证误差。此后训练损失继续下降，验证表现基本停滞。'],
  per_joint_errors: ['FBF 和 PCH 各关键点的验证集与测试集平均误差', '误差在部件之间不均匀。PCH 的 CentralScrew 与 CentralHook 长尾明显；n=0 表示没有可见标注，不能报告精度。'],
  test_error_cdf: ['测试集 FBF 和 PCH 的可见点误差累积分布', '曲线表示误差在指定像素阈值以内的可见点比例，竖线标出 5、10、20px。'],
};
$$('.figure-tabs button').forEach(button => button.addEventListener('click', () => {
  $$('.figure-tabs button').forEach(b => b.setAttribute('aria-selected', String(b === button)));
  $('#results-chart').src = `assets/charts/${button.dataset.chart}.png`;
  $('#results-chart').alt = charts[button.dataset.chart][0]; $('#chart-caption').textContent = charts[button.dataset.chart][1];
}));

async function initialize() {
  try {
    const [clips, summary] = await Promise.all([loadJSON('data/clips.json'), loadJSON('data/results.json')]);
    manifest = clips;
    const names = {train: '训练', val: '验证', test: '测试'};
    $('#results-body').innerHTML = ['FBF', 'PCH'].flatMap((tool, t) => ['train', 'val', 'test'].map((split, i) => {
      const metric = summary.splits[split].tools[tool].visible;
      return `<tr class="${split === 'test' ? 'test-row' : ''} ${t && !i ? 'group-start' : ''}"><td><span class="table-split">${names[split]}</span>${tool}</td><td>${metric.mean_px.toFixed(2)} px</td><td>${(100 * metric.pck_5px).toFixed(1)}%</td><td>${(100 * metric.pck_10px).toFixed(1)}%</td></tr>`;
    })).join('');
    await setClip('steady');
  } catch (error) { showError(error); $('#results-body').innerHTML = '<tr><td colspan="4">指标载入失败，请刷新页面。</td></tr>'; }
}
initialize();

$$('[role="tablist"]').forEach(list => list.addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  let index = tabs.indexOf(document.activeElement);
  if (index < 0) return;
  event.preventDefault();
  if (event.key === 'Home') index = 0;
  else if (event.key === 'End') index = tabs.length - 1;
  else index = (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  tabs[index].focus(); tabs[index].click();
}));
