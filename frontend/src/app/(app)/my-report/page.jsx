'use client';
import { useState, useEffect } from 'react';
import { getToken } from '@/lib/auth';

const ASSET_INFO = {
  '005930': { name: '삼성전자',      price: 0, color: '#dc2626', sector: '반도체', unit: '주' },
  '000660': { name: 'SK하이닉스',   price: 0, color: '#16a34a', sector: '반도체', unit: '주' },
  '005380': { name: '현대차',        price: 0, color: '#f59e0b', sector: '자동차', unit: '주' },
  '000270': { name: '기아',          price: 0, color: '#8b5cf6', sector: '자동차', unit: '주' },
  '079550': { name: 'LIG디펜스',    price: 0, color: '#06b6d4', sector: '방산',   unit: '주' },
  '012450': { name: '한화에어로',   price: 0, color: '#f97316', sector: '방산',   unit: '주' },
  '105560': { name: 'KB금융',        price: 0, color: '#6366f1', sector: '금융',   unit: '주' },
  '055550': { name: '신한지주',      price: 0, color: '#0d9488', sector: '금융',   unit: '주' },
  '051910': { name: 'LG화학',        price: 0, color: '#ec4899', sector: '화학',   unit: '주' },
  '096770': { name: 'SK이노베이션', price: 0, color: '#84cc16', sector: '화학',   unit: '주' },
  'KRW/USD': { name: 'USD 달러',    price: 0, color: '#78716c', sector: '외화',   unit: '달러' },
  'KRW/JPY': { name: 'JPY 엔',      price: 0, color: '#a16207', sector: '외화',   unit: '엔' },
  'KRW/EUR': { name: 'EUR 유로',    price: 0, color: '#9333ea', sector: '외화',   unit: '유로' },
  'KRW/CNY': { name: 'CNY 위안',    price: 0, color: '#0891b2', sector: '외화',   unit: '위안' },
  'KRW/CHF': { name: 'CHF 프랑',    price: 0, color: '#0f766e', sector: '외화',   unit: '프랑' },
  'KRW/GBP': { name: 'GBP 파운드', price: 0, color: '#b91c1c', sector: '외화',   unit: '파운드' },
};

const STORE_KEY = 'whai_reports_v2';
const fmt = n => Math.round(n).toLocaleString('ko-KR');
function fmtCompact(n) {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}억원`;
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${fmt(n)}원`;
}

function defaultReports() {
  return [{
    id: 'demo1',
    title: '내 메인 포트폴리오',
    date: '2026.05.06',
    holdings: [
      { id: '005930', qty: 100, avgPrice: 70000 },
      { id: '012450', qty: 5, avgPrice: 400000 },
      { id: '000660', qty: 10, avgPrice: 185000 },
      { id: '051910', qty: 3, avgPrice: 320000 },
    ]
  }];
}

function loadReports() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || defaultReports(); }
  catch { return defaultReports(); }
}
function saveReports(list) { localStorage.setItem(STORE_KEY, JSON.stringify(list)); }

function calcTotals(holdings, prices) {
  const sorted = holdings.map(h => {
    const info = { ...ASSET_INFO[h.id], price: prices[h.id] ?? 0 };
    const curVal = h.qty * info.price;
    const cost = h.qty * h.avgPrice;
    return { ...h, info, curVal, cost };
  }).sort((a, b) => b.curVal - a.curVal);
  const totalVal = sorted.reduce((s, h) => s + h.curVal, 0);
  const totalCost = sorted.reduce((s, h) => s + h.cost, 0);
  return { totalVal, totalCost, sorted };
}

function DonutSvg({ sorted, totalVal }) {
  const r = 42, sw = 18, cx = 60, cy = 60;
  const C = 2 * Math.PI * r;
  const gap = 1.5;
  let paths = '', cum = 0;
  sorted.forEach(h => {
    if (h.curVal <= 0) return;
    const frac = h.curVal / totalVal;
    const len = frac * C;
    const segLen = Math.max(len - gap, 0.1);
    const offset = -cum;
    paths += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${h.info.color || '#94a3b8'}" stroke-width="${sw}" stroke-dasharray="${segLen.toFixed(2)} ${C.toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    cum += len;
  });
  const centerLabel = fmtCompact(totalVal);
  return (
    <svg viewBox="0 0 120 120" style={{ width: 160, height: 160 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
      <g dangerouslySetInnerHTML={{ __html: paths }} />
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize="8" fill="#94a3b8">총 평가액</text>
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize="9.5" fontWeight="800" fill="#1e293b">{centerLabel}</text>
    </svg>
  );
}

function renderAIAnalysis(title, sorted, totalVal) {
  const weights = sorted.map(h => ({
    name: h.info.name || h.id,
    sector: h.info.sector || '기타',
    w: totalVal > 0 ? h.curVal / totalVal * 100 : 0,
    pnlPct: h.cost > 0 ? (h.curVal - h.cost) / h.cost * 100 : 0,
    color: h.info.color || '#94a3b8',
  }));
  const top = weights[0];
  const lines = [];
  if (top.w >= 50) lines.push(`<strong>⚠️ 단일 종목 집중 위험</strong>: <strong>${top.name}</strong> 비중이 <strong>${top.w.toFixed(1)}%</strong>로 전체의 절반 이상을 차지합니다.`);
  else if (top.w >= 35) lines.push(`<strong>📊 비중 점검 권장</strong>: <strong>${top.name}</strong> 비중이 <strong>${top.w.toFixed(1)}%</strong>로 다소 높습니다.`);
  else lines.push(`<strong>✅ 분산 투자 양호</strong>: 가장 높은 비중의 <strong>${top.name}</strong>이 <strong>${top.w.toFixed(1)}%</strong>로 집중 위험이 낮습니다.`);
  const sectors = {};
  weights.forEach(h => { sectors[h.sector] = (sectors[h.sector] || 0) + h.w; });
  const sectorList = Object.entries(sectors).sort((a, b) => b[1] - a[1]);
  const topSector = sectorList[0];
  if (sectorList.length <= 2 && topSector[1] > 60) lines.push(`<strong>🔍 섹터 쏠림 주의</strong>: 포트폴리오의 <strong>${topSector[1].toFixed(0)}%</strong>가 <strong>${topSector[0]}</strong> 섹터에 집중되어 있습니다.`);
  else lines.push(`<strong>📈 섹터 구성</strong>: ${sectorList.slice(0, 3).map(([s, w]) => `${s} ${w.toFixed(0)}%`).join(', ')}.`);
  const losers = weights.filter(h => h.pnlPct < 0);
  const gainers = weights.filter(h => h.pnlPct > 0);
  if (losers.length > 0) {
    const worst = losers.sort((a, b) => a.pnlPct - b.pnlPct)[0];
    lines.push(`<strong>📉 손실 종목 주의</strong>: <strong>${worst.name}</strong>이 <span style="color:#dc2626">${worst.pnlPct.toFixed(1)}%</span> 손실 중입니다.`);
  }
  if (gainers.length > 0) {
    const best = gainers.sort((a, b) => b.pnlPct - a.pnlPct)[0];
    lines.push(`<strong>📈 수익 종목</strong>: <strong>${best.name}</strong>이 <span style="color:#16a34a">+${best.pnlPct.toFixed(1)}%</span>로 가장 좋은 성과를 보이고 있습니다.`);
  }
  const avgReturn = weights.reduce((s, h) => s + h.pnlPct * h.w / 100, 0);
  const opinion = avgReturn > 5 ? '전반적으로 긍정적인 수익률을 기록 중입니다.'
    : avgReturn > 0 ? '소폭 플러스 수익률을 유지하고 있습니다.'
    : '현재 전체 포트폴리오가 손실 구간입니다.';
  lines.push(`<strong>💡 종합 의견</strong>: ${opinion}`);
  return lines.map(l => `<p style="margin:0 0 8px;line-height:1.6">${l}</p>`).join('');
}

export default function MyReportPage() {
  const [view, setView] = useState('list');
  const [reports, setReports] = useState([]);
  const [prices, setPrices] = useState({});
  const [pricesLoaded, setPricesLoaded] = useState(false);
  const [newHoldings, setNewHoldings] = useState([]);
  const [newTitle, setNewTitle] = useState('');
  const [addAsset, setAddAsset] = useState('005930');
  const [addQty, setAddQty] = useState('');
  const [addPrice, setAddPrice] = useState('');
  const [generating, setGenerating] = useState(false);
  const [currentReport, setCurrentReport] = useState(null);

  useEffect(() => {
    setReports(loadReports());
    loadPrices();
  }, []);

  async function loadPrices() {
    try {
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const [pr, fr] = await Promise.all([
        fetch('/api/v1/prices/latest', { headers }),
        fetch('/api/v1/exchange-rates/latest', { headers }),
      ]);
      const next = {};
      if (pr.ok) { const d = await pr.json(); d.forEach(({ ticker, close }) => { next[ticker] = close; }); }
      if (fr.ok) { const d = await fr.json(); d.forEach(({ pair, rate }) => { next[pair] = rate; }); }
      setPrices(next);
    } catch { /* silent */ }
    setPricesLoaded(true);
  }

  function getPrice(id) { return prices[id] ?? ASSET_INFO[id]?.price ?? 0; }

  function addHolding() {
    const qty = parseFloat(addQty);
    const priceInput = parseFloat(addPrice);
    if (!qty || qty <= 0) { alert('수량을 입력해주세요.'); return; }
    const avg = priceInput > 0 ? priceInput : getPrice(addAsset);
    const existing = newHoldings.find(h => h.id === addAsset);
    if (existing) {
      const totalQty = existing.qty + qty;
      existing.avgPrice = (existing.qty * existing.avgPrice + qty * avg) / totalQty;
      existing.qty = totalQty;
      setNewHoldings([...newHoldings]);
    } else {
      setNewHoldings([...newHoldings, { id: addAsset, qty, avgPrice: avg }]);
    }
    setAddQty(''); setAddPrice('');
  }

  function removeHolding(id) { setNewHoldings(newHoldings.filter(h => h.id !== id)); }

  function generateReport() {
    if (newHoldings.length === 0) { alert('자산을 1개 이상 추가해주세요.'); return; }
    setGenerating(true);
    setTimeout(() => {
      const now = new Date();
      const dateStr = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')}`;
      const report = { id: 'r' + Date.now(), title: newTitle.trim() || '내 포트폴리오', date: dateStr, holdings: newHoldings.map(h => ({ ...h })) };
      const next = [report, ...reports];
      setReports(next);
      saveReports(next);
      setGenerating(false);
      openDetail(report);
    }, 1200);
  }

  function openDetail(report) {
    setCurrentReport(report);
    setView('detail');
  }

  function deleteReport(id) {
    if (!confirm('리포트를 삭제하시겠습니까?')) return;
    const next = reports.filter(r => r.id !== id);
    setReports(next);
    saveReports(next);
  }

  function deleteCurrentReport() {
    if (!confirm('이 리포트를 삭제하시겠습니까?')) return;
    const next = reports.filter(r => r.id !== currentReport.id);
    setReports(next);
    saveReports(next);
    setView('list');
  }

  if (!pricesLoaded) return <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>불러오는 중...</div>;

  if (view === 'list') {
    return (
      <>
        <div className="sec-header">
          <div>
            <div className="sec-title">내 리포트</div>
            <div className="sec-sub">포트폴리오를 입력하면 AI가 분석 리포트를 생성해드려요</div>
          </div>
          <button className="btn btn-primary" onClick={() => { setNewHoldings([]); setNewTitle(''); setView('new'); }}>＋ 새 리포트 작성</button>
        </div>
        <div className="other-card">
          {reports.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>📋 작성된 리포트가 없습니다.<br />새 리포트 작성을 눌러 포트폴리오를 분석해보세요.</div>
          ) : reports.map(r => {
            const { totalVal, totalCost } = calcTotals(r.holdings, prices);
            const pnl = totalVal - totalCost;
            const pnlPct = totalCost > 0 ? pnl / totalCost * 100 : 0;
            const sign = pnl >= 0 ? '+' : '';
            const pnlColor = pnl >= 0 ? '#16a34a' : '#dc2626';
            const names = r.holdings.slice(0, 3).map(h => ASSET_INFO[h.id]?.name || h.id).join(' · ');
            return (
              <div key={r.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 14, padding: '14px 0', borderBottom: '1px solid #f1f5f9' }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: '#eff6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>📊</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>{r.title}</div>
                  <div style={{ fontSize: 11, color: '#64748b', marginBottom: 5 }}>{r.date} · {r.holdings.length}개 자산 · 총 {fmtCompact(totalVal)}</div>
                  <div style={{ fontSize: 12, color: '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {names}{r.holdings.length > 3 ? ` 외 ${r.holdings.length - 3}개` : ''} &nbsp;|&nbsp;
                    <span style={{ color: pnlColor, fontWeight: 700 }}>{sign}{fmt(pnl)}원 ({sign}{pnlPct.toFixed(1)}%)</span>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => openDetail(r)}>보기</button>
                  <button className="btn btn-danger" style={{ fontSize: 12 }} onClick={() => deleteReport(r.id)}>삭제</button>
                </div>
              </div>
            );
          })}
        </div>
      </>
    );
  }

  if (view === 'new') {
    const totalVal = newHoldings.reduce((s, h) => s + h.qty * getPrice(h.id), 0);
    return (
      <>
        <div className="sec-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="back-btn" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, color: '#64748b', cursor: 'pointer', background: '#f8fafc', border: '1px solid #e2e8f0' }} onClick={() => setView('list')}>← 목록</div>
            <div className="sec-title">새 리포트 작성</div>
          </div>
        </div>
        <div className="other-card">
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>리포트 제목</div>
            <input className="form-input" value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="예: 내 메인 포트폴리오" maxLength={40} />
          </div>

          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>보유 자산 추가</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="fsel" value={addAsset} onChange={e => setAddAsset(e.target.value)} style={{ flex: 2, minWidth: 140 }}>
                {Object.entries(ASSET_INFO).map(([id, info]) => <option key={id} value={id}>{info.name} ({id})</option>)}
              </select>
              <input className="form-input" type="number" min="0" placeholder="수량" value={addQty} onChange={e => setAddQty(e.target.value)} style={{ flex: 1, minWidth: 80, width: 80 }} />
              <input className="form-input" type="number" min="0" placeholder="평균 매입가" value={addPrice} onChange={e => setAddPrice(e.target.value)} style={{ flex: 1, minWidth: 120, width: 120 }} />
              <button className="btn btn-primary" onClick={addHolding} style={{ whiteSpace: 'nowrap' }}>＋ 추가</button>
            </div>
            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 5 }}>평균 매입가 미입력 시 현재가로 자동 설정됩니다</div>
          </div>

          {newHoldings.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#94a3b8', fontSize: 12 }}>자산을 추가하면 여기에 표시됩니다</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  {['종목 / 자산', '수량', '평균 매입가', '현재가', '평가액', '예상 비중', ''].map(h => (
                    <th key={h} style={{ textAlign: h ? 'right' : 'left', padding: '6px 8px', fontSize: 10, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', borderBottom: '1px solid #f1f5f9' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {newHoldings.map(h => {
                  const info = ASSET_INFO[h.id] || {};
                  const cur = getPrice(h.id);
                  const curVal = h.qty * cur;
                  const weight = totalVal > 0 ? curVal / totalVal * 100 : 0;
                  const pnl = curVal - h.qty * h.avgPrice;
                  return (
                    <tr key={h.id}>
                      <td style={{ padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>
                        <span style={{ width: 9, height: 9, borderRadius: '50%', display: 'inline-block', marginRight: 5, background: info.color || '#94a3b8' }} />
                        <strong>{info.name || h.id}</strong>
                      </td>
                      <td style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.qty)}{info.unit || ''}</td>
                      <td style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.avgPrice)}원</td>
                      <td style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(cur)}원</td>
                      <td style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(curVal)}원</td>
                      <td style={{ textAlign: 'right', padding: '8px 8px', borderBottom: '1px solid #f8fafc', color: pnl >= 0 ? '#16a34a' : '#dc2626' }}>{weight.toFixed(1)}%</td>
                      <td style={{ padding: '8px 8px', borderBottom: '1px solid #f8fafc' }}>
                        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cbd5e1', fontSize: 14 }} onClick={() => removeHolding(h.id)}>×</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: 14, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn btn-ghost" onClick={() => setView('list')}>취소</button>
            <button className="btn btn-primary" onClick={generateReport} disabled={generating} style={{ minWidth: 140 }}>
              {generating ? <span><span className="spin">⟳</span> 분석 중...</span> : '▶ AI 리포트 생성'}
            </button>
          </div>
        </div>
      </>
    );
  }

  if (view === 'detail' && currentReport) {
    const { totalVal, totalCost, sorted } = calcTotals(currentReport.holdings, prices);
    const totalPnl = totalVal - totalCost;
    const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
    const pnlColor = totalPnl >= 0 ? '#16a34a' : '#dc2626';
    const aiHtml = renderAIAnalysis(currentReport.title, sorted, totalVal);

    return (
      <>
        <div className="sec-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, color: '#64748b', cursor: 'pointer', background: '#f8fafc', border: '1px solid #e2e8f0' }} onClick={() => setView('list')}>← 목록</div>
            <div>
              <div className="sec-title">{currentReport.title}</div>
              <div className="sec-sub">{currentReport.date} 기준</div>
            </div>
          </div>
          <button className="btn btn-danger" style={{ fontSize: 12 }} onClick={deleteCurrentReport}>삭제</button>
        </div>

        <div className="other-card mb">
          <div className="other-card-title">포트폴리오 현황</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 20, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <DonutSvg sorted={sorted} totalVal={totalVal} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 11, width: '100%' }}>
                {sorted.map(h => {
                  const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                  return (
                    <div key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 9, height: 9, borderRadius: '50%', background: h.info.color || '#94a3b8', display: 'inline-block', flexShrink: 0 }} />
                      <span style={{ color: '#475569' }}>{h.info.name || h.id}</span>
                      <span style={{ marginLeft: 'auto', fontWeight: 700, color: '#374151' }}>{w.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    {['종목 / 자산', '수량', '평균 매입가', '현재가', '평가액', '손익', '비중'].map((h, i) => (
                      <th key={h} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '6px 8px', fontSize: 10, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', borderBottom: '1px solid #f1f5f9' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(h => {
                    const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                    const pnl = h.curVal - h.cost;
                    const pnlPct = h.cost > 0 ? pnl / h.cost * 100 : 0;
                    const pc = pnl >= 0 ? '#16a34a' : '#dc2626';
                    return (
                      <tr key={h.id}>
                        <td style={{ padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>
                          <span style={{ width: 9, height: 9, borderRadius: '50%', display: 'inline-block', marginRight: 5, background: h.info.color || '#94a3b8' }} />
                          <strong>{h.info.name || h.id}</strong>
                        </td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.qty)}{h.info.unit || ''}</td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.avgPrice)}원</td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.info.price || 0)}원</td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.curVal)}원</td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc', color: pc, fontWeight: 600 }}>
                          {pnl >= 0 ? '+' : ''}{fmt(pnl)}원<br />
                          <span style={{ fontSize: 10 }}>({pnl >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)</span>
                        </td>
                        <td style={{ textAlign: 'right', padding: '9px 8px', borderBottom: '1px solid #f8fafc' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                            <div style={{ background: '#f1f5f9', borderRadius: 4, height: 5, flex: 1, minWidth: 50 }}>
                              <div style={{ width: `${Math.min(w, 100)}%`, height: 5, borderRadius: 4, background: h.info.color || '#94a3b8' }} />
                            </div>
                            <span style={{ whiteSpace: 'nowrap', fontWeight: 700 }}>{w.toFixed(1)}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr style={{ background: '#f8fafc', fontWeight: 700, borderTop: '2px solid #e2e8f0' }}>
                    <td colSpan={4} style={{ padding: '9px 8px' }}>합계</td>
                    <td style={{ textAlign: 'right', padding: '9px 8px' }}>{fmt(totalVal)}원</td>
                    <td style={{ textAlign: 'right', padding: '9px 8px', color: pnlColor }}>
                      {totalPnl >= 0 ? '+' : ''}{fmt(totalPnl)}원<br />
                      <span style={{ fontSize: 10 }}>({totalPnl >= 0 ? '+' : ''}{totalPnlPct.toFixed(1)}%)</span>
                    </td>
                    <td style={{ textAlign: 'right', padding: '9px 8px' }}>100%</td>
                  </tr>
                </tfoot>
              </table>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
                {[
                  { label: '총 매입 원가', val: fmtCompact(totalCost) },
                  { label: '총 평가액', val: fmtCompact(totalVal) },
                  { label: '총 손익', val: (totalPnl >= 0 ? '+' : '') + fmtCompact(Math.abs(totalPnl)), color: pnlColor },
                  { label: '수익률', val: (totalPnlPct >= 0 ? '+' : '') + totalPnlPct.toFixed(2) + '%', color: pnlColor },
                ].map(({ label, val, color }) => (
                  <div key={label} style={{ background: '#f8fafc', borderRadius: 8, padding: '8px 10px' }}>
                    <div style={{ fontSize: 10, color: '#94a3b8', marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: color || 'inherit' }}>{val}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="other-card">
          <div className="other-card-title">AI 포트폴리오 분석</div>
          <div className="ai-box">
            <div className="ai-header">
              <span className="ai-badge">AI 분석</span>
              <span className="ai-title">{currentReport.title} 분석</span>
            </div>
            <div className="ai-text" dangerouslySetInnerHTML={{ __html: aiHtml }} />
            <div className="ai-sources">
              <span className="ai-src-tag">📊 {sorted.length}개 자산</span>
              <span className="ai-src-tag">🤖 AI 분석</span>
              <span className="ai-src-tag">📅 {new Date().toLocaleDateString('ko-KR')} 기준</span>
            </div>
          </div>
        </div>
      </>
    );
  }

  return null;
}
