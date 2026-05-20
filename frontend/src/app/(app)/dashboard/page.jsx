'use client';
import { useState, useEffect } from 'react';
import { getToken } from '@/lib/auth';
import { ASSETS, EXCHANGE_PAIRS, fetchAssetData, buildPeriodData } from '@/lib/data';
import StockDetailModal from '@/components/StockDetailModal';

const SW = 860, SH = 300, ML = 52, MR = 72, MT = 22, MB = 38;
const CW = SW - ML - MR, CH = SH - MT - MB;

const STOCK_SECTORS = [
  { label: '반도체', ids: ['005930', '000660'] },
  { label: '자동차', ids: ['005380', '000270'] },
  { label: '방산',   ids: ['079550', '012450'] },
  { label: '금융',   ids: ['105560', '055550'] },
  { label: '화학',   ids: ['051910', '096770'] },
];

const STOCK_NAMES = {
  '005930': '삼성전자', '000660': 'SK하이닉스',
  '005380': '현대차',   '000270': '기아',
  '079550': 'LIG디펜스앤에어로', '012450': '한화에어로스페이스',
  '105560': 'KB금융',   '055550': '신한지주',
  '051910': 'LG화학',   '096770': 'SK이노베이션',
};

const FX_INFO = {
  'KRW/USD': { flag: '/assets/flags/us.png', desc: '미국 달러' },
  'KRW/EUR': { flag: '/assets/flags/eu.png', desc: '유럽연합 유로' },
  'KRW/JPY': { flag: '/assets/flags/jp.png', desc: '일본 엔 (100엔)' },
  'KRW/CNY': { flag: '/assets/flags/cn.png', desc: '중국 위안' },
  'KRW/CHF': { flag: '/assets/flags/ch.png', desc: '스위스 프랑' },
  'KRW/GBP': { flag: '/assets/flags/gb.png', desc: '영국 파운드' },
};

const LOGO = id => `/assets/logos/${({
  '005930': 'samsung.svg', '000660': 'skhynix.svg',
  '005380': 'hyundai.png', '000270': 'kia.png',
  '079550': 'lignex1.svg', '012450': 'hanwha.svg',
  '105560': 'kb.svg',      '055550': 'shinhan.svg',
  '051910': 'lgchem.svg',  '096770': 'skinnovation.svg',
}[id])}`;

const NEWS_TICKER_OPTIONS = [
  { value: '005930', label: '삼성전자' }, { value: '000660', label: 'SK하이닉스' },
  { value: '005380', label: '현대차' },   { value: '000270', label: '기아' },
  { value: '079550', label: 'LIG디펜스앤에어로' }, { value: '012450', label: '한화에어로스페이스' },
  { value: '105560', label: 'KB금융' },   { value: '055550', label: '신한지주' },
  { value: '051910', label: 'LG화학' },   { value: '096770', label: 'SK이노베이션' },
  { value: 'KRW/USD', label: 'KRW/USD' }, { value: 'KRW/EUR', label: 'KRW/EUR' },
  { value: 'KRW/JPY', label: 'KRW/JPY' }, { value: 'KRW/CNY', label: 'KRW/CNY' },
  { value: 'KRW/CHF', label: 'KRW/CHF' }, { value: 'KRW/GBP', label: 'KRW/GBP' },
];

function NewsDrawer({ open, onClose }) {
  const [ticker, setTicker] = useState('');
  const [days, setDays] = useState('30');
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (open) fetchNews(); }, [open]);

  async function fetchNews() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ days });
      if (ticker) params.set('ticker', ticker);
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`/api/v1/news?${params}`, { headers });
      if (!res.ok) throw new Error();
      setNews(await res.json());
    } catch { setNews([]); }
    setLoading(false);
  }

  return (
    <>
      {open && <div className="news-drawer-backdrop" onClick={onClose} />}
      <div className={`news-drawer${open ? ' open' : ''}`}>
        <div className="news-drawer-header">
          <div className="news-drawer-title">📰 뉴스</div>
          <button className="news-drawer-close" onClick={onClose}>✕</button>
        </div>
        <div className="news-drawer-filters">
          <select className="fsel" value={ticker} onChange={e => setTicker(e.target.value)}>
            <option value="">전체 종목</option>
            {NEWS_TICKER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select className="fsel" value={days} onChange={e => setDays(e.target.value)}>
            <option value="7">최근 7일</option>
            <option value="30">최근 30일</option>
            <option value="90">최근 90일</option>
          </select>
          <button className="btn btn-primary" onClick={fetchNews}>검색</button>
        </div>
        <div className="news-drawer-body">
          {loading ? (
            <div style={{ color: '#94a3b8', fontSize: 12, padding: '24px 0', textAlign: 'center' }}>불러오는 중...</div>
          ) : news.length === 0 ? (
            <div style={{ color: '#94a3b8', fontSize: 12, padding: '24px 0', textAlign: 'center' }}>뉴스가 없습니다.</div>
          ) : news.map((n, i) => (
            <div key={i} className="news-item">
              <div className="news-meta">
                <span className="ticker-tag">{n.ticker}</span>
                <span className="news-date">{n.date_str}</span>
                <span className="news-source">{n.source}</span>
              </div>
              <div className="news-title">{n.title}</div>
              <div className="news-body">{n.body}</div>
              {n.ai_summary && (
                <div className="ai-box" style={{ marginTop: 8, padding: '10px 12px' }}>
                  <div className="ai-header" style={{ marginBottom: 6 }}>
                    <span className="ai-badge" style={{ fontSize: 9 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 3줄 요약</span>
                  </div>
                  <div className="ai-text" style={{ fontSize: 11 }}>{n.ai_summary}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}


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

function renderChartSvg(activeAssets, pd) {
  if (!pd || activeAssets.length === 0) return '';
  const n = pd.labels.length;

  let allV = [0];
  activeAssets.forEach(a => { if (pd.d[a]) allV.push(...pd.d[a].filter(v => v !== null)); });
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
    const isFx = a.startsWith('KRW/');
    const isKospi = a === '000000';
    const lineAttr = isKospi
      ? 'stroke-dasharray="1,5" stroke-linecap="round" stroke-width="2.5"'
      : isFx
        ? 'stroke-dasharray="7,4" stroke-linecap="butt" stroke-width="1.8"'
        : 'stroke-linecap="round" stroke-width="2"';

    let seg = [];
    vals.forEach((v, i) => {
      if (v === null) {
        if (seg.length > 1) h += `<polyline points="${seg.join(' ')}" fill="none" stroke="${col}" stroke-linejoin="round" ${lineAttr}/>`;
        seg = [];
      } else {
        seg.push(`${toX(i, n).toFixed(1)},${toY(v, minV, maxV).toFixed(1)}`);
      }
    });
    if (seg.length > 1) h += `<polyline points="${seg.join(' ')}" fill="none" stroke="${col}" stroke-linejoin="round" ${lineAttr}/>`;

    let lastIdx = vals.length - 1;
    while (lastIdx >= 0 && vals[lastIdx] === null) lastIdx--;
    if (lastIdx < 0) return;
    const lv = vals[lastIdx];
    const lx = toX(lastIdx, n), ly = toY(lv, minV, maxV);
    h += `<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="${col}"/>`;
    const sign = lv >= 0 ? '+' : '';
    h += `<text x="${(lx + 6).toFixed(1)}" y="${(ly + 4).toFixed(1)}" font-size="10" fill="${col}" font-weight="700">${sign}${lv.toFixed(1)}%</text>`;
  });

  return h;
}

async function fetchFavs(token) {
  try {
    const res = await fetch('/api/v1/favorites', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return new Set();
    const { assets } = await res.json();
    return new Set(assets);
  } catch { return new Set(); }
}

async function pushFavs(s, token) {
  try {
    await fetch('/api/v1/favorites', {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ assets: [...s] }),
    });
  } catch { /* silent */ }
}

function fmtChg(pct) {
  const sign = pct >= 0 ? '▲' : '▼';
  const cls = pct >= 0 ? 'positive' : 'negative';
  return { text: `${sign} ${Math.abs(pct).toFixed(2)}%`, cls };
}

export default function DashboardPage() {
  const [activeAssets, setActiveAssets] = useState(['000000']);
  const [period, setPeriod] = useState('1M');
  const [prices, setPrices] = useState({});
  const [chartSvg, setChartSvg] = useState('');
  const [legend, setLegend] = useState([]);
  const [favs, setFavs] = useState(new Set());
  const [detailStockId, setDetailStockId] = useState(null);
  const [complexData, setComplexData] = useState({});
  const [rightOpen, setRightOpen] = useState(false);
  const [newsDrawerOpen, setNewsDrawerOpen] = useState(false);
  const [previewNews, setPreviewNews] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expandedNews, setExpandedNews] = useState(null);
  const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

  useEffect(() => {
    fetchFavs(getToken()).then(setFavs);
    loadLatestPrices();
    loadLatestRates();
    loadPreviewNews();
  }, []);

  useEffect(() => {
    renderChart();
  }, [activeAssets, period, prices]);

  async function loadLatestPrices() {
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('/api/v1/prices/latest', { headers });
      if (!res.ok) return;
      const data = await res.json();
      setPrices(prev => {
        const next = { ...prev };
        data.forEach(({ ticker, close, change_pct, change }) => {
          next[ticker] = { price: close, change_pct, change };
        });
        return next;
      });
    } catch { /* silent */ }
  }

  async function loadPreviewNews() {
    setPreviewLoading(true);
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('/api/v1/news?days=30', { headers });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setPreviewNews(data.slice(0, 3));
    } catch { setPreviewNews([]); }
    setPreviewLoading(false);
  }

  async function loadLatestRates() {
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('/api/v1/exchange-rates/latest', { headers });
      if (!res.ok) return;
      const data = await res.json();
      setPrices(prev => {
        const next = { ...prev };
        data.forEach(({ pair, rate, change_pct, change }) => {
          next[pair] = { price: rate, change_pct, change, isRate: true };
        });
        return next;
      });
    } catch { /* silent */ }
  }

  function shortLabel(id) {
    if (id === '000000') return 'KOSPI';
    if (id.startsWith('KRW/')) return id.split('/')[1];
    return ASSETS[id]?.label || id;
  }

  function calcPearson(d1, d2) {
    const map1 = {}, map2 = {};
    d1.dates.forEach((d, i) => { map1[d] = d1.dr[i]; });
    d2.dates.forEach((d, i) => { map2[d] = d2.dr[i]; });
    const common = d1.dates.filter(d => map2[d] !== undefined);
    if (common.length < 2) return 0;
    const r1 = common.map(d => map1[d]), r2 = common.map(d => map2[d]);
    const n = r1.length;
    const m1 = r1.reduce((a, b) => a + b, 0) / n;
    const m2 = r2.reduce((a, b) => a + b, 0) / n;
    let num = 0, den1 = 0, den2 = 0;
    for (let i = 0; i < n; i++) {
      const a = r1[i] - m1, b = r2[i] - m2;
      num += a * b; den1 += a * a; den2 += b * b;
    }
    const denom = Math.sqrt(den1 * den2);
    return denom === 0 ? 0 : parseFloat((num / denom).toFixed(2));
  }

  function corrStyle(v) {
    const t = Math.max(-1, Math.min(1, v));
    const nr = 248, ng = 250, nb = 252;
    let r, g, b;
    if (t >= 0) {
      r = Math.round(nr + (30 - nr) * t); g = Math.round(ng + (64 - ng) * t); b = Math.round(nb + (175 - nb) * t);
    } else {
      const s = -t;
      r = Math.round(nr + (185 - nr) * s); g = Math.round(ng + (28 - ng) * s); b = Math.round(nb + (28 - nb) * s);
    }
    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    return { background: `rgb(${r},${g},${b})`, color: brightness < 140 ? 'white' : (t < 0 ? '#7f1d1d' : '#1e3a8a') };
  }

  async function computeComplex(ids, p) {
    if (ids.length < 2) { setComplexData({}); return; }
    const results = await Promise.all(ids.map(id => fetchAssetData(id, p)));
    const cd = {};
    ids.forEach((id, i) => {
      const rows = results[i];
      if (!rows || rows.length < 2) return;
      const isFx = EXCHANGE_PAIRS.has(id);
      const closes = rows.map(r => Number(isFx ? r.rate : r.close));
      const dr = [], dates = [];
      for (let j = 1; j < closes.length; j++) {
        dr.push((closes[j] - closes[j - 1]) / closes[j - 1]);
        dates.push(rows[j].date);
      }
      const totalReturn = rows[rows.length - 1].return_pct;
      const mean = dr.reduce((a, b) => a + b, 0) / dr.length;
      const std = Math.sqrt(dr.reduce((a, b) => a + (b - mean) ** 2, 0) / dr.length);
      const sharpe = std === 0 ? 0 : parseFloat((mean / std * Math.sqrt(252)).toFixed(2));
      cd[id] = { totalReturn, sharpe, dr, dates };
    });
    setComplexData(cd);
  }

  async function renderChart() {
    if (activeAssets.length === 0) { setChartSvg(''); setLegend([]); setComplexData({}); return; }
    await Promise.all(activeAssets.map(id => fetchAssetData(id, period)));
    const pd = buildPeriodData(period, activeAssets);
    const svg = renderChartSvg(activeAssets, pd);
    setChartSvg(svg);
    setLegend(activeAssets.map(a => {
      const vals = pd?.d[a];
      const last = vals ? (vals.filter(v => v !== null).pop() ?? 0) : 0;
      return { id: a, last };
    }));
    computeComplex(activeAssets, period);
  }

  async function toggleAsset(id) {
    setActiveAssets(prev =>
      prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
    );
  }

  function toggleFav(id, e) {
    e.stopPropagation();
    const next = new Set(favs);
    if (next.has(id)) next.delete(id); else next.add(id);
    setFavs(new Set(next));
    pushFavs(next, getToken());
  }

  function priceStr(id) {
    const d = prices[id];
    if (!d) return '—';
    return d.isRate
      ? Number(d.price).toLocaleString('ko-KR')
      : Number(d.price).toLocaleString('ko-KR') + '원';
  }

  function ChgEl({ id }) {
    const d = prices[id];
    if (!d || d.change_pct === undefined) return <div className="tk-chg">—</div>;
    const { text, cls } = fmtChg(d.change_pct);
    return <div className={`tk-chg ${cls}`}>{text}</div>;
  }

  function TkCard({ id, name }) {
    const inChart = activeAssets.includes(id);
    const d = prices[id];
    const starred = favs.has(id);
    return (
      <div className={`tk-card${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)} title={name}>
        <div className="tk-card-head">
          <div className="tk-card-logo">
            <img src={LOGO(id)} alt={name} />
          </div>
          <div className="tk-card-name">{name}</div>
          <div className="tk-card-acts">
            <button
              className={`tk-card-star${starred ? ' starred' : ''}`}
              onClick={e => toggleFav(id, e)}
            >{starred ? '★' : '☆'}</button>
            <button
              className="tk-card-det"
              onClick={e => { e.stopPropagation(); setDetailStockId(id); }}
              title="자세히 보기"
            >↗</button>
          </div>
        </div>
        <div className="tk-card-bottom">
          <span className="tk-card-price">{d ? Number(d.price).toLocaleString('ko-KR') + '원' : '—'}</span>
          <ChgEl id={id} />
        </div>
      </div>
    );
  }

  function FxCard({ id }) {
    const info = FX_INFO[id];
    const inChart = activeAssets.includes(id);
    const currency = id.split('/')[1];
    const starred = favs.has(id);
    return (
      <div className={`fx-card${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)}>
        <div className="fx-card-head">
          <img src={info.flag} alt={currency} className="fx-card-flag" />
          <span className="fx-card-code">{currency}</span>
          <button
            className={`tk-card-star${starred ? ' starred' : ''}`}
            onClick={e => toggleFav(id, e)}
          >{starred ? '★' : '☆'}</button>
        </div>
        <div className="fx-card-bottom">
          <span className="fx-card-rate">{priceStr(id)}</span>
          <ChgEl id={id} />
        </div>
      </div>
    );
  }

  const kospiInChart = activeAssets.includes('000000');
  const kospiPrice = prices['000000'];

  const complexIds = activeAssets.filter(id => complexData[id]);
  const showComplex = complexIds.length >= 2;
  const insightLines = (() => {
    if (complexIds.length < 2) return [];
    const sorted = [...complexIds].sort((a, b) => complexData[b].totalReturn - complexData[a].totalReturn);
    const best = sorted[0];
    let minCorr = 1, minPair = null;
    for (let i = 0; i < complexIds.length; i++) {
      for (let j = i + 1; j < complexIds.length; j++) {
        const c = calcPearson(complexData[complexIds[i]], complexData[complexIds[j]]);
        if (c < minCorr) { minCorr = c; minPair = [complexIds[i], complexIds[j]]; }
      }
    }
    const lines = [];
    const r = complexData[best].totalReturn;
    lines.push(`${shortLabel(best)}(${r >= 0 ? '+' : ''}${r.toFixed(1)}%)이 선택 종목 중 가장 높은 수익률을 기록했습니다.`);
    if (minPair) lines.push(`${shortLabel(minPair[0])}와 ${shortLabel(minPair[1])}의 상관계수는 ${minCorr.toFixed(2)}로 가장 낮아 분산 효과가 큽니다.`);
    const allPos = complexIds.every(id => complexData[id].totalReturn >= 0);
    const allNeg = complexIds.every(id => complexData[id].totalReturn < 0);
    if (allPos) lines.push('전 종목이 플러스 수익률을 기록 중입니다.');
    else if (allNeg) lines.push('전 종목이 마이너스 수익률을 기록 중입니다.');
    return lines;
  })();

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <NewsDrawer open={newsDrawerOpen} onClose={() => setNewsDrawerOpen(false)} />
      {detailStockId && (
        <StockDetailModal stockId={detailStockId} onClose={() => setDetailStockId(null)} />
      )}
      <div className={`dash-layout${rightOpen ? ' panel-open' : ''}`} style={{ minHeight: 'calc(100vh - 120px)' }}>

        {/* LEFT: Chart */}
        <div className="chart-panel">
          <div className="chart-controls">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>기간</div>
              <div className="period-sel">
                {PERIODS.map(p => (
                  <button
                    key={p}
                    className={`per-btn${period === p ? ' active' : ''}`}
                    onClick={() => setPeriod(p)}
                  >
                    {p === '1W' ? '1주' : p === '1M' ? '1개월' : p === '3M' ? '3개월' : p === '6M' ? '6개월' : p === '1Y' ? '1년' : p === '3Y' ? '3년' : '전체'}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                className={`kospi-widget${kospiInChart ? ' in-chart' : ''}`}
                onClick={() => toggleAsset('000000')}
              >
                <div style={{ fontSize: 20, fontWeight: 800, color: '#475569', letterSpacing: 1 }}>KOSPI</div>
                <div style={{ width: 1, height: 28, background: '#e2e8f0' }} />
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5 }}>
                  {kospiPrice ? Number(kospiPrice.price).toLocaleString('ko-KR') : '—'}
                </div>
                {kospiPrice && kospiPrice.change_pct !== undefined ? (() => {
                  const { text, cls } = fmtChg(kospiPrice.change_pct);
                  return <div className={`tk-chg ${cls}`} style={{ fontSize: 13 }}>{text}</div>;
                })() : <div className="tk-chg" style={{ fontSize: 13 }}>—</div>}
              </div>
            </div>
          </div>

          <div className="active-chips">
            {[...activeAssets.filter(a => a === '000000'), ...activeAssets.filter(a => a !== '000000')].map(a => (
              <span key={a} className="a-chip" style={{ color: ASSETS[a].color, borderColor: ASSETS[a].color, background: ASSETS[a].color + '18' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: ASSETS[a].color, display: 'inline-block' }} />
                {ASSETS[a].label}
                <span className="rm" onClick={e => { e.stopPropagation(); setActiveAssets(prev => prev.filter(x => x !== a)); }}>✕</span>
              </span>
            ))}
          </div>

          <div className="chart-card">
            {activeAssets.length === 0 && (
              <div className="chart-empty">
                <div style={{ fontSize: 48 }}>🖥️</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#334155' }}>종목을 선택해주세요</div>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>오른쪽 목록에서 종목을 클릭하면 차트가 표시됩니다</div>
              </div>
            )}
            <div className="chart-svg-wrap">
              <svg
                viewBox={`0 0 ${SW} ${SH}`}
                preserveAspectRatio="none"
                style={{ width: '100%', minHeight: 280, display: 'block' }}
                dangerouslySetInnerHTML={{ __html: chartSvg }}
              />
            </div>
            {legend.length > 0 && (
              <div className="chart-legend">
                {legend.map(({ id, last }) => {
                  const sign = last >= 0 ? '+' : '';
                  const col = last >= 0 ? '#16a34a' : '#dc2626';
                  return (
                    <div key={id} className="leg-item">
                      <div className="leg-dot" style={{ background: ASSETS[id].color }} />
                      <span className="leg-name">{ASSETS[id].label}</span>
                      <span className="leg-val" style={{ color: col }}>{sign}{last.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* AI 메인 패널 */}
        <div className="ai-main-panel">
          <div className="ai-main-card">
            <div className="ai-main-title">
              <span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
              개인화된 시장 분석
            </div>
            <div className="ai-main-body">
              방산주 강세 지속. 달러 약세로 수출주 단기 환율 리스크.<br /><br />
              반도체는 HBM 수요 기반 상승 모멘텀 유지 중.<br /><br />
              <span style={{ color: '#6d28d9', fontWeight: 600 }}>회원님의 관심 종목</span> 중 KB금융은 금리 인하 수혜 기대감으로 단기 매수세 유입 가능성이 높습니다.
            </div>
          </div>
          <div className="news-preview-card">
            <div className="news-preview-header">
              <span className="news-preview-title">뉴스</span>
              <button className="news-preview-more" onClick={() => setNewsDrawerOpen(true)}>전체 보기 →</button>
            </div>
            {previewLoading ? (
              <div style={{ color: '#94a3b8', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>불러오는 중...</div>
            ) : previewNews.length === 0 ? (
              <div style={{ color: '#94a3b8', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>뉴스가 없습니다.</div>
            ) : previewNews.map((n, i) => (
              <div key={i} className="news-preview-item" style={{ cursor: n.ai_summary ? 'pointer' : 'default' }} onClick={() => n.ai_summary && setExpandedNews(expandedNews === i ? null : i)}>
                <div className="news-meta">
                  <span className="ticker-tag">{n.ticker}</span>
                  <span className="news-date">{n.date_str}</span>
                  {n.ai_summary && <span style={{ marginLeft: 'auto', fontSize: 10, color: '#94a3b8' }}>{expandedNews === i ? '▲' : '▼'}</span>}
                </div>
                <div className="news-title" style={{ fontSize: 12 }}>{n.title}</div>
                {expandedNews === i && n.ai_summary && (
                  <div className="ai-box" style={{ marginTop: 8, padding: '10px 12px' }}>
                    <div className="ai-header" style={{ marginBottom: 6 }}>
                      <span className="ai-badge" style={{ fontSize: 9 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 3줄 요약</span>
                    </div>
                    <div className="ai-text" style={{ fontSize: 11 }} dangerouslySetInnerHTML={{ __html: n.ai_summary }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar toggle tab */}
        <button
          className="sidebar-tab"
          onClick={() => setRightOpen(o => !o)}
          title={rightOpen ? '패널 닫기' : '패널 열기'}
        >
          {rightOpen ? '‹' : '›'}
        </button>

        {/* RIGHT panel */}
        <div className={`right-panel${rightOpen ? '' : ' right-panel-closed'}`}>
          {/* Favorites */}
          <div className="card">
            <div className="card-title">⭐ 즐겨찾기</div>
            {favs.size === 0 ? (
              <div className="fav-empty">별 아이콘을 눌러 추가하세요</div>
            ) : (
              <div className="fav-grid">
                {[...favs].map(id => {
                  if (!ASSETS[id]) return null;
                  const inChart = activeAssets.includes(id);
                  const d = prices[id];
                  const isFx = EXCHANGE_PAIRS.has(id);
                  let ps = '—', amtStr = null;
                  if (d) {
                    ps = isFx ? Number(d.price).toLocaleString('ko-KR') : Number(d.price).toLocaleString('ko-KR') + '원';
                    if (d.change !== undefined) {
                      const pos = d.change >= 0;
                      amtStr = {
                        text: isFx
                          ? `${pos ? '+' : ''}${d.change.toFixed(2)}`
                          : `${pos ? '+' : ''}${Math.round(d.change).toLocaleString('ko-KR')}원`,
                        cls: pos ? 'positive' : 'negative',
                      };
                    }
                  }
                  const icon = isFx
                    ? <img src={FX_INFO[id]?.flag} alt={id} style={{ width: 18, height: 12, borderRadius: 2, objectFit: 'cover', flexShrink: 0 }} />
                    : <div className="tk-card-logo"><img src={LOGO(id)} alt={ASSETS[id].label} /></div>;
                  return (
                    <div key={id} className={`fav-card${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)} title={ASSETS[id].label}>
                      <div className="tk-card-head">
                        {icon}
                        <div className="tk-card-name">{ASSETS[id].label}</div>
                        <button className="tk-card-star starred" onClick={e => toggleFav(id, e)}>★</button>
                      </div>
                      <div className="tk-card-bottom">
                        <span className="tk-card-price">{ps}</span>
                        <ChgEl id={id} />
                        {amtStr && <span className={`fav-amt ${amtStr.cls}`}>{amtStr.text}</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Watchlist */}
          <div className="card">
            <div className="card-title">
              종목 현황
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>클릭하면 차트에 추가</span>
            </div>
            <div className="stock-grid">
              {STOCK_SECTORS.flatMap(s => s.ids).map(id => (
                <TkCard key={id} id={id} name={STOCK_NAMES[id]} />
              ))}
            </div>
          </div>

          {/* Exchange rates */}
          <div className="card">
            <div className="card-title">
              환율 현황
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>클릭하면 차트에 추가</span>
            </div>
            <div className="fx-grid">
              {Object.keys(FX_INFO).map(id => <FxCard key={id} id={id} />)}
            </div>
          </div>

        </div>
      </div>

      {showComplex && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
          <div className="other-card">
            <div className="other-card-title">
              상관계수 매트릭스
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>Pearson · {period}</span>
            </div>
            <table className="matrix-table">
              <thead>
                <tr>
                  <th className="mh" />
                  {complexIds.map(id => <th key={id} className="mh">{shortLabel(id)}</th>)}
                </tr>
              </thead>
              <tbody>
                {complexIds.map(row => (
                  <tr key={row}>
                    <th className="mh" style={{ textAlign: 'right', paddingRight: 5 }}>{shortLabel(row)}</th>
                    {complexIds.map(col => {
                      if (row === col) return <td key={col} className="mc" style={{ background: '#f1f5f9', border: '1px solid #e2e8f0' }} />;
                      const v = calcPearson(complexData[row], complexData[col]);
                      const { background, color } = corrStyle(v);
                      return <td key={col} className="mc" style={{ background, color }}>{v.toFixed(2)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 10, color: '#64748b' }}>
              <span>-1.0</span>
              <div style={{ width: 120, height: 8, borderRadius: 4, background: 'linear-gradient(to right,rgb(185,28,28),rgb(248,250,252),rgb(30,64,175))' }} />
              <span>+1.0</span>
            </div>
          </div>

          <div className="other-card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="other-card-title">
              <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span className="ai-badge" style={{ textTransform: 'none', letterSpacing: 0 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
                종목 분석
              </span>
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>{period}</span>
            </div>
            <div style={{ background: 'linear-gradient(160deg, #f5f3ff 0%, #eef2ff 100%)', border: '1px solid #c4b5fd', borderRadius: 10, padding: '14px 16px', flex: 1, fontSize: 13, lineHeight: 1.8, color: '#312e81' }}>
              {insightLines.map((line, i) => (
                <p key={i} style={{ margin: i === 0 ? 0 : '10px 0 0' }}>{line}</p>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
