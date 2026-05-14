const SW = 860, SH = 300, ML = 52, MR = 72, MT = 22, MB = 38;
const CW = SW - ML - MR, CH = SH - MT - MB;

let currentPeriod = '1W';
let activeAssets = ['000000'];

function toX(i, n) { return ML + (i / (n - 1)) * CW; }
function toY(v, minV, maxV) { return MT + ((maxV - v) / (maxV - minV)) * CH; }

function niceTicks(min, max, target) {
  const range = max - min || 1;
  const raw = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map(s => s * mag).find(s => range / s <= target + 1) || mag;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 1000) / 1000);
  return ticks;
}

async function render() {
  await Promise.all(activeAssets.map(id => fetchAssetData(id, currentPeriod)));
  const pd = buildPeriodData(currentPeriod, activeAssets);
  renderChips();
  _renderChart(pd);
  _renderLegend(pd);
  document.querySelectorAll('[data-id]').forEach(el => {
    el.classList.toggle('in-chart', activeAssets.includes(el.dataset.id));
  });
}

function _renderChart(pd) {
  const svg = document.getElementById('main-chart');
  const emptyEl = document.getElementById('chart-empty');
  if (!pd || activeAssets.length === 0) {
    svg.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'flex';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';
  const n = pd.labels.length;

  let allV = [0];
  activeAssets.forEach(a => { if (pd.d[a]) allV.push(...pd.d[a]); });
  let minV = Math.min(...allV), maxV = Math.max(...allV);
  const pad = Math.max((maxV - minV) * 0.12, 3);
  minV -= pad; maxV += pad;

  let h = '';

  niceTicks(minV, maxV, 6).forEach(v => {
    const y = toY(v, minV, maxV);
    const isZero = Math.abs(v) < 0.01;
    h += `<line x1="${ML}" y1="${y.toFixed(1)}" x2="${SW - MR}" y2="${y.toFixed(1)}" stroke="${isZero ? '#cbd5e1' : '#f1f5f9'}" stroke-width="${isZero ? 1.5 : 1}" ${isZero ? 'stroke-dasharray="5,4"' : ''}/>`;
    const label = (v >= 0 ? '+' : '') + v.toFixed(v % 1 === 0 ? 0 : 1) + '%';
    h += `<text x="${ML - 5}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="${isZero ? '#475569' : '#94a3b8'}" font-weight="${isZero ? 600 : 400}">${label}</text>`;
  });

  const step = Math.max(1, Math.ceil(n / 8));
  for (let i = 0; i < n; i += step) {
    const x = toX(i, n);
    h += `<text x="${x.toFixed(1)}" y="${(MT + CH + 22).toFixed(1)}" text-anchor="middle" font-size="10" fill="#94a3b8">${pd.labels[i]}</text>`;
  }
  if ((n - 1) % step !== 0) {
    const x = toX(n - 1, n);
    h += `<text x="${x.toFixed(1)}" y="${(MT + CH + 22).toFixed(1)}" text-anchor="middle" font-size="10" fill="#94a3b8">${pd.labels[n - 1]}</text>`;
  }

  activeAssets.forEach(a => {
    const vals = pd.d[a];
    if (!vals) return;
    const col = ASSETS[a].color;
    const pts = vals.map((v, i) => `${toX(i, n).toFixed(1)},${toY(v, minV, maxV).toFixed(1)}`).join(' ');
    const isFx = a.startsWith('KRW/');
    const isKospi = a === '000000';
    const lineAttr = isKospi
      ? 'stroke-dasharray="1,5" stroke-linecap="round" stroke-width="2.5"'
      : isFx
        ? 'stroke-dasharray="7,4" stroke-linecap="butt" stroke-width="1.8"'
        : 'stroke-linecap="round" stroke-width="2"';
    h += `<polyline points="${pts}" fill="none" stroke="${col}" stroke-linejoin="round" ${lineAttr}/>`;
    const lv = vals[n - 1];
    const lx = toX(n - 1, n), ly = toY(lv, minV, maxV);
    h += `<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="${col}"/>`;
    const sign = lv >= 0 ? '+' : '';
    h += `<text x="${(lx + 6).toFixed(1)}" y="${(ly + 4).toFixed(1)}" font-size="10" fill="${col}" font-weight="700">${sign}${lv.toFixed(1)}%</text>`;
  });

  svg.innerHTML = h;
}

function _renderLegend(pd) {
  document.getElementById('chart-legend').innerHTML = activeAssets.map(a => {
    const vals = pd?.d[a];
    const last = vals ? vals[vals.length - 1] : 0;
    const sign = last >= 0 ? '+' : '';
    const col = last >= 0 ? '#16a34a' : '#dc2626';
    return `<div class="leg-item">
      <div class="leg-dot" style="background:${ASSETS[a].color}"></div>
      <span class="leg-name">${ASSETS[a].label}</span>
      <span class="leg-val" style="color:${col}">${sign}${last.toFixed(1)}%</span>
    </div>`;
  }).join('');
}

function renderChips() {
  const sorted = [
    ...activeAssets.filter(a => a === '000000'),
    ...activeAssets.filter(a => a !== '000000'),
  ];
  const chips = sorted.map(a => {
    const meta = ASSETS[a];
    return `<span class="a-chip" style="color:${meta.color};border-color:${meta.color};background:${meta.color}18">
      <span style="width:7px;height:7px;border-radius:50%;background:${meta.color};display:inline-block"></span>
      ${meta.label}
      <span class="rm" onclick="event.stopPropagation();removeAsset('${a}')">✕</span>
    </span>`;
  }).join('');
  document.getElementById('active-chips').innerHTML = chips;
}

function renderDropdown() {
  const groups = [
    { label: '지수',   ids: ['000000'] },
    { label: '반도체', ids: ['005930', '000660'] },
    { label: '자동차', ids: ['005380', '000270'] },
    { label: '방산',   ids: ['079550', '012450'] },
    { label: '금융',   ids: ['105560', '055550'] },
    { label: '화학',   ids: ['051910', '096770'] },
    { label: '환율',   ids: ['KRW/USD', 'KRW/JPY', 'KRW/EUR', 'KRW/CNY', 'KRW/CHF', 'KRW/GBP'] },
  ];
  document.getElementById('ind-dropdown').innerHTML = groups.map(g => `
    <div class="ind-group-label">${g.label}</div>
    ${g.ids.map(id => {
      const isActive = activeAssets.includes(id);
      return `<div class="ind-option ${isActive ? 'checked' : ''}" onclick="toggleAsset('${id}');renderDropdown()">
        <div class="ind-dot" style="background:${ASSETS[id].color}"></div>
        <span>${ASSETS[id].label}</span>
        ${isActive ? '<span class="ind-check">✓</span>' : ''}
      </div>`;
    }).join('')}
  `).join('');
}

async function toggleAsset(id) {
  if (activeAssets.includes(id)) {
    activeAssets = activeAssets.filter(a => a !== id);
  } else {
    activeAssets.push(id);
  }
  await render();
}

async function removeAsset(id) {
  activeAssets = activeAssets.filter(a => a !== id);
  await render();
}

function toggleDropdown(e) {
  e.stopPropagation();
  const dd = document.getElementById('ind-dropdown');
  const isOpen = dd.style.display !== 'none';
  dd.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) renderDropdown();
}

document.addEventListener('click', () => {
  const dd = document.getElementById('ind-dropdown');
  if (dd) dd.style.display = 'none';
});

document.getElementById('period-sel').addEventListener('click', async e => {
  const btn = e.target.closest('.per-btn');
  if (!btn) return;
  currentPeriod = btn.dataset.p;
  document.querySelectorAll('.per-btn').forEach(b => b.classList.toggle('active', b === btn));
  await render();
});
