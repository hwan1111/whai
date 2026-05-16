'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '@/lib/auth';
import { ASSETS, EXCHANGE_PAIRS, fetchAssetData, buildPeriodData } from '@/lib/data';

const SW = 860, SH = 300, ML = 52, MR = 72, MT = 22, MB = 38;
const CW = SW - ML - MR, CH = SH - MT - MB;
const FAV_KEY = 'whai_favorites';

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

const IND_GROUPS = [
  { label: '지수',   ids: ['000000'] },
  { label: '반도체', ids: ['005930', '000660'] },
  { label: '자동차', ids: ['005380', '000270'] },
  { label: '방산',   ids: ['079550', '012450'] },
  { label: '금융',   ids: ['105560', '055550'] },
  { label: '화학',   ids: ['051910', '096770'] },
  { label: '환율',   ids: ['KRW/USD', 'KRW/JPY', 'KRW/EUR', 'KRW/CNY', 'KRW/CHF', 'KRW/GBP'] },
];

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

function getFavs() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY)) || []); }
  catch { return new Set(); }
}
function saveFavs(s) { localStorage.setItem(FAV_KEY, JSON.stringify([...s])); }

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
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropRef = useRef(null);

  const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

  useEffect(() => {
    setFavs(getFavs());
    loadLatestPrices();
    loadLatestRates();
  }, []);

  useEffect(() => {
    renderChart();
  }, [activeAssets, period, prices]);

  useEffect(() => {
    function handler(e) {
      if (dropRef.current && !dropRef.current.contains(e.target)) setDropdownOpen(false);
    }
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  async function loadLatestPrices() {
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('/api/v1/prices/latest', { headers });
      if (!res.ok) return;
      const data = await res.json();
      setPrices(prev => {
        const next = { ...prev };
        data.forEach(({ ticker, close, change_pct }) => {
          next[ticker] = { price: close, change_pct };
        });
        return next;
      });
    } catch { /* silent */ }
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
        data.forEach(({ pair, rate, change_pct }) => {
          next[pair] = { price: rate, change_pct, isRate: true };
        });
        return next;
      });
    } catch { /* silent */ }
  }

  async function renderChart() {
    if (activeAssets.length === 0) { setChartSvg(''); setLegend([]); return; }
    await Promise.all(activeAssets.map(id => fetchAssetData(id, period)));
    const pd = buildPeriodData(period, activeAssets);
    const svg = renderChartSvg(activeAssets, pd);
    setChartSvg(svg);
    setLegend(activeAssets.map(a => {
      const vals = pd?.d[a];
      const last = vals ? (vals.filter(v => v !== null).pop() ?? 0) : 0;
      return { id: a, last };
    }));
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
    saveFavs(next);
    setFavs(new Set(next));
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

  function StarBtn({ id }) {
    const starred = favs.has(id);
    return (
      <button
        className={`star-btn${starred ? ' starred' : ''}`}
        onClick={e => toggleFav(id, e)}
      >
        {starred ? '★' : '☆'}
      </button>
    );
  }

  function TkRow({ id, name, longName }) {
    const inChart = activeAssets.includes(id);
    return (
      <div className={`tk-row${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)}>
        <div className="tk-left">
          <StarBtn id={id} />
          <div className="tk-icon logo" style={{ width: 28, height: 28, borderRadius: 6 }}>
            <img src={LOGO(id)} alt={name} />
          </div>
          <div>
            <div className="tk-name" style={longName ? { fontSize: 11 } : {}}>{name}</div>
            <div className="tk-code">{id}</div>
          </div>
        </div>
        <div className="tk-right">
          <div className="tk-price">{prices[id] ? Number(prices[id].price).toLocaleString('ko-KR') + '원' : '—'}</div>
          <ChgEl id={id} />
        </div>
      </div>
    );
  }

  function FxRow({ id }) {
    const info = FX_INFO[id];
    const inChart = activeAssets.includes(id);
    return (
      <div className={`ex-row${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)}>
        <div className="ex-left">
          <StarBtn id={id} />
          <img className="ex-flag" src={info.flag} alt={id} />
          <div>
            <div className="pair-code">KRW / {id.split('/')[1]}</div>
            <div className="pair-desc">{info.desc}</div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 12, fontWeight: 700 }}>{priceStr(id)}</div>
          <ChgEl id={id} />
        </div>
      </div>
    );
  }

  const kospiInChart = activeAssets.includes('000000');
  const kospiPrice = prices['000000'];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="dash-layout">

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
              <div className="ind-dropdown-wrap" ref={dropRef}>
                <button className="btn-add-ind" onClick={e => { e.stopPropagation(); setDropdownOpen(o => !o); }}>
                  ＋ 지표 추가
                </button>
                {dropdownOpen && (
                  <div className="ind-dropdown">
                    {IND_GROUPS.map(g => (
                      <div key={g.label}>
                        <div className="ind-group-label">{g.label}</div>
                        {g.ids.map(id => (
                          <div
                            key={id}
                            className={`ind-option${activeAssets.includes(id) ? ' checked' : ''}`}
                            onClick={() => toggleAsset(id)}
                          >
                            <div className="ind-dot" style={{ background: ASSETS[id].color }} />
                            <span>{ASSETS[id].label}</span>
                            {activeAssets.includes(id) && <span className="ind-check">✓</span>}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
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

        {/* RIGHT panel */}
        <div className="right-panel">
          {/* Favorites */}
          <div className="card">
            <div className="card-title">⭐ 즐겨찾기</div>
            {favs.size === 0 ? (
              <div className="fav-empty">별 아이콘을 눌러 추가하세요</div>
            ) : (
              [...favs].map(id => {
                if (!ASSETS[id]) return null;
                const inChart = activeAssets.includes(id);
                const d = prices[id];
                const isFx = EXCHANGE_PAIRS.has(id);
                let ps = '—', chgText = '—', chgCls = 'tk-chg';
                if (d) {
                  ps = isFx ? Number(d.price).toLocaleString('ko-KR') : Number(d.price).toLocaleString('ko-KR') + '원';
                  if (d.change_pct !== undefined) {
                    const { text, cls } = fmtChg(d.change_pct);
                    chgText = text; chgCls = `tk-chg ${cls}`;
                  }
                }
                const icon = isFx
                  ? <img className="ex-flag" src={FX_INFO[id]?.flag} alt={id} style={{ width: 20, height: 14 }} />
                  : <div className="tk-icon logo" style={{ width: 22, height: 22, borderRadius: 5 }}><img src={LOGO(id)} alt={id} /></div>;
                return (
                  <div key={id} className={`fav-row${inChart ? ' in-chart' : ''}`} onClick={() => toggleAsset(id)}>
                    <div className="fav-left">
                      <button className="star-btn starred" onClick={e => toggleFav(id, e)}>★</button>
                      {icon}
                      <div style={{ minWidth: 0 }}>
                        <div className="fav-name">{ASSETS[id].label}</div>
                        <div className="tk-code">{isFx ? (FX_INFO[id]?.desc || id) : id}</div>
                      </div>
                    </div>
                    <div className="fav-right">
                      <div className="fav-price">{ps}</div>
                      <div className={chgCls}>{chgText}</div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Watchlist */}
          <div className="card">
            <div className="card-title">
              종목 현황
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>클릭하면 차트에 추가</span>
            </div>
            {STOCK_SECTORS.map(({ label, ids }) => (
              <div key={label}>
                <div className="sect-label">{label}</div>
                {ids.map(id => (
                  <TkRow key={id} id={id} name={STOCK_NAMES[id]} longName={id === '079550' || id === '012450'} />
                ))}
              </div>
            ))}
          </div>

          {/* Exchange rates */}
          <div className="card">
            <div className="card-title">
              환율 현황
              <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>클릭하면 차트에 추가</span>
            </div>
            {Object.keys(FX_INFO).map(id => <FxRow key={id} id={id} />)}
          </div>

          {/* AI Summary */}
          <div className="ai-box">
            <div className="ai-header">
              <span className="ai-badge">AI</span>
              <span className="ai-title">오늘의 시장 요약</span>
            </div>
            <div className="ai-text">방산주 강세 지속. 달러 약세로 수출주 단기 환율 리스크. 반도체는 HBM 수요 기반 상승 모멘텀 유지 중.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
