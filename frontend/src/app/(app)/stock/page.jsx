'use client';
import { useState } from 'react';
import { getToken } from '@/lib/auth';

const STOCK_CONFIG = {
  '005930': { name: '삼성전자', sector: '반도체', meta: '코스피 · 반도체 · KRX · KRW', logo: 'samsung.svg', color: '#034EA2',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 수요 증가', pct: 42, color: '#7c3aed', val: '+42%', desc: 'AI 서버향 HBM3E 수요 급증' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000660': { name: 'SK하이닉스', sector: '반도체', meta: '코스피 · 반도체 · KRX · KRW', logo: 'skhynix.svg', color: '#E31837',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 28, color: '#2563eb', val: '+28%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 공급 선도', pct: 55, color: '#7c3aed', val: '+55%', desc: 'HBM 독점 공급 구조 확립' },
              { label: '환율 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원화 강세 → 반도체 수출 수익 감소' }] },
  '005380': { name: '현대차', sector: '자동차', meta: '코스피 · 자동차 · KRX · KRW', logo: 'hyundai.png', color: '#002C5F',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '전동화 전환 성과', pct: 38, color: '#7c3aed', val: '+38%', desc: 'EV 판매 증가 및 프리미엄화 전략' },
              { label: '환율 영향', pct: 12, color: '#dc2626', val: '-12%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000270': { name: '기아', sector: '자동차', meta: '코스피 · 자동차 · KRX · KRW', logo: 'kia.png', color: '#C8102E',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 44, color: '#2563eb', val: '+44%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'EV9 판매 호조', pct: 38, color: '#7c3aed', val: '+38%', desc: '북미·유럽 전기 SUV 수요 급증' },
              { label: '환율 영향', pct: 10, color: '#dc2626', val: '-10%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '079550': { name: 'LIG디펜스앤에어로스페이스', sector: '방산', meta: '코스피 · 방산 · KRX · KRW', logo: 'lignex1.svg', color: '#0077C8',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 18, color: '#2563eb', val: '+18%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 확대', pct: 68, color: '#7c3aed', val: '+68%', desc: 'K2 전차·K9 자주포 수출 계약 증가' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '012450': { name: '한화에어로스페이스', sector: '방산', meta: '코스피 · 방산 · KRX · KRW', logo: 'hanwha.svg', color: '#ED7100',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 32, color: '#2563eb', val: '+32%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 이슈', pct: 52, color: '#7c3aed', val: '+52%', desc: '폴란드·루마니아 수출 계약 뉴스 영향' },
              { label: '환율 영향', pct: 6, color: '#dc2626', val: '-6%', desc: '원화 강세 → 수출 수익 환산 시 감소' }] },
  '105560': { name: 'KB금융', sector: '금융', meta: '코스피 · 금융 · KRX · KRW', logo: 'kb.svg', color: '#D4960A',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 48, color: '#2563eb', val: '+48%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 38, color: '#7c3aed', val: '+38%', desc: '순이자마진(NIM) 개선 효과' },
              { label: '대손충당금 증가', pct: 8, color: '#dc2626', val: '-8%', desc: '부동산 PF 리스크 반영' }] },
  '055550': { name: '신한지주', sector: '금융', meta: '코스피 · 금융 · KRX · KRW', logo: 'shinhan.svg', color: '#5BADD1',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 45, color: '#2563eb', val: '+45%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 35, color: '#7c3aed', val: '+35%', desc: '이자이익 증가 효과' },
              { label: '대출 부실 위험', pct: 9, color: '#dc2626', val: '-9%', desc: '기업 구조조정 관련 충당금 부담' }] },
  '051910': { name: 'LG화학', sector: '화학', meta: '코스피 · 화학 · KRX · KRW', logo: 'lgchem.svg', color: '#A50034',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 사업 부진', pct: 48, color: '#dc2626', val: '-48%', desc: 'EV 배터리 수요 둔화 및 가격 하락' },
              { label: '글로벌 수요 약세', pct: 18, color: '#dc2626', val: '-18%', desc: '화학 제품 수요 둔화' }] },
  '096770': { name: 'SK이노베이션', sector: '화학', meta: '코스피 · 화학 · KRX · KRW', logo: 'skinnovation.svg', color: '#F46F19',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 수주 증가', pct: 45, color: '#7c3aed', val: '+45%', desc: '북미 배터리 공장 가동률 상승' },
              { label: '유가 변동 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원유 가격 하락 → 화학 부문 수익성 압박' }] },
};

const PERIOD_LABELS = { '1W': '1주', '1M': '1개월', '3M': '3개월', '6M': '6개월', '1Y': '1년', '3Y': '3년', 'ALL': '전체' };
const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

const SECTORS = ['반도체', '자동차', '방산', '금융', '화학'];

function buildChartSvg(vals, color) {
  const W = 500, H = 150, ML = 38, MR = 8, MT = 10, MB = 18;
  const CW = W - ML - MR, CH = H - MT - MB;
  const n = vals.length;

  let minV = Math.min(0, ...vals), maxV = Math.max(0, ...vals);
  const pad = Math.max((maxV - minV) * 0.15, 2);
  minV -= pad; maxV += pad;

  const toX = i => ML + (i / (n - 1)) * CW;
  const toY = v => MT + ((maxV - v) / (maxV - minV)) * CH;

  const range = maxV - minV || 1;
  const rawStep = range / 3;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step = [1, 2, 5, 10].map(s => s * mag).find(s => range / s <= 4) || mag;
  const ticks = [];
  for (let v = Math.ceil(minV / step) * step; v <= maxV + 1e-9; v += step)
    ticks.push(Math.round(v * 100) / 100);

  let h = `<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="${color}" stop-opacity="0.18"/>
    <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
  </linearGradient></defs>`;

  ticks.forEach(v => {
    const y = toY(v).toFixed(1);
    const isZero = Math.abs(v) < 0.01;
    h += `<line x1="${ML}" y1="${y}" x2="${W - MR}" y2="${y}" stroke="${isZero ? '#cbd5e1' : '#f1f5f9'}" stroke-width="${isZero ? 1.5 : 1}" ${isZero ? 'stroke-dasharray="4,3"' : ''}/>`;
    const lbl = (v >= 0 ? '+' : '') + v.toFixed(v % 1 === 0 ? 0 : 1) + '%';
    h += `<text x="${ML - 3}" y="${(+y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${isZero ? '#475569' : '#94a3b8'}" font-weight="${isZero ? 600 : 400}">${lbl}</text>`;
  });

  const pts = vals.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const zeroY = toY(0).toFixed(1);
  const x0 = toX(0).toFixed(1), xN = toX(n - 1).toFixed(1);
  const lastY = toY(vals[n - 1]).toFixed(1);

  h += `<polygon points="${pts} ${xN},${zeroY} ${x0},${zeroY}" fill="url(#sg)"/>`;
  h += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  h += `<circle cx="${xN}" cy="${lastY}" r="3.5" fill="${color}"/>`;
  return h;
}

export default function StockPage() {
  const [currentStock, setCurrentStock] = useState('');
  const [period, setPeriod] = useState('3M');
  const [state, setState] = useState('empty');
  const [stockData, setStockData] = useState(null);
  const [chartSvg, setChartSvg] = useState('');
  const [chartLabels, setChartLabels] = useState([]);
  const [news, setNews] = useState([]);

  const apiHeaders = () => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  async function selectStock(id) {
    if (!id || !STOCK_CONFIG[id]) { setState('empty'); return; }
    setCurrentStock(id);
    setState('loading');

    const cfg = STOCK_CONFIG[id];
    const [priceData, histData, newsData] = await Promise.all([
      loadPrice(id),
      loadChart(id, period),
      loadNews(id),
    ]);

    setStockData({ cfg, ...priceData });
    if (histData) {
      setChartSvg(buildChartSvg(histData.vals, cfg.color));
      setChartLabels(histData.labels);
    }
    setNews(newsData);
    setState('content');
  }

  async function loadPrice(ticker) {
    let price = null, changePct = null, stats = null;
    try {
      const res = await fetch('/api/v1/prices/latest', { headers: apiHeaders() });
      if (res.ok) {
        const all = await res.json();
        const row = all.find(r => r.ticker === ticker);
        if (row) { price = row.close; changePct = row.change_pct; }
      }
    } catch { /* silent */ }
    try {
      const res = await fetch(`/api/v1/prices/${ticker}/stats`, { headers: apiHeaders() });
      if (res.ok) stats = await res.json();
    } catch { /* silent */ }
    return { price, changePct, stats };
  }

  async function loadChart(ticker, p) {
    try {
      const res = await fetch(`/api/v1/prices/${ticker}/history?period=${p}`, { headers: apiHeaders() });
      if (!res.ok) return null;
      const data = await res.json();
      if (!data.length) return null;
      const vals = data.map(d => d.return_pct);
      const labels = data.map(d => { const [, m, day] = d.date.split('-'); return `${+m}/${+day}`; });
      const latest = data[data.length - 1].close;
      const hi = Math.max(...data.map(d => d.close));
      const lo = Math.min(...data.map(d => d.close));
      const pos = hi > lo ? Math.round((latest - lo) / (hi - lo) * 100) : 50;
      return { vals, labels, pos };
    } catch { return null; }
  }

  async function loadNews(ticker) {
    try {
      const res = await fetch(`/api/v1/news?ticker=${ticker}&days=90`, { headers: apiHeaders() });
      return res.ok ? await res.json() : [];
    } catch { return []; }
  }

  async function changePeriod(p) {
    setPeriod(p);
    if (!currentStock) return;
    const histData = await loadChart(currentStock, p);
    if (histData) {
      setChartSvg(buildChartSvg(histData.vals, STOCK_CONFIG[currentStock].color));
      setChartLabels(histData.labels);
      setStockData(prev => prev ? { ...prev, chartPos: histData.pos } : prev);
    }
  }

  const sectors = SECTORS;
  const grouped = {};
  Object.entries(STOCK_CONFIG).forEach(([id, cfg]) => {
    if (!grouped[cfg.sector]) grouped[cfg.sector] = [];
    grouped[cfg.sector].push([id, cfg.name]);
  });

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
    if (jo >= 1) return jo.toFixed(0) + '조';
    return (v / 1e8).toFixed(0) + '억';
  }

  const cfg = currentStock ? STOCK_CONFIG[currentStock] : null;
  const s = stockData?.stats;

  const step2 = Math.max(1, Math.ceil(chartLabels.length / 4));
  const shownLabels = [];
  for (let i = 0; i < chartLabels.length; i += step2) shownLabels.push(chartLabels[i]);
  if (chartLabels.length > 0 && chartLabels[chartLabels.length - 1] !== shownLabels[shownLabels.length - 1])
    shownLabels.push(chartLabels[chartLabels.length - 1]);

  return (
    <>
      <div className="other-card mb">
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 10, color: '#64748b', marginBottom: 3 }}>종목 선택</div>
            <select className="fsel" value={currentStock} onChange={e => selectStock(e.target.value)}>
              <option value="">종목을 선택하세요</option>
              {sectors.map(sector => (
                <optgroup key={sector} label={sector}>
                  {(grouped[sector] || []).map(([id, name]) => (
                    <option key={id} value={id}>{name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        </div>
      </div>

      {state === 'empty' && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: 14 }}>
          <div style={{ fontSize: 40 }}>📊</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#475569' }}>종목을 선택해주세요</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>위 드롭다운에서 분석할 종목을 선택하면 차트와 지표가 표시됩니다</div>
        </div>
      )}

      {state === 'loading' && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0' }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#64748b' }}>데이터를 불러오는 중...</div>
        </div>
      )}

      {state === 'content' && cfg && (
        <>
          <div className="other-card mb" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 46, height: 46, borderRadius: 10, background: '#fff', border: '1px solid #e8ecf0', padding: 3, overflow: 'hidden' }}>
                <img src={`/assets/logos/${cfg.logo}`} alt={cfg.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              </div>
              <div>
                <div style={{ fontSize: 19, fontWeight: 800 }}>
                  {cfg.name} <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>{currentStock}</span>
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{cfg.meta}</div>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 28, fontWeight: 800 }}>
                {stockData?.price ? Number(stockData.price).toLocaleString('ko-KR') : '—'}
                <span style={{ fontSize: 13, color: '#94a3b8', fontWeight: 400 }}> 원</span>
              </div>
              {stockData?.changePct !== null && stockData?.changePct !== undefined && (
                <div style={{ fontSize: 12, marginTop: 2, color: stockData.changePct >= 0 ? '#16a34a' : '#dc2626' }}>
                  {stockData.changePct >= 0 ? '▲' : '▼'} {Math.abs(stockData.changePct).toFixed(2)}% 오늘
                </div>
              )}
            </div>
          </div>

          <div className="grid g21 mb">
            <div className="other-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>주가 차트 (변동률 기준)</div>
                <div className="range-sel">
                  {PERIODS.map(p => (
                    <div key={p} className={`rbtn${period === p ? ' active' : ''}`} onClick={() => changePeriod(p)}>{PERIOD_LABELS[p]}</div>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <svg viewBox="0 0 500 150" width="100%" height={150} style={{ display: 'block' }} dangerouslySetInnerHTML={{ __html: chartSvg }} />
                  <div style={{ display: 'flex', justifyContent: 'space-around', fontSize: 10, color: '#94a3b8', marginTop: 4 }}>
                    {shownLabels.map((l, i) => <span key={i}>{l}</span>)}
                  </div>
                </div>
                <div style={{ width: 88, flexShrink: 0, paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 7 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.5 }}>{PERIOD_LABELS[period]} 범위</div>
                  <div>
                    <div style={{ fontSize: 9, color: '#94a3b8' }}>52주 최고</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#dc2626' }}>{s?.high52 ? fmt(s.high52) + '원' : '—'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: '#94a3b8' }}>52주 최저</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#2563eb' }}>{s?.low52 ? fmt(s.low52) + '원' : '—'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: '#94a3b8' }}>현재가 위치</div>
                    <div style={{ fontSize: 13, fontWeight: 800, color: cfg.color }}>{stockData?.chartPos !== undefined ? stockData.chartPos + '%' : '—'}</div>
                  </div>
                </div>
              </div>
            </div>
            <div className="other-card">
              <div className="other-card-title">주요 지표</div>
              <div className="grid g11" style={{ gap: 7, marginBottom: 12 }}>
                <div className="metric-box"><div className="metric-label">거래량</div><div className="metric-value">{fmtVol(s?.volume)}</div></div>
                <div className="metric-box"><div className="metric-label">시가총액</div><div className="metric-value">{fmtCap(s?.market_cap)}</div></div>
                <div className="metric-box"><div className="metric-label">52주 최고</div><div className="metric-value positive">{fmt(s?.high52)}</div></div>
                <div className="metric-box"><div className="metric-label">52주 최저</div><div className="metric-value negative">{fmt(s?.low52)}</div></div>
                <div className="metric-box">
                  <div className="metric-label">PER</div>
                  <div className="metric-value">
                    {s?.per ? (
                      s.per.toFixed(2)
                    ) : (
                      <>
                        <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b' }}>산출불가</span>
                        <div style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, marginTop: 2 }}>현재 순손실 중인 기업으로<br />PER을 계산할 수 없어요</div>
                      </>
                    )}
                  </div>
                </div>
                <div className="metric-box"><div className="metric-label">PBR</div><div className="metric-value">{s?.pbr ? s.pbr.toFixed(2) : '—'}</div></div>
              </div>
            </div>
          </div>

          <div className="other-card mb">
            <div className="other-card-title">AI 해석 — 통계를 쉽게 이해해 드려요</div>
            <div className="ai-box">
              <div className="ai-header">
                <span className="ai-badge">AI 분석</span>
                <span className="ai-title">{cfg.name} 주가 움직임</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: '#7c6fbb' }}>{PERIOD_LABELS[period]} 기준</span>
              </div>
              <div className="ai-text">종목을 선택하면 AI 분석 내용이 표시됩니다.</div>
              <div className="ai-sources"></div>
            </div>
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 10, color: '#374151' }}>주가 변동 원인 분석</div>
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
          </div>

          <div className="other-card">
            <div className="other-card-title">관련 뉴스</div>
            {news.length === 0 ? (
              <div style={{ color: '#94a3b8', fontSize: 12, padding: '16px 0', textAlign: 'center' }}>관련 뉴스가 없습니다.</div>
            ) : (
              news.map((n, i) => (
                <div key={i} className="news-item">
                  <div className="news-meta">
                    <span className="ticker-tag">{n.ticker}</span>
                    <span className="news-date">{n.date_str}</span>
                    <span className="news-source">{n.source}</span>
                  </div>
                  <div className="news-title">{n.title}</div>
                  <div className="news-body">{n.body}</div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </>
  );
}
