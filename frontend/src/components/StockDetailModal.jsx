'use client';
import { useState, useEffect } from 'react';
import { fetchWithAuth } from '@/lib/auth';

export const STOCK_CONFIG = {
  '005930': { name: '삼성전자', sector: '반도체', meta: '코스피 · 반도체', logo: 'samsung.svg', color: '#034EA2',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 수요 증가', pct: 42, color: '#7c3aed', val: '+42%', desc: 'AI 서버향 HBM3E 수요 급증' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000660': { name: 'SK하이닉스', sector: '반도체', meta: '코스피 · 반도체', logo: 'skhynix.svg', color: '#E31837',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 28, color: '#2563eb', val: '+28%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 공급 선도', pct: 55, color: '#7c3aed', val: '+55%', desc: 'HBM 독점 공급 구조 확립' },
              { label: '환율 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원화 강세 → 반도체 수출 수익 감소' }] },
  '005380': { name: '현대차', sector: '자동차', meta: '코스피 · 자동차', logo: 'hyundai.png', color: '#002C5F',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '전동화 전환 성과', pct: 38, color: '#7c3aed', val: '+38%', desc: 'EV 판매 증가 및 프리미엄화 전략' },
              { label: '환율 영향', pct: 12, color: '#dc2626', val: '-12%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000270': { name: '기아', sector: '자동차', meta: '코스피 · 자동차', logo: 'kia.png', color: '#C8102E',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 44, color: '#2563eb', val: '+44%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'EV9 판매 호조', pct: 38, color: '#7c3aed', val: '+38%', desc: '북미·유럽 전기 SUV 수요 급증' },
              { label: '환율 영향', pct: 10, color: '#dc2626', val: '-10%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '079550': { name: 'LIG디펜스앤에어로스페이스', sector: '방산', meta: '코스피 · 방산', logo: 'lignex1.svg', color: '#0077C8',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 18, color: '#2563eb', val: '+18%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 확대', pct: 68, color: '#7c3aed', val: '+68%', desc: 'K2 전차·K9 자주포 수출 계약 증가' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '012450': { name: '한화에어로스페이스', sector: '방산', meta: '코스피 · 방산', logo: 'hanwha.svg', color: '#ED7100',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 32, color: '#2563eb', val: '+32%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 이슈', pct: 52, color: '#7c3aed', val: '+52%', desc: '폴란드·루마니아 수출 계약 뉴스 영향' },
              { label: '환율 영향', pct: 6, color: '#dc2626', val: '-6%', desc: '원화 강세 → 수출 수익 환산 시 감소' }] },
  '105560': { name: 'KB금융', sector: '금융', meta: '코스피 · 금융', logo: 'kb.svg', color: '#D4960A',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 48, color: '#2563eb', val: '+48%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 38, color: '#7c3aed', val: '+38%', desc: '순이자마진(NIM) 개선 효과' },
              { label: '대손충당금 증가', pct: 8, color: '#dc2626', val: '-8%', desc: '부동산 PF 리스크 반영' }] },
  '055550': { name: '신한지주', sector: '금융', meta: '코스피 · 금융', logo: 'shinhan.svg', color: '#5BADD1',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 45, color: '#2563eb', val: '+45%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 35, color: '#7c3aed', val: '+35%', desc: '이자이익 증가 효과' },
              { label: '대출 부실 위험', pct: 9, color: '#dc2626', val: '-9%', desc: '기업 구조조정 관련 충당금 부담' }] },
  '051910': { name: 'LG화학', sector: '화학', meta: '코스피 · 화학', logo: 'lgchem.svg', color: '#A50034',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 사업 부진', pct: 48, color: '#dc2626', val: '-48%', desc: 'EV 배터리 수요 둔화 및 가격 하락' },
              { label: '글로벌 수요 약세', pct: 18, color: '#dc2626', val: '-18%', desc: '화학 제품 수요 둔화' }] },
  '096770': { name: 'SK이노베이션', sector: '화학', meta: '코스피 · 화학', logo: 'skinnovation.svg', color: '#F46F19',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 수주 증가', pct: 45, color: '#7c3aed', val: '+45%', desc: '북미 배터리 공장 가동률 상승' },
              { label: '유가 변동 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원유 가격 하락 → 화학 부문 수익성 압박' }] },
};

const PERIOD_LABELS = { '1W': '1주', '1M': '1개월', '3M': '3개월', '6M': '6개월', '1Y': '1년', '3Y': '3년', 'ALL': '전체' };
const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

function buildChartSvg(vals, color, labels = []) {
  const W = 500, H = 220, ML = 38, MR = 8, MT = 10, MB = 18;
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
    h += `<line x1="${ML}" y1="${y}" x2="${W - MR}" y2="${y}" stroke="${isZero ? '#94a3b8' : '#e8edf2'}" stroke-width="${isZero ? 2 : 1}" ${isZero ? '' : 'stroke-dasharray="3,3"'}/>`;
    const lbl = (v >= 0 ? '+' : '') + v.toFixed(v % 1 === 0 ? 0 : 1) + '%';
    h += `<text x="${ML - 3}" y="${(+y + 3.5).toFixed(1)}" text-anchor="end" font-size="9" fill="${isZero ? '#94a3b8' : '#94a3b8'}" font-weight="${isZero ? 700 : 400}">${lbl}</text>`;
  });
  const pts = vals.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const zeroY = toY(0).toFixed(1);
  const x0 = toX(0).toFixed(1), xN = toX(n - 1).toFixed(1);
  const lastY = toY(vals[n - 1]).toFixed(1);
  h += `<polygon points="${pts} ${xN},${zeroY} ${x0},${zeroY}" fill="url(#sg)"/>`;
  h += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  if (labels.length === n && n > 1) {
    const labelStep = Math.max(1, Math.ceil(n / 4));
    const labelIndices = [];
    for (let i = 0; i < n; i += labelStep) labelIndices.push(i);
    if (labelIndices[labelIndices.length - 1] !== n - 1) labelIndices.push(n - 1);
    const labelY = (MT + CH + 13).toFixed(1);
    labelIndices.forEach((i, pos) => {
      const anchor = pos === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle');
      h += `<text x="${toX(i).toFixed(1)}" y="${labelY}" text-anchor="${anchor}" font-size="9" fill="#94a3b8">${labels[i]}</text>`;
    });
  }
  return h;
}

export default function StockDetailModal({ stockId, onClose }) {
  const [period, setPeriod] = useState('3M');
  const [state, setState] = useState('loading');
  const [stockData, setStockData] = useState(null);
  const [chartSvg, setChartSvg] = useState('');
  const [chartLabels, setChartLabels] = useState([]);
  const [news, setNews] = useState([]);
  const [expandedNews, setExpandedNews] = useState(null);

  useEffect(() => {
    setPeriod('3M');
    loadStock(stockId, '3M');
  }, [stockId]);

  async function loadStock(id, p) {
    setState('loading');
    const cfg = STOCK_CONFIG[id];
    if (!cfg) { setState('empty'); return; }
    const [priceData, histData, newsData] = await Promise.all([
      loadPrice(id), loadChart(id, p), loadNews(id),
    ]);
    setStockData({ cfg, ...priceData, chartPos: histData?.pos });
    if (histData) {
      setChartSvg(buildChartSvg(histData.vals, cfg.color, histData.labels));
      setChartLabels(histData.labels);
    }
    setNews(newsData);
    setState('content');
  }

  async function loadPrice(ticker) {
    let price = null, changePct = null, stats = null;
    try {
      const res = await fetchWithAuth('/api/v1/prices/latest');
      if (res.ok) {
        const all = await res.json();
        const row = all.find(r => r.ticker === ticker);
        if (row) { price = row.close; changePct = row.change_pct; }
      }
    } catch { /* silent */ }
    try {
      const res = await fetchWithAuth(`/api/v1/prices/${ticker}/stats`);
      if (res.ok) stats = await res.json();
    } catch { /* silent */ }
    return { price, changePct, stats };
  }

  async function loadChart(ticker, p) {
    try {
      const res = await fetchWithAuth(`/api/v1/prices/${ticker}/history?period=${p}`);
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
      const res = await fetchWithAuth(`/api/v1/news?ticker=${ticker}&days=90`);
      return res.ok ? await res.json() : [];
    } catch { return []; }
  }

  async function changePeriod(p) {
    setPeriod(p);
    const cfg = STOCK_CONFIG[stockId];
    if (!cfg) return;
    const histData = await loadChart(stockId, p);
    if (histData) {
      setChartSvg(buildChartSvg(histData.vals, cfg.color, histData.labels));
      setChartLabels(histData.labels);
      setStockData(prev => prev ? { ...prev, chartPos: histData.pos } : prev);
    }
  }

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
    if (jo >= 1) return jo.toFixed(1) + '조원';
    return (v / 1e8).toFixed(1) + '억원';
  }

  const cfg = STOCK_CONFIG[stockId];
  const s = stockData?.stats;
  const chgAmt = s?.change;
  const chgPct = stockData?.changePct;
  const chgColor = (chgPct ?? 0) >= 0 ? '#16a34a' : '#dc2626';
  const chgArrow = (chgPct ?? 0) >= 0 ? '▲' : '▼';

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box" style={{ width: 1240, maxWidth: '98vw', padding: 0 }}>

        {/* 헤더 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid #e2e8f0', borderRadius: '16px 16px 0 0' }}>
          {cfg && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#fff', border: '1px solid #e8ecf0', padding: 3, overflow: 'hidden' }}>
                <img src={`/assets/logos/${cfg.logo}`} alt={cfg.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              </div>
              <div>
                <div style={{ fontSize: 16, fontWeight: 800 }}>{cfg.name} <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 500 }}>{stockId}</span></div>
                <div style={{ fontSize: 10, color: '#94a3b8' }}>{cfg.meta}</div>
              </div>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {state === 'content' && stockData?.price && (
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{ fontSize: 20, fontWeight: 800 }}>
                  {Number(stockData.price).toLocaleString('ko-KR')}
                  <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 400 }}>원</span>
                </span>
                {chgPct != null && (
                  <>
                    <span style={{ fontSize: 13, fontWeight: 700, color: chgColor }}>
                      {chgArrow} {chgAmt != null ? `${fmt(Math.abs(chgAmt))}원` : ''}
                    </span>
                    <span style={{ fontSize: 12, color: chgColor }}>
                      ({Math.abs(chgPct).toFixed(2)}%)
                    </span>
                  </>
                )}
              </div>
            )}
            <button className="btn btn-ghost" style={{ padding: '4px 12px', fontSize: 13 }} onClick={onClose}>✕</button>
          </div>
        </div>

        {/* 바디: 좌(차트+지표+원인분석) | 우(뉴스) */}
        <div style={{ padding: '20px' }}>
          {state === 'loading' && (
            <div style={{ textAlign: 'center', padding: '50px 0', color: '#94a3b8', fontSize: 14 }}>데이터를 불러오는 중...</div>
          )}

          {state === 'content' && cfg && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 14 }}>

              {/* 좌측: 차트+지표 + 원인분석 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div className="grid g21">
                  <div className="other-card">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>주가 차트 (변동률)</div>
                      <div className="range-sel">
                        {PERIODS.map(p => (
                          <div key={p} className={`rbtn${period === p ? ' active' : ''}`} onClick={() => changePeriod(p)}>{PERIOD_LABELS[p]}</div>
                        ))}
                      </div>
                    </div>
                    <svg viewBox="0 0 500 220" width="100%" height={210} style={{ display: 'block' }} dangerouslySetInnerHTML={{ __html: chartSvg }} />
                  </div>

                  <div className="other-card" style={{ display: 'flex', flexDirection: 'column' }}>
                    <div className="other-card-title">주요 지표</div>
                    <div className="grid g11" style={{ gap: 7, flex: 1, alignContent: 'space-between' }}>
                      <div className="metric-box"><div className="metric-label">거래량</div><div className="metric-value">{fmtVol(s?.volume)}</div></div>
                      <div className="metric-box"><div className="metric-label">시가총액</div><div className="metric-value" style={{ whiteSpace: 'nowrap' }}>{fmtCap(s?.market_cap)}</div></div>
                      <div className="metric-box"><div className="metric-label">52주 최고</div><div className="metric-value positive" style={{ whiteSpace: 'nowrap' }}>{s?.high52 ? `${fmt(s.high52)}원` : '—'}</div></div>
                      <div className="metric-box"><div className="metric-label">52주 최저</div><div className="metric-value negative" style={{ whiteSpace: 'nowrap' }}>{s?.low52 ? `${fmt(s.low52)}원` : '—'}</div></div>
                      <div className="metric-box">
                        <div className="metric-label">PER</div>
                        <div className="metric-value">{s?.per != null ? s.per.toFixed(2) : <span style={{ fontSize: 12, color: '#94a3b8' }}>적자</span>}</div>
                      </div>
                      <div className="metric-box"><div className="metric-label">PBR</div><div className="metric-value">{s?.pbr != null ? s.pbr.toFixed(2) : '-'}</div></div>
                    </div>
                  </div>
                </div>

                <div className="other-card">
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

              {/* 우측: 뉴스 */}
              <div className="other-card" style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="other-card-title">관련 뉴스</div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {news.length === 0 ? (
                    <div style={{ color: '#94a3b8', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>관련 뉴스가 없습니다.</div>
                  ) : expandedNews !== null ? (
                    (() => {
                      const n = news[expandedNews];
                      return (
                        <div className="news-item" style={{ cursor: 'pointer' }} onClick={() => setExpandedNews(null)}>
                          <div className="news-meta">
                            <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>
                              {n.direction || '혼조'}
                            </span>
                            <span className="news-date">{n.start_date} ~ {n.end_date}</span>
                          </div>
                          {n.cause && <div className="news-title" style={{ marginBottom: 8 }}>{n.cause}</div>}
                          {(n.cause || n.vol_insight) && (
                            <div className="ai-box" style={{ padding: '10px 12px' }}>
                              <div className="ai-header" style={{ marginBottom: 6 }}>
                                <span className="ai-badge" style={{ fontSize: 9 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 장세 분석</span>
                              </div>
                              {n.cause && <div className="ai-text" style={{ fontSize: 11, marginBottom: 4 }}>{n.cause}</div>}
                              {n.vol_insight && <div className="ai-text" style={{ fontSize: 11, color: '#4338ca' }}>{n.vol_insight}</div>}
                            </div>
                          )}
                        </div>
                      );
                    })()
                  ) : (
                    news.slice(0, 5).map((n, i) => (
                      <div key={i} className="news-item" style={{ cursor: 'pointer' }} onClick={() => setExpandedNews(i)}>
                        <div className="news-meta">
                          <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>
                            {n.direction || '혼조'}
                          </span>
                          <span className="news-date">{n.start_date} ~ {n.end_date}</span>
                        </div>
                        {n.cause && <div className="news-title">{n.cause}</div>}
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
