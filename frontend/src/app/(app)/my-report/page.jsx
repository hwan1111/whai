'use client';
import { useState, useEffect } from 'react';
import { getToken } from '@/lib/auth';

const ASSET_INFO = {
  '005930': { name: '삼성전자',      color: '#dc2626', sector: '반도체', unit: '주' },
  '000660': { name: 'SK하이닉스',   color: '#16a34a', sector: '반도체', unit: '주' },
  '005380': { name: '현대차',        color: '#f59e0b', sector: '자동차', unit: '주' },
  '000270': { name: '기아',          color: '#8b5cf6', sector: '자동차', unit: '주' },
  '079550': { name: 'LIG디펜스',    color: '#06b6d4', sector: '방산',   unit: '주' },
  '012450': { name: '한화에어로',   color: '#f97316', sector: '방산',   unit: '주' },
  '105560': { name: 'KB금융',        color: '#6366f1', sector: '금융',   unit: '주' },
  '055550': { name: '신한지주',      color: '#0d9488', sector: '금융',   unit: '주' },
  '051910': { name: 'LG화학',        color: '#ec4899', sector: '화학',   unit: '주' },
  '096770': { name: 'SK이노베이션', color: '#84cc16', sector: '화학',   unit: '주' },
  'KRW/USD': { name: 'USD 달러',    color: '#78716c', sector: '외화', unit: '달러' },
  'KRW/JPY': { name: 'JPY 엔',      color: '#a16207', sector: '외화', unit: '엔' },
  'KRW/EUR': { name: 'EUR 유로',    color: '#9333ea', sector: '외화', unit: '유로' },
  'KRW/CNY': { name: 'CNY 위안',    color: '#0891b2', sector: '외화', unit: '위안' },
  'KRW/CHF': { name: 'CHF 프랑',    color: '#0f766e', sector: '외화', unit: '프랑' },
  'KRW/GBP': { name: 'GBP 파운드', color: '#b91c1c', sector: '외화', unit: '파운드' },
};

const STOCK_IDS = ['005930','000660','005380','000270','079550','012450','105560','055550','051910','096770'];
const FX_IDS    = ['KRW/USD','KRW/JPY','KRW/EUR','KRW/CNY','KRW/CHF','KRW/GBP'];

const LOGO_MAP = {
  '005930': 'samsung.svg', '000660': 'skhynix.svg',
  '005380': 'hyundai.png', '000270': 'kia.png',
  '079550': 'lignex1.svg', '012450': 'hanwha.svg',
  '105560': 'kb.svg',      '055550': 'shinhan.svg',
  '051910': 'lgchem.svg',  '096770': 'skinnovation.svg',
};
const FLAG_MAP = {
  'KRW/USD': 'us', 'KRW/JPY': 'jp', 'KRW/EUR': 'eu',
  'KRW/CNY': 'cn', 'KRW/CHF': 'ch', 'KRW/GBP': 'gb',
};
const getLogo = id => LOGO_MAP[id] ? `/assets/logos/${LOGO_MAP[id]}` : null;
const getFlag = id => FLAG_MAP[id] ? `/assets/flags/${FLAG_MAP[id]}.png` : null;

const MAX_SNAPSHOTS = 10;
const STORE_KEY = 'whai_snapshots_v1';

const fmt = n => Math.round(n).toLocaleString('ko-KR');
function fmtCompact(n) {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}억원`;
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${fmt(n)}원`;
}
function fmtDatetime(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}  ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function loadSnapshots() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || []; }
  catch { return []; }
}
function saveSnapshots(list) { localStorage.setItem(STORE_KEY, JSON.stringify(list)); }

function calcTotals(holdings, prices) {
  const sorted = holdings.map(h => {
    const info = ASSET_INFO[h.id] || {};
    const curPrice = prices[h.id] ?? h.avgPrice;
    const curVal = h.qty * curPrice;
    const cost = h.qty * h.avgPrice;
    return { ...h, info, curPrice, curVal, cost };
  }).sort((a, b) => b.curVal - a.curVal);
  const totalVal = sorted.reduce((s, h) => s + h.curVal, 0);
  const totalCost = sorted.reduce((s, h) => s + h.cost, 0);
  return { totalVal, totalCost, sorted };
}

function DonutChart({ sorted, totalVal, size = 180 }) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.36, sw = size * 0.155;
  const C = 2 * Math.PI * r;
  const gap = 2;
  let paths = '', cum = 0;
  sorted.forEach(h => {
    if (h.curVal <= 0) return;
    const len = (h.curVal / totalVal) * C;
    const segLen = Math.max(len - gap, 0.1);
    paths += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${h.info.color || '#94a3b8'}" stroke-width="${sw}" stroke-dasharray="${segLen.toFixed(2)} ${C.toFixed(2)}" stroke-dashoffset="${(-cum).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    cum += len;
  });
  const fs1 = Math.round(size * 0.067), fs2 = Math.round(size * 0.078);
  return (
    <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size, flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
      <g dangerouslySetInnerHTML={{ __html: paths }} />
      <text x={cx} y={cy - size * 0.055} textAnchor="middle" fontSize={fs1} fill="#94a3b8">총 평가액</text>
      <text x={cx} y={cy + size * 0.075} textAnchor="middle" fontSize={fs2} fontWeight="800" fill="#1e293b">{fmtCompact(totalVal)}</text>
    </svg>
  );
}

function buildAiHtml(sorted, totalVal, totalCost) {
  const weights = sorted.map(h => ({
    name: h.info.name || h.id,
    sector: h.info.sector || '기타',
    w: totalVal > 0 ? h.curVal / totalVal * 100 : 0,
    pnlPct: h.cost > 0 ? (h.curVal - h.cost) / h.cost * 100 : 0,
    curVal: h.curVal,
    cost: h.cost,
  }));
  const top = weights[0];
  const avgReturn = totalCost > 0 ? (totalVal - totalCost) / totalCost * 100 : 0;
  const sectors = {};
  weights.forEach(h => { sectors[h.sector] = (sectors[h.sector] || 0) + h.w; });
  const sectorList = Object.entries(sectors).sort((a, b) => b[1] - a[1]);
  const losers = weights.filter(h => h.pnlPct < 0).sort((a, b) => a.pnlPct - b.pnlPct);
  const gainers = weights.filter(h => h.pnlPct > 0).sort((a, b) => b.pnlPct - a.pnlPct);
  const lines = [];

  // 1. 집중도 분석
  if (top.w >= 50)
    lines.push(`<strong>⚠️ 집중도 경고</strong>: <strong>${top.name}</strong> 단일 종목 비중이 <strong>${top.w.toFixed(1)}%</strong>로 절반을 초과합니다. 해당 종목의 변동성이 포트폴리오 전체 성과를 크게 좌우할 수 있어 비중 축소 또는 분산 매수를 권장합니다.`);
  else if (top.w >= 35)
    lines.push(`<strong>📊 비중 점검 권장</strong>: <strong>${top.name}</strong> 비중이 <strong>${top.w.toFixed(1)}%</strong>로 다소 높습니다. 리스크 관리 차원에서 30% 이하로 조절하는 것을 고려해 보세요.`);
  else
    lines.push(`<strong>✅ 분산 투자 양호</strong>: 최고 비중 종목인 <strong>${top.name}</strong>이 <strong>${top.w.toFixed(1)}%</strong>로 집중 위험이 낮습니다. 현재 비중 분산 수준은 안정적입니다.`);

  // 2. 섹터 분석
  if (sectorList.length === 1)
    lines.push(`<strong>🔍 섹터 단일 집중</strong>: 모든 자산이 <strong>${sectorList[0][0]}</strong> 섹터에 집중되어 있습니다. 섹터 리스크에 취약하므로 다른 섹터 편입을 검토하세요.`);
  else if (sectorList[0][1] > 70)
    lines.push(`<strong>🔍 섹터 쏠림 주의</strong>: <strong>${sectorList[0][0]}</strong> 섹터 비중이 <strong>${sectorList[0][1].toFixed(0)}%</strong>로 매우 높습니다. ${sectorList.slice(1, 3).map(([s]) => s).join(', ')} 등 타 섹터 비중을 늘려 균형을 맞추는 것이 좋습니다.`);
  else
    lines.push(`<strong>📂 섹터 구성</strong>: ${sectorList.map(([s, w]) => `<strong>${s}</strong> ${w.toFixed(0)}%`).join(', ')}으로 구성되어 있습니다.`);

  // 3. 수익/손실 종목
  if (gainers.length > 0 && losers.length > 0) {
    lines.push(`<strong>📈 성과 상위</strong>: <strong>${gainers[0].name}</strong>이 <span style="color:#16a34a">+${gainers[0].pnlPct.toFixed(1)}%</span>로 가장 높은 수익을 기록 중입니다.`);
    lines.push(`<strong>📉 손실 종목</strong>: <strong>${losers[0].name}</strong>이 <span style="color:#dc2626">${losers[0].pnlPct.toFixed(1)}%</span> 손실 중입니다. 손절 기준 또는 추가 매수 여부를 점검해 보세요.`);
  } else if (gainers.length > 0) {
    lines.push(`<strong>📈 전 종목 수익</strong>: <strong>${gainers[0].name}</strong>이 <span style="color:#16a34a">+${gainers[0].pnlPct.toFixed(1)}%</span>로 최고 성과를 기록 중입니다.`);
  } else if (losers.length > 0) {
    lines.push(`<strong>📉 전 종목 손실</strong>: <strong>${losers[0].name}</strong>이 <span style="color:#dc2626">${losers[0].pnlPct.toFixed(1)}%</span>로 가장 큰 손실입니다. 시장 상황과 보유 근거를 재검토하세요.`);
  }

  // 4. 종합 의견
  if (avgReturn > 15)
    lines.push(`<strong>💡 종합 의견</strong>: 포트폴리오 전체 수익률이 <span style="color:#16a34a">+${avgReturn.toFixed(1)}%</span>로 우수한 성과를 기록 중입니다. 수익 실현 시점을 고려하거나 이익을 재투자하는 전략을 검토해 보세요.`);
  else if (avgReturn > 0)
    lines.push(`<strong>💡 종합 의견</strong>: <span style="color:#16a34a">+${avgReturn.toFixed(1)}%</span>의 플러스 수익률을 유지하고 있습니다. 분산 투자 원칙을 지키며 꾸준히 운용하고 있는 것으로 보입니다.`);
  else
    lines.push(`<strong>💡 종합 의견</strong>: 현재 <span style="color:#dc2626">${avgReturn.toFixed(1)}%</span>의 손실 구간에 있습니다. 손실 원인을 분석하고 포트폴리오 재구성 여부를 검토해 보세요.`);

  return lines.map(l => `<p style="margin:0 0 10px;line-height:1.75;font-size:12.5px;color:#312e81">${l}</p>`).join('');
}

function SnapshotCard({ snap, prices, onDelete }) {
  const { totalVal, totalCost, sorted } = calcTotals(snap.holdings, prices);
  const totalPnl = totalVal - totalCost;
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
  const pnlColor = totalPnl >= 0 ? '#16a34a' : '#dc2626';
  const aiHtml = buildAiHtml(sorted, totalVal, totalCost);

  return (
    <div className="snapshot-card">
      <div className="snapshot-card-header">
        <span className="snapshot-datetime">{fmtDatetime(snap.datetime)}</span>
        <button className="snapshot-delete-btn" onClick={() => onDelete(snap.id)} title="삭제">✕</button>
      </div>

      <div className="snapshot-body">
        {/* 1열: AI 분석 */}
        <div className="snapshot-ai">
          <div className="snapshot-ai-header">
            <span className="ai-badge" style={{ fontSize: 9 }}>AI 분석</span>
            <span style={{ fontSize: 11, color: '#6d28d9', fontWeight: 600 }}>포트폴리오 분석</span>
          </div>
          <div dangerouslySetInnerHTML={{ __html: aiHtml }} />
        </div>

        {/* 2열: 도넛 차트만 */}
        <div className="snapshot-chart-center">
          <DonutChart sorted={sorted} totalVal={totalVal} size={400} />
        </div>

        {/* 3열: 레전드 + 요약 */}
        <div className="snapshot-right">
          <div className="snapshot-legend">
            {sorted.map(h => {
              const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
              const pnl = h.curVal - h.cost;
              const pnlPct = h.cost > 0 ? pnl / h.cost * 100 : 0;
              const pc = pnl >= 0 ? '#16a34a' : '#dc2626';
              return (
                <div key={h.id} className="snapshot-legend-row">
                  <span className="snapshot-legend-dot" style={{ background: h.info.color || '#94a3b8' }} />
                  <span className="snapshot-legend-name">{h.info.name || h.id}</span>
                  <span className="snapshot-legend-pct">{w.toFixed(1)}%</span>
                  <span className="snapshot-legend-val">{fmtCompact(h.curVal)}</span>
                  <span className="snapshot-legend-pnl" style={{ color: pc }}>
                    {pnl >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>

          <div className="snapshot-summary">
            {[
              { label: '총 매입 원가', val: fmtCompact(totalCost) },
              { label: '총 평가액',   val: fmtCompact(totalVal) },
              { label: '총 손익',     val: (totalPnl >= 0 ? '+' : '') + fmtCompact(Math.abs(totalPnl)), color: pnlColor },
              { label: '수익률',      val: (totalPnlPct >= 0 ? '+' : '') + totalPnlPct.toFixed(2) + '%', color: pnlColor },
            ].map(({ label, val, color }) => (
              <div key={label} className="snapshot-summary-item">
                <div className="snapshot-summary-label">{label}</div>
                <div className="snapshot-summary-val" style={{ color: color || 'inherit' }}>{val}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MyReportPage() {
  const [snapshots, setSnapshots] = useState([]);
  const [prices, setPrices] = useState({});
  const [pricesLoaded, setPricesLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [holdings, setHoldings] = useState([]);
  const [addAsset, setAddAsset] = useState('005930');
  const [addQty, setAddQty] = useState('1');
  const [addPrice, setAddPrice] = useState('');
  const [generating, setGenerating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    setSnapshots(loadSnapshots());
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
      if (next['005930']) setAddPrice(String(next['005930']));
    } catch { /* silent */ }
    setPricesLoaded(true);
  }

  function getPrice(id) { return prices[id] ?? ASSET_INFO[id]?.avgPrice ?? 0; }

  function addHolding() {
    const qty = parseFloat(addQty);
    if (!qty || qty <= 0) { alert('수량을 입력해주세요.'); return; }
    const manualPrice = parseFloat(addPrice);
    const fetchedPrice = getPrice(addAsset);
    if (!(manualPrice > 0) && !(fetchedPrice > 0)) {
      alert('종가 데이터를 불러오지 못했습니다. 평균 매입가를 직접 입력해주세요.');
      return;
    }
    const avg = manualPrice > 0 ? manualPrice : fetchedPrice;
    const existing = holdings.find(h => h.id === addAsset);
    if (existing) {
      const totalQty = existing.qty + qty;
      existing.avgPrice = (existing.qty * existing.avgPrice + qty * avg) / totalQty;
      existing.qty = totalQty;
      setHoldings([...holdings]);
    } else {
      setHoldings([...holdings, { id: addAsset, qty, avgPrice: avg }]);
    }
    setAddQty('1'); setAddPrice(prices[addAsset] ? String(prices[addAsset]) : '');
  }

  function removeHolding(id) { setHoldings(holdings.filter(h => h.id !== id)); }

  function saveSnapshot() {
    if (holdings.length === 0) { alert('자산을 1개 이상 추가해주세요.'); return; }
    setGenerating(true);
    setTimeout(() => {
      const snap = { id: 'snap_' + Date.now(), datetime: new Date().toISOString(), holdings: holdings.map(h => ({ ...h })) };
      const next = [snap, ...snapshots].slice(0, MAX_SNAPSHOTS);
      setSnapshots(next);
      saveSnapshots(next);
      setHoldings([]);
      setAddQty('1'); setAddPrice(prices[addAsset] ? String(prices[addAsset]) : '');
      setFormOpen(false);
      setGenerating(false);
    }, 800);
  }

  function deleteSnapshot(id) { setDeleteTarget(id); }

  function confirmDelete() {
    const next = snapshots.filter(s => s.id !== deleteTarget);
    setSnapshots(next);
    saveSnapshots(next);
    setDeleteTarget(null);
  }

  if (!pricesLoaded) return <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>불러오는 중...</div>;

  const totalCount = snapshots.length;
  const formTotalVal = holdings.reduce((s, h) => s + h.qty * getPrice(h.id), 0);

  return (
    <>
      <div className="sec-header">
        <div>
          <div className="sec-title">마이 리포트</div>
          <div className="sec-sub">포트폴리오 스냅샷 · 최대 {MAX_SNAPSHOTS}개 보관 {totalCount > 0 ? `· 현재 ${totalCount}개` : ''}</div>
        </div>
        <button className="btn btn-primary" onClick={() => { setFormOpen(o => !o); setHoldings([]); }}>
          {formOpen ? '✕ 취소' : '＋ 새 스냅샷 기록'}
        </button>
      </div>

      {/* 새 스냅샷 입력 폼 */}
      {formOpen && (
        <div className="other-card" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 }}>보유 자산 선택</div>

          {/* 주식 카드 그리드 */}
          <div style={{ fontSize: 9, fontWeight: 700, color: '#94a3b8', letterSpacing: 0.5, marginBottom: 5 }}>주식</div>
          <div className="asset-pick-grid" style={{ marginBottom: 10 }}>
            {STOCK_IDS.map(id => {
              const info = ASSET_INFO[id];
              const logo = getLogo(id);
              const sel = addAsset === id;
              return (
                <div key={id} className={`asset-pick-card${sel ? ' selected' : ''}`} onClick={() => { setAddAsset(id); setAddPrice(prices[id] ? String(prices[id]) : ''); }}>
                  <div className="asset-pick-logo">
                    {logo && <img src={logo} alt={info.name} />}
                  </div>
                  <div className="asset-pick-name">{info.name}</div>
                </div>
              );
            })}
          </div>

          {/* 외화 카드 그리드 */}
          <div style={{ fontSize: 9, fontWeight: 700, color: '#94a3b8', letterSpacing: 0.5, marginBottom: 5 }}>외화</div>
          <div className="asset-pick-grid asset-pick-fx" style={{ marginBottom: 14 }}>
            {FX_IDS.map(id => {
              const info = ASSET_INFO[id];
              const flag = getFlag(id);
              const sel = addAsset === id;
              const [code, ...rest] = info.name.split(' ');
              return (
                <div key={id} className={`asset-pick-card${sel ? ' selected' : ''}`} onClick={() => { setAddAsset(id); setAddPrice(prices[id] ? String(prices[id]) : ''); }}>
                  {flag && <img className="asset-pick-flag" src={flag} alt={info.name} />}
                  <div className="asset-pick-name">{code}</div>
                  <div className="asset-pick-label">{rest.join(' ')}</div>
                </div>
              );
            })}
          </div>

          {/* 수량 / 가격 입력 */}
          <div className="add-holding-row">
            {/* 선택된 자산 뱃지 */}
            <div className="add-holding-asset">
              {getLogo(addAsset)
                ? <div className="asset-pick-logo" style={{ width: 32, height: 32, borderRadius: 8 }}><img src={getLogo(addAsset)} alt="" /></div>
                : getFlag(addAsset)
                  ? <img className="asset-pick-flag" src={getFlag(addAsset)} alt="" style={{ width: 30, height: 20 }} />
                  : null
              }
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#1e293b' }}>{ASSET_INFO[addAsset]?.name}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>{ASSET_INFO[addAsset]?.sector} · {addAsset}</div>
              </div>
            </div>

            <div style={{ width: 1, background: '#f1f5f9', alignSelf: 'stretch' }} />

            {/* 수량 */}
            <div className="add-holding-field">
              <label className="add-holding-label">수량</label>
              <input className="form-input" type="number" min="1" placeholder="1" value={addQty}
                onChange={e => setAddQty(e.target.value)}
                onBlur={e => { const v = parseFloat(e.target.value); setAddQty(String(!v || v < 1 ? 1 : v)); }}
                style={{ width: 100 }} />
            </div>

            {/* 평균 매입가 */}
            <div className="add-holding-field">
              <label className="add-holding-label">평균 매입가 <span style={{ fontWeight: 400, color: '#cbd5e1' }}>(종가 자동 입력 · 수정 가능)</span></label>
              <input className="form-input" type="number" min="0"
                placeholder={prices[addAsset] ? String(prices[addAsset]) : '직접 입력'}
                value={addPrice} onChange={e => setAddPrice(e.target.value)} style={{ width: 220 }} />
            </div>

            <button className="btn btn-primary" style={{ alignSelf: 'flex-end', height: 36 }} onClick={addHolding}>＋ 추가</button>
          </div>

          {holdings.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginBottom: 12 }}>
              <thead>
                <tr>
                  {['종목', '수량', '평균 매입가', '종가', '평가액', '예상 비중', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '5px 8px', fontSize: 10, fontWeight: 700, color: '#94a3b8', borderBottom: '1px solid #f1f5f9' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {holdings.map(h => {
                  const info = ASSET_INFO[h.id] || {};
                  const cur = getPrice(h.id);
                  const curVal = h.qty * cur;
                  const w = formTotalVal > 0 ? curVal / formTotalVal * 100 : 0;
                  return (
                    <tr key={h.id}>
                      <td style={{ padding: '7px 8px', borderBottom: '1px solid #f8fafc', textAlign: 'left' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', display: 'inline-block', marginRight: 5, background: info.color || '#94a3b8' }} />
                        {info.name || h.id}
                      </td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.qty)}{info.unit || ''}</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(h.avgPrice)}원</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(cur)}원</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(curVal)}원</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{w.toFixed(1)}%</td>
                      <td style={{ padding: '7px 8px', borderBottom: '1px solid #f8fafc', textAlign: 'center' }}>
                        <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cbd5e1', fontSize: 15 }} onClick={() => removeHolding(h.id)}>×</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn btn-ghost" onClick={() => { setFormOpen(false); setHoldings([]); }}>취소</button>
            <button className="btn btn-primary" onClick={saveSnapshot} disabled={generating || holdings.length === 0} style={{ minWidth: 140 }}>
              {generating ? '⟳ 분석 중...' : '▶ 스냅샷 저장'}
            </button>
          </div>
        </div>
      )}

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()} style={{ width: 340 }}>
            <div className="modal-title">스냅샷 삭제</div>
            <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.6, marginBottom: 20 }}>
              이 기록을 삭제하면 복구할 수 없습니다.<br />정말 삭제하시겠습니까?
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>취소</button>
              <button className="btn btn-danger" onClick={confirmDelete}>삭제</button>
            </div>
          </div>
        </div>
      )}

      {/* 스냅샷 타임라인 */}
      {snapshots.length === 0 ? (
        <div className="other-card" style={{ textAlign: 'center', padding: '60px 0', color: '#94a3b8', fontSize: 13 }}>
          📋 기록된 스냅샷이 없습니다.<br />
          <span style={{ fontSize: 12, marginTop: 6, display: 'block' }}>위의 버튼을 눌러 포트폴리오를 기록해보세요.</span>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {snapshots.map(snap => (
            <SnapshotCard key={snap.id} snap={snap} prices={prices} onDelete={deleteSnapshot} />
          ))}
          {snapshots.length >= MAX_SNAPSHOTS && (
            <div style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8', padding: '4px 0 8px' }}>
              최대 {MAX_SNAPSHOTS}개 보관 — 새 스냅샷 추가 시 가장 오래된 기록이 자동 삭제됩니다.
            </div>
          )}
        </div>
      )}
    </>
  );
}
