'use client';
import { useState, useEffect, useRef } from 'react';
import { fetchWithAuth } from '@/lib/auth';
import { ASSETS, EXCHANGE_PAIRS, fetchAssetData, buildPeriodData } from '@/lib/data';
import StockDetailModal, { STOCK_CONFIG } from '@/components/StockDetailModal';

const SW = 860, SH = 300, ML = 52, MR = 16, MT = 22, MB = 38;
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
  '079550': 'LIG디펜스앤에어로스페이스', '012450': '한화에어로스페이스',
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
  { value: '079550', label: 'LIG디펜스앤에어로스페이스' }, { value: '012450', label: '한화에어로스페이스' },
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
      const res = await fetchWithAuth(`/api/v1/news?${params}`);
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
          <div className="news-drawer-title"><span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span> 뉴스 요약</div>
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
            <div style={{ color: '#94a3b8', fontSize: 12, padding: '24px 0', textAlign: 'center' }}>데이터가 없습니다.</div>
          ) : news.map((n, i) => (
            <div key={i} className="news-item">
              <div className="news-meta">
                <span className="ticker-tag">{n.name}</span>
                <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>
                  {n.direction || '혼조'}
                </span>
                <span className="news-date">{n.start_date} ~ {n.end_date}</span>
              </div>
              <div className="ai-box" style={{ marginTop: 6, padding: '10px 12px' }}>
                <div className="ai-header" style={{ marginBottom: 6 }}>
                  <span className="ai-badge" style={{ fontSize: 9 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 장세 분석</span>
                </div>
                {n.cause && <div className="ai-text" style={{ fontSize: 11, marginBottom: 4 }}>{n.cause}</div>}
                {n.vol_insight && <div className="ai-text" style={{ fontSize: 11, color: '#4338ca' }}>{n.vol_insight}</div>}
              </div>
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

function LineChart({ activeAssets, pd, hoveredAsset, onHoverAsset }) {
  const [tooltip, setTooltip] = useState(null);
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const svgRef = useRef(null);
  if (!pd || activeAssets.length === 0) return null;
  const n = pd.labels.length;

  let allV = [0];
  activeAssets.forEach(a => { if (pd.d[a]) allV.push(...pd.d[a].filter(v => v !== null)); });
  let minV = Math.min(...allV), maxV = Math.max(...allV);
  const pad = Math.max((maxV - minV) * 0.12, 3);
  minV -= pad; maxV += pad;

  const ticks = niceTicks(minV, maxV, 6);
  const step = Math.max(1, Math.ceil(n / 8));
  const xLabelIndices = [];
  for (let i = 0; i < n; i += step) xLabelIndices.push(i);
  if ((n - 1) % step !== 0) xLabelIndices.push(n - 1);

  function getIdx(clientX) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    const svgX = (clientX - rect.left) / rect.width * SW;
    return Math.max(0, Math.min(n - 1, Math.round((svgX - ML) / CW * (n - 1))));
  }

  function buildTooltip(a, clientX, clientY) {
    const idx = getIdx(clientX);
    const closes = pd.closes?.[a];
    const close = closes?.[idx] ?? null;
    const prevClose = idx > 0 ? closes?.[idx - 1] : null;
    const dailyChgPct = close != null && prevClose != null
      ? (close - prevClose) / prevClose * 100 : null;
    return {
      x: clientX, y: clientY,
      name: ASSETS[a].label,
      color: ASSETS[a].color,
      date: pd.labels[idx],
      close,
      isFx: EXCHANGE_PAIRS.has(a),
      periodVal: pd.d[a]?.[idx] ?? 0,
      dailyChgPct,
    };
  }

  return (
    <>
    {tooltip && (
      <div style={{
        position: 'fixed',
        left: Math.min(tooltip.x + 14, window.innerWidth - 210),
        top: Math.max(10, tooltip.y - 120),
        background: 'white', border: `1.5px solid ${tooltip.color}`, borderRadius: 10,
        padding: '9px 14px', boxShadow: '0 4px 16px rgba(15,23,42,0.12)',
        zIndex: 200, pointerEvents: 'none', minWidth: 200,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: tooltip.color, flexShrink: 0, display: 'inline-block' }} />
          <span style={{ fontWeight: 700, fontSize: 15, color: '#1e293b' }}>{tooltip.name}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 13, marginBottom: 4 }}>
          <span style={{ color: '#94a3b8' }}>날짜</span>
          <span style={{ fontWeight: 600, color: '#374151' }}>{tooltip.date}</span>
        </div>
        {tooltip.close != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 13, marginBottom: 4 }}>
            <span style={{ color: '#94a3b8' }}>{tooltip.isFx ? '환율' : '주가'}</span>
            <span style={{ fontWeight: 700, color: '#1e293b' }}>
              {tooltip.isFx
                ? tooltip.close.toLocaleString('ko-KR', { maximumFractionDigits: 2 })
                : `${Number(tooltip.close).toLocaleString('ko-KR')}원`}
            </span>
          </div>
        )}
        {tooltip.dailyChgPct != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 13, marginBottom: 4 }}>
            <span style={{ color: '#94a3b8' }}>전일 대비</span>
            <span style={{ fontWeight: 700, color: tooltip.dailyChgPct >= 0 ? '#16a34a' : '#dc2626' }}>
              {tooltip.dailyChgPct >= 0 ? '▲' : '▼'} {Math.abs(tooltip.dailyChgPct).toFixed(2)}%
            </span>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 13 }}>
          <span style={{ color: '#94a3b8' }}>기간 수익률</span>
          <span style={{ fontWeight: 700, color: tooltip.periodVal >= 0 ? '#16a34a' : '#dc2626' }}>
            {tooltip.periodVal >= 0 ? '+' : ''}{tooltip.periodVal.toFixed(2)}%
          </span>
        </div>
      </div>
    )}
    <svg ref={svgRef} viewBox={`0 0 ${SW} ${SH}`} preserveAspectRatio="none"
      style={{ width: '100%', height: '100%', display: 'block' }}
      onMouseLeave={() => { onHoverAsset(null); setTooltip(null); setHoveredIdx(null); }}>

      {/* 그리드 + y축 라벨 */}
      {ticks.map(v => {
        const y = toY(v, minV, maxV);
        const isZero = Math.abs(v) < 0.01;
        const label = (v >= 0 ? '+' : '') + v.toFixed(v % 1 === 0 ? 0 : 1) + '%';
        return (
          <g key={v}>
            <line x1={ML} y1={y.toFixed(1)} x2={SW - MR} y2={y.toFixed(1)}
              stroke={isZero ? '#94a3b8' : '#f1f5f9'} strokeWidth={isZero ? 1.5 : 1}
              />
            <text x={ML - 5} y={(y + 4).toFixed(1)} textAnchor="end" fontSize={10}
              fill={isZero ? '#94a3b8' : '#94a3b8'} fontWeight={isZero ? 600 : 400}>{label}</text>
          </g>
        );
      })}

      {/* x축 라벨 */}
      {xLabelIndices.map(i => (
        <text key={i} x={toX(i, n).toFixed(1)} y={(MT + CH + 22).toFixed(1)}
          textAnchor="middle" fontSize={10} fill="#94a3b8">{pd.labels[i]}</text>
      ))}

      {/* crosshair */}
      {hoveredIdx !== null && (
        <line
          x1={toX(hoveredIdx, n).toFixed(1)} y1={MT}
          x2={toX(hoveredIdx, n).toFixed(1)} y2={MT + CH}
          stroke="#cbd5e1" strokeWidth={1} strokeDasharray="3,3" pointerEvents="none"
        />
      )}

      {/* 라인 */}
      {activeAssets.map(a => {
        const vals = pd.d[a];
        if (!vals) return null;
        const col = ASSETS[a].color;
        const isFx = a.startsWith('KRW/');
        const isKospi = a === '000000';
        const isDimmed = hoveredAsset !== null && hoveredAsset !== a;

        const strokeDasharray = isKospi ? '1,5' : isFx ? '7,4' : undefined;
        const strokeLinecap = isFx ? 'butt' : 'round';
        const strokeWidth = isKospi ? 2.5 : isFx ? 1.8 : 2;

        const segments = [];
        let seg = [];
        vals.forEach((v, i) => {
          if (v === null) {
            if (seg.length > 1) segments.push([...seg]);
            seg = [];
          } else {
            seg.push(`${toX(i, n).toFixed(1)},${toY(v, minV, maxV).toFixed(1)}`);
          }
        });
        if (seg.length > 1) segments.push(seg);

        let lastIdx = vals.length - 1;
        while (lastIdx >= 0 && vals[lastIdx] === null) lastIdx--;
        if (lastIdx < 0) return null;
        const lv = vals[lastIdx];
        const lx = toX(lastIdx, n), ly = toY(lv, minV, maxV);
        const sign = lv >= 0 ? '+' : '';

        return (
          <g key={a} style={{ opacity: isDimmed ? 0.15 : 1, transition: 'opacity 0.2s' }}>
            {segments.map((pts, si) => (
              <polyline key={si} points={pts.join(' ')} fill="none" stroke={col}
                strokeLinejoin="round" strokeDasharray={strokeDasharray}
                strokeLinecap={strokeLinecap} strokeWidth={strokeWidth} />
            ))}
            {segments.map((pts, si) => (
              <polyline key={`h${si}`} points={pts.join(' ')} fill="none" stroke="transparent"
                strokeWidth={14} style={{ cursor: 'pointer' }}
                onMouseEnter={e => {
                  onHoverAsset(a);
                  const idx = getIdx(e.clientX);
                  setHoveredIdx(idx);
                  setTooltip(buildTooltip(a, e.clientX, e.clientY));
                }}
                onMouseMove={e => {
                  const idx = getIdx(e.clientX);
                  setHoveredIdx(idx);
                  setTooltip(buildTooltip(a, e.clientX, e.clientY));
                }}
                onMouseLeave={() => { onHoverAsset(null); setTooltip(null); setHoveredIdx(null); }} />
            ))}
          </g>
        );
      })}
    </svg>
    </>
  );
}

async function fetchFavs() {
  try {
    const res = await fetchWithAuth('/api/v1/favorites');
    if (!res.ok) return new Set();
    const { assets } = await res.json();
    return new Set(assets);
  } catch { return new Set(); }
}

async function pushFavs(s, onFail) {
  try {
    const res = await fetchWithAuth('/api/v1/favorites', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assets: [...s] }),
    });
    if (!res.ok) onFail?.();
  } catch { onFail?.(); }
}

function fmtChg(pct) {
  const sign = pct >= 0 ? '▲' : '▼';
  const cls = pct >= 0 ? 'positive' : 'negative';
  return { text: `${sign} ${Math.abs(pct).toFixed(2)}%`, cls };
}

export default function DashboardPage() {
  const [activeAssets, setActiveAssets] = useState([]);
  const [period, setPeriod] = useState('1M');
  const [prices, setPrices] = useState({});
  const [chartPd, setChartPd] = useState(null);
  const [hoveredAsset, setHoveredAsset] = useState(null);
  const [legend, setLegend] = useState([]);
  const [favs, setFavs] = useState(new Set());
  const [detailStockId, setDetailStockId] = useState(null);
  const [complexData, setComplexData] = useState({});
  const [rightOpen, setRightOpen] = useState(false);
  const [newsDrawerOpen, setNewsDrawerOpen] = useState(false);
  const [selectedFavId, setSelectedFavId] = useState(null);
  const [favDetail, setFavDetail] = useState(null);
  const [favDetailLoading, setFavDetailLoading] = useState(false);
  const [favNewsExpanded, setFavNewsExpanded] = useState(null);
  const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

  useEffect(() => {
    const raw = sessionStorage.getItem('whai_prefetch');
    if (raw) {
      try {
        const cache = JSON.parse(raw);
        sessionStorage.removeItem('whai_prefetch');
        if (cache.favs) setFavs(new Set(cache.favs.assets || []));
        if (cache.prices) setPrices(prev => {
          const next = { ...prev };
          cache.prices.forEach(({ ticker, close, change_pct, change }) => {
            next[ticker] = { price: close, change_pct, change };
          });
          return next;
        });
        if (cache.rates) setPrices(prev => {
          const next = { ...prev };
          cache.rates.forEach(({ pair, rate, change_pct, change }) => {
            next[pair] = { price: rate, change_pct, change, isRate: true };
          });
          return next;
        });
      } catch { /* silent */ }
    }
    fetchFavs().then(favSet => {
      setFavs(favSet);
      const favArr = [...favSet].filter(id => ASSETS[id]);
      setActiveAssets([...favArr]);
      const firstStock = favArr.find(id => STOCK_CONFIG[id]);
      if (firstStock) setSelectedFavId(firstStock);
    });
    loadLatestPrices();
    loadLatestRates();
  }, []);

  useEffect(() => {
    if (selectedFavId) loadFavDetail(selectedFavId);
  }, [selectedFavId]);

  useEffect(() => {
    renderChart();
  }, [activeAssets, period, prices]);


  async function loadLatestPrices() {
    try {
      const res = await fetchWithAuth('/api/v1/prices/latest');
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

  async function loadFavDetail(id) {
    if (!STOCK_CONFIG[id]) return;
    setFavDetailLoading(true);
    setFavDetail(null);
    setFavNewsExpanded(null);
    try {
      const [priceRes, statsRes, newsRes] = await Promise.all([
        fetchWithAuth('/api/v1/prices/latest'),
        fetchWithAuth(`/api/v1/prices/${id}/stats`),
        fetchWithAuth(`/api/v1/news?ticker=${id}&days=90`),
      ]);
      const allPrices = priceRes.ok ? await priceRes.json() : [];
      const row = allPrices.find(r => r.ticker === id);
      const stats = statsRes.ok ? await statsRes.json() : null;
      const news = newsRes.ok ? await newsRes.json() : [];
      setFavDetail({ price: row?.close, changePct: row?.change_pct, change: row?.change, stats, news });
    } catch { setFavDetail({ price: null, changePct: null, change: null, stats: null, news: [] }); }
    setFavDetailLoading(false);
  }

  async function loadLatestRates() {
    try {
      const res = await fetchWithAuth('/api/v1/exchange-rates/latest');
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
    if (activeAssets.length === 0) { setChartPd(null); setLegend([]); setComplexData({}); return; }
    await Promise.all(activeAssets.map(id => fetchAssetData(id, period)));
    const pd = buildPeriodData(period, activeAssets);
    setChartPd(pd);
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
    const prev = new Set(favs);
    const next = new Set(favs);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (next.size >= 3) return;
      next.add(id);
    }
    setFavs(next);
    pushFavs(next, () => setFavs(prev));
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
          {d ? (
            <>
              <span className="tk-card-price">{Number(d.price).toLocaleString('ko-KR')}원</span>
              <ChgEl id={id} />
            </>
          ) : (
            <>
              <span className="skeleton" style={{ width: 76, height: 15 }} />
              <span className="skeleton" style={{ width: 54, height: 13 }} />
            </>
          )}
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
          {prices[id] ? (
            <>
              <span className="fx-card-rate">{priceStr(id)}</span>
              <ChgEl id={id} />
            </>
          ) : (
            <>
              <span className="skeleton" style={{ width: 64, height: 15 }} />
              <span className="skeleton" style={{ width: 48, height: 13 }} />
            </>
          )}
        </div>
      </div>
    );
  }

  const kospiInChart = activeAssets.includes('000000');
  const kospiPrice = prices['000000'];

  const complexIds = activeAssets.filter(id => complexData[id]);
  const showComplex = complexIds.length >= 2;

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <NewsDrawer open={newsDrawerOpen} onClose={() => setNewsDrawerOpen(false)} />
      {detailStockId && (
        <StockDetailModal stockId={detailStockId} onClose={() => setDetailStockId(null)} />
      )}
      <div className={`dash-layout${rightOpen ? ' panel-open' : ''}`}>

        {/* LEFT: Chart */}
        <div className="chart-panel">
          <div className="chart-controls">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
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
          </div>

          <div className="active-chips">
            {[...favs].filter(id => ASSETS[id]).map(id => {
              const isSelected = id === selectedFavId;
              const color = ASSETS[id].color;
              return (
                <span
                  key={id}
                  className={`a-chip a-chip-clickable${isSelected ? ' a-chip-active' : ''}`}
                  style={{
                    color: isSelected ? 'white' : color,
                    borderColor: color,
                    background: isSelected ? color : color + '18',
                  }}
                  onClick={() => setSelectedFavId(id)}
                >
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: isSelected ? 'white' : color, display: 'inline-block' }} />
                  {ASSETS[id].label}
                </span>
              );
            })}
          </div>

          <div className="chart-body">
            <div className="chart-main">
              <div className="chart-card">
                {activeAssets.length === 0 && (
                  <div className="chart-empty">
                    <div style={{ fontSize: 48 }}>🖥️</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#334155' }}>종목을 선택해주세요</div>
                    <div style={{ fontSize: 12, color: '#94a3b8' }}>오른쪽 목록에서 종목을 클릭하면 차트가 표시됩니다</div>
                  </div>
                )}
                <div className="chart-svg-wrap">
                  <LineChart activeAssets={activeAssets} pd={chartPd}
                    hoveredAsset={hoveredAsset} onHoverAsset={setHoveredAsset} />
                </div>
                {legend.length > 0 && (
                  <div className="chart-legend">
                    {legend.map(({ id, last }) => {
                      const sign = last >= 0 ? '+' : '';
                      const col = last >= 0 ? '#16a34a' : '#dc2626';
                      const isDimmed = hoveredAsset !== null && hoveredAsset !== id;
                      return (
                        <div key={id} className="leg-item"
                          style={{ opacity: isDimmed ? 0.25 : 1, transition: 'opacity 0.2s', cursor: 'pointer' }}
                          onMouseEnter={() => setHoveredAsset(id)}
                          onMouseLeave={() => setHoveredAsset(null)}>
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
            {showComplex && (
              <div className="matrix-side">
                <div className="matrix-side-title">
                  상관계수 매트릭스
                  <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400 }}>Pearson</span>
                </div>
                {(() => {
                  const n = complexIds.length;
                  const cellH = n <= 6 ? 36 : n <= 8 ? 30 : n <= 12 ? 25 : 22;
                  const cellStyle = { height: cellH, lineHeight: `${cellH}px` };
                  const lbl = id => { const l = shortLabel(id); return n >= 9 ? l.slice(0, 4) : l; };
                  return (
                    <table className="matrix-table">
                      <thead>
                        <tr>
                          <th className="mh" style={cellStyle} />
                          {complexIds.map(id => <th key={id} className="mh" style={cellStyle}>{lbl(id)}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {complexIds.map(row => (
                          <tr key={row}>
                            <th className="mh" style={{ ...cellStyle, textAlign: 'right', paddingRight: 5 }}>{lbl(row)}</th>
                            {complexIds.map(col => {
                              if (row === col) return <td key={col} className="mc" style={{ ...cellStyle, background: '#f1f5f9', border: '1px solid #e2e8f0' }} />;
                              const v = calcPearson(complexData[row], complexData[col]);
                              const { background, color } = corrStyle(v);
                              return <td key={col} className="mc" style={{ ...cellStyle, background, color }}>{v.toFixed(2)}</td>;
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  );
                })()}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 10, color: '#94a3b8' }}>
                  <span>-1.0</span>
                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'linear-gradient(to right,rgb(185,28,28),rgb(248,250,252),rgb(30,64,175))' }} />
                  <span>+1.0</span>
                </div>
                {(() => {
                  let maxV = -Infinity, minV = Infinity;
                  let maxPair = null, minPair = null;
                  for (let i = 0; i < complexIds.length; i++) {
                    for (let j = i + 1; j < complexIds.length; j++) {
                      const v = calcPearson(complexData[complexIds[i]], complexData[complexIds[j]]);
                      if (v > maxV) { maxV = v; maxPair = [complexIds[i], complexIds[j]]; }
                      if (v < minV) { minV = v; minPair = [complexIds[i], complexIds[j]]; }
                    }
                  }
                  return (
                    <div className="ai-box" style={{ marginTop: 8 }}>
                      <div className="ai-header">
                        <span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 상관 분석</span>
                      </div>
                      <div className="ai-text" style={{ fontSize: 11 }}>
                        {maxPair && <div>최강 연동 <b style={{ color: '#4338ca' }}>{shortLabel(maxPair[0])} · {shortLabel(maxPair[1])} ({maxV.toFixed(2)})</b></div>}
                        {minV < 0 && minPair && <div>역상관 <b>{shortLabel(minPair[0])} · {shortLabel(minPair[1])} ({minV.toFixed(2)})</b></div>}
                        <div style={{ marginTop: 4, fontSize: 10, color: '#6d28d9' }}>|r| ≥ 0.7 강함 · 0.3 ~ 0.7 보통 · 0 ~ 0.3 약함</div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>

        {/* 종목 상세 패널 */}
        {(() => {
          const cfg = selectedFavId ? STOCK_CONFIG[selectedFavId] : null;
          const s = favDetail?.stats;
          const chgPct = favDetail?.changePct;
          const chgAmt = favDetail?.change;
          const chgColor = (chgPct ?? 0) >= 0 ? '#16a34a' : '#dc2626';
          const chgArrow = (chgPct ?? 0) >= 0 ? '▲' : '▼';
          function fmt(v) { return v ? Number(v).toLocaleString('ko-KR') : '—'; }
          function fmtVol(v) {
            if (!v) return '—';
            if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
            if (v >= 1_000) return (v / 1_000).toFixed(0) + 'K';
            return String(v);
          }
          function fmtCap(v) {
            if (!v) return '—';
            const jo = v / 1e12;
            return jo >= 1 ? jo.toFixed(1) + '조원' : (v / 1e8).toFixed(1) + '억원';
          }
          return (
            <div className="ai-main-panel">
              {/* 종목 헤더 + 주요 지표 */}
              <div className="ai-main-card" style={{ flex: 2 }}>
                {cfg && (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <div style={{ width: 32, height: 32, borderRadius: 7, background: '#fff', border: '1px solid #e8ecf0', padding: 3, overflow: 'hidden', flexShrink: 0 }}>
                        <img src={`/assets/logos/${cfg.logo}`} alt={cfg.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                      </div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 800, color: '#1e293b' }}>{cfg.name} <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>{selectedFavId}</span></div>
                        <div style={{ fontSize: 10, color: '#94a3b8' }}>{cfg.meta}</div>
                      </div>
                      {favDetail?.price && (
                        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                          <div style={{ fontSize: 15, fontWeight: 800 }}>{Number(favDetail.price).toLocaleString('ko-KR')}<span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>원</span></div>
                          {chgPct != null && (
                            <div style={{ fontSize: 11, fontWeight: 600, color: chgColor }}>{chgArrow} {chgAmt != null ? `${fmt(Math.abs(chgAmt))}원` : ''} ({Math.abs(chgPct).toFixed(2)}%)</div>
                          )}
                        </div>
                      )}
                    </div>
                    <div style={{ borderTop: '1px solid #f1f5f9', marginBottom: 8 }} />
                  </>
                )}
                <div className="ai-main-title" style={{ marginBottom: 10 }}>주요 지표</div>
                {favDetailLoading ? (
                  <div className="grid g11" style={{ gap: 7 }}>
                    {[0,1,2,3,4,5].map(i => <div key={i} className="metric-box"><span className="skeleton" style={{ width: '60%', height: 12 }} /><span className="skeleton" style={{ width: '40%', height: 16, marginTop: 4 }} /></div>)}
                  </div>
                ) : !cfg ? (
                  <div style={{ color: '#94a3b8', fontSize: 12, textAlign: 'center', padding: '8px 0' }}>관심종목을 선택해주세요</div>
                ) : (
                  <div className="grid g11" style={{ gap: 7 }}>
                    <div className="metric-box"><div className="metric-label">거래량</div><div className="metric-value">{fmtVol(s?.volume)}</div></div>
                    <div className="metric-box"><div className="metric-label">시가총액</div><div className="metric-value" style={{ whiteSpace: 'nowrap' }}>{fmtCap(s?.market_cap)}</div></div>
                    <div className="metric-box"><div className="metric-label">52주 최고</div><div className="metric-value positive" style={{ whiteSpace: 'nowrap' }}>{s?.high52 ? `${fmt(s.high52)}원` : '—'}</div></div>
                    <div className="metric-box"><div className="metric-label">52주 최저</div><div className="metric-value negative" style={{ whiteSpace: 'nowrap' }}>{s?.low52 ? `${fmt(s.low52)}원` : '—'}</div></div>
                    <div className="metric-box"><div className="metric-label">PER</div><div className="metric-value">{s?.per != null ? s.per.toFixed(2) : <span style={{ fontSize: 12, color: '#94a3b8' }}>적자</span>}</div></div>
                    <div className="metric-box"><div className="metric-label">PBR</div><div className="metric-value">{s?.pbr != null ? s.pbr.toFixed(2) : '—'}</div></div>
                  </div>
                )}
              </div>

              {/* 주가 변동 원인 분석 */}
              {cfg && (
                <div className="ai-main-card" style={{ flex: 3 }}>
                  <div className="ai-main-title" style={{ marginBottom: 10 }}>주가 변동 원인 분석</div>
                  {cfg.factors.map(f => (
                    <div key={f.label}>
                      <div className="factor-row">
                        <div className="factor-label">{f.label}</div>
                        <div className="factor-bar-bg"><div className="factor-fill" style={{ width: `${f.pct}%`, background: f.color }} /></div>
                        <div className={`factor-val ${f.val.startsWith('-') ? 'negative' : 'positive'}`}>{f.val}</div>
                      </div>
                      <div className="factor-desc">{f.desc}</div>
                    </div>
                  ))}
                </div>
              )}

            </div>
          );
        })()}

        {/* NEWS column */}
        <div className="news-col">
          <div className="news-preview-card" style={{ flex: 1, overflow: 'hidden' }}>
            <div className="news-preview-header">
              <div className="news-preview-title">
                <span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
                관련 뉴스{selectedFavId && STOCK_CONFIG[selectedFavId] ? ` — ${STOCK_CONFIG[selectedFavId].name}` : ''}
              </div>
              <button className="news-preview-more" onClick={() => setNewsDrawerOpen(true)}>전체 보기 →</button>
            </div>
            {favDetailLoading ? (
              [0, 1, 2].map(i => (
                <div key={i} className="news-preview-item">
                  <div className="news-meta" style={{ gap: 6 }}>
                    <span className="skeleton" style={{ width: 48, height: 16, borderRadius: 6 }} />
                    <span className="skeleton" style={{ width: 56, height: 12 }} />
                  </div>
                  <span className="skeleton" style={{ width: '100%', height: 13, marginTop: 6 }} />
                </div>
              ))
            ) : !favDetail || favDetail.news.length === 0 ? (
              <div style={{ color: '#94a3b8', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
                {selectedFavId && STOCK_CONFIG[selectedFavId] ? '관련 뉴스가 없습니다.' : '관심종목을 선택해주세요'}
              </div>
            ) : favNewsExpanded !== null ? (
              (() => { const n = favDetail.news[favNewsExpanded]; return (
                <div className="news-preview-item" style={{ cursor: 'pointer' }} onClick={() => setFavNewsExpanded(null)}>
                  <div className="news-meta">
                    <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>{n.direction || '혼조'}</span>
                    <span className="news-date" style={{ marginLeft: 'auto' }}>{n.start_date} ~ {n.end_date}</span>
                  </div>
                  <div className="news-title" style={{ fontSize: 12, marginBottom: 8 }}>{n.cause}</div>
                  {n.vol_insight && (
                    <div style={{ background: 'rgba(255,255,255,0.75)', border: '1px solid #ddd6fe', borderRadius: 8, padding: '10px 12px' }}>
                      <div style={{ fontSize: 11, color: '#334155', lineHeight: 1.7 }}>{n.vol_insight}</div>
                    </div>
                  )}
                </div>
              ); })()
            ) : favDetail.news.slice(0, 5).map((n, i) => (
              <div key={i} className="news-preview-item" style={{ cursor: 'pointer' }} onClick={() => setFavNewsExpanded(i)}>
                <div className="news-meta">
                  <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>{n.direction || '혼조'}</span>
                  <span className="news-date" style={{ marginLeft: 'auto' }}>{n.start_date} ~ {n.end_date}</span>
                </div>
                <div className="news-title" style={{ fontSize: 12 }}>{n.cause}</div>
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
          <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <div className="panel-section-label">KOSPI 지수</div>
              <div
                className={`tk-card${kospiInChart ? ' in-chart' : ''}`}
                onClick={() => toggleAsset('000000')}
              >
                <div className="tk-card-head">
                  <div className="tk-card-logo">
                    <img src="/assets/flags/kr.png" alt="KOSPI" />
                  </div>
                  <div className="tk-card-name">KOSPI 지수</div>
                </div>
                <div className="tk-card-bottom">
                  {kospiPrice ? (
                    <>
                      <span className="tk-card-price">{Number(kospiPrice.price).toLocaleString('ko-KR')}</span>
                      <ChgEl id="000000" />
                    </>
                  ) : (
                    <>
                      <span className="skeleton" style={{ width: 76, height: 15 }} />
                      <span className="skeleton" style={{ width: 54, height: 13 }} />
                    </>
                  )}
                </div>
              </div>
            </div>

            <div>
              <div className="panel-section-label">KRX 주요 종목</div>
              <div className="stock-grid">
                {STOCK_SECTORS.flatMap(s => s.ids).map(id => (
                  <TkCard key={id} id={id} name={STOCK_NAMES[id]} />
                ))}
              </div>
            </div>

            <div>
              <div className="panel-section-label">주요국 환율</div>
              <div className="fx-grid">
                {Object.keys(FX_INFO).map(id => <FxCard key={id} id={id} />)}
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
