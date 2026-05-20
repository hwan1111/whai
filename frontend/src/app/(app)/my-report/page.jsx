'use client';
import { useState, useEffect, useRef } from 'react';
import { handleUnauthorized, fetchWithAuth } from '@/lib/auth';
import { ASSETS } from '@/lib/data';

const ASSET_INFO = {
  '005930': { name: '삼성전자',      color: ASSETS['005930'].color,  sector: '반도체', unit: '주' },
  '000660': { name: 'SK하이닉스',   color: ASSETS['000660'].color,  sector: '반도체', unit: '주' },
  '005380': { name: '현대차',        color: ASSETS['005380'].color,  sector: '자동차', unit: '주' },
  '000270': { name: '기아',          color: ASSETS['000270'].color,  sector: '자동차', unit: '주' },
  '079550': { name: 'LIG디펜스',    color: ASSETS['079550'].color,  sector: '방산',   unit: '주' },
  '012450': { name: '한화에어로',   color: ASSETS['012450'].color,  sector: '방산',   unit: '주' },
  '105560': { name: 'KB금융',        color: ASSETS['105560'].color,  sector: '금융',   unit: '주' },
  '055550': { name: '신한지주',      color: ASSETS['055550'].color,  sector: '금융',   unit: '주' },
  '051910': { name: 'LG화학',        color: ASSETS['051910'].color,  sector: '화학',   unit: '주' },
  '096770': { name: 'SK이노베이션', color: ASSETS['096770'].color,  sector: '화학',   unit: '주' },
  'KRW/USD': { name: 'USD 달러',    color: ASSETS['KRW/USD'].color, sector: '외화', unit: '달러' },
  'KRW/JPY': { name: 'JPY 엔',      color: ASSETS['KRW/JPY'].color, sector: '외화', unit: '엔' },
  'KRW/EUR': { name: 'EUR 유로',    color: ASSETS['KRW/EUR'].color, sector: '외화', unit: '유로' },
  'KRW/CNY': { name: 'CNY 위안',    color: ASSETS['KRW/CNY'].color, sector: '외화', unit: '위안' },
  'KRW/CHF': { name: 'CHF 프랑',    color: ASSETS['KRW/CHF'].color, sector: '외화', unit: '프랑' },
  'KRW/GBP': { name: 'GBP 파운드', color: ASSETS['KRW/GBP'].color, sector: '외화', unit: '파운드' },
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

const fmt = n => Math.round(n).toLocaleString('ko-KR');
function fmtCompact(n) {
  return `${Math.round(n).toLocaleString('ko-KR')}원`;
}
function fmtShort(n) {
  if (n >= 1e12) return `${(n / 1e12).toFixed(1)}조원`;
  if (n >= 1e8)  return `${(n / 1e8).toFixed(1)}억원`;
  if (n >= 1e4)  return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${Math.round(n).toLocaleString('ko-KR')}원`;
}
function fmtDatetime(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}  ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function fetchSnapshots() {
  try {
    const res = await fetchWithAuth('/api/v1/report/snapshots');
    if (!res.ok) return [];
    const data = await res.json();
    return data.snapshots || [];
  } catch { return []; }
}

async function postSnapshot(snap) {
  const res = await fetchWithAuth('/api/v1/report/snapshots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snap),
  });
  if (res.status === 401) { handleUnauthorized(); return; }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`snapshot POST failed: ${res.status} ${body}`);
  }
}

async function deleteSnapshotApi(id) {
  try {
    await fetchWithAuth(`/api/v1/report/snapshots/${id}`, { method: 'DELETE' });
  } catch { /* silent */ }
}

function calcTotals(holdings, prices) {
  const sorted = holdings.map(h => {
    const info = ASSET_INFO[h.id] || {};
    const curPrice = h.snapshotPrice ?? prices[h.id] ?? h.avgPrice;
    const curVal = h.qty * curPrice;
    const cost = h.qty * h.avgPrice;
    return { ...h, info, curPrice, curVal, cost };
  }).sort((a, b) => b.curVal - a.curVal);
  const totalVal = sorted.reduce((s, h) => s + h.curVal, 0);
  const totalCost = sorted.reduce((s, h) => s + h.cost, 0);
  return { totalVal, totalCost, sorted };
}

function DonutChart({ sorted, totalVal, size = 180, onSegmentClick }) {
  const [tooltip, setTooltip] = useState(null);
  const wrapRef = useRef(null);

  const cx = size / 2, cy = size / 2;
  const r = size * 0.36, sw = size * 0.155;
  const gapAngle = 1.5 / r;

  let cumAngle = 0;
  const segments = sorted
    .filter(h => h.curVal > 0)
    .map(h => {
      const angle = (h.curVal / totalVal) * 2 * Math.PI;
      const half = angle > gapAngle ? gapAngle / 2 : 0;
      const seg = { h, startAngle: cumAngle + half, endAngle: cumAngle + angle - half, w: h.curVal / totalVal * 100 };
      cumAngle += angle;
      return seg;
    });

  function arcPath(startAngle, endAngle) {
    const outerR = r + sw / 2, innerR = r - sw / 2;
    const s = startAngle - Math.PI / 2, e = endAngle - Math.PI / 2;
    const large = endAngle - startAngle > Math.PI ? 1 : 0;
    const [ox1, oy1] = [cx + outerR * Math.cos(s), cy + outerR * Math.sin(s)];
    const [ox2, oy2] = [cx + outerR * Math.cos(e), cy + outerR * Math.sin(e)];
    const [ix1, iy1] = [cx + innerR * Math.cos(e), cy + innerR * Math.sin(e)];
    const [ix2, iy2] = [cx + innerR * Math.cos(s), cy + innerR * Math.sin(s)];
    return `M${ox1} ${oy1} A${outerR} ${outerR} 0 ${large} 1 ${ox2} ${oy2} L${ix1} ${iy1} A${innerR} ${innerR} 0 ${large} 0 ${ix2} ${iy2}Z`;
  }

  const fs1 = Math.round(size * 0.067), fs2 = Math.round(size * 0.078);

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size, display: 'block' }}
        onMouseLeave={() => setTooltip(null)}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
        {segments.map((seg, i) => (
          <path
            key={i}
            d={arcPath(seg.startAngle, seg.endAngle)}
            fill={seg.h.info.color || '#94a3b8'}
            style={{ cursor: 'pointer', transition: 'opacity 0.15s' }}
            onMouseEnter={e => {
              const rect = wrapRef.current.getBoundingClientRect();
              const pnl = seg.h.curVal - seg.h.cost;
              const retPct = seg.h.cost > 0 ? pnl / seg.h.cost * 100 : 0;
              setTooltip({ name: seg.h.info.name || seg.h.id, pct: seg.w.toFixed(1), val: fmtCompact(seg.h.curVal), pnl, retPct: retPct.toFixed(2), color: seg.h.info.color || '#94a3b8', x: e.clientX - rect.left, y: e.clientY - rect.top });
            }}
            onMouseMove={e => {
              const rect = wrapRef.current.getBoundingClientRect();
              setTooltip(prev => prev ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top } : null);
            }}
            onClick={() => { setTooltip(null); onSegmentClick && onSegmentClick(seg.h); }}
          />
        ))}
        <text x={cx} y={cy - size * 0.055} textAnchor="middle" fontSize={fs1} fill="#94a3b8" pointerEvents="none">총 평가액</text>
        <text x={cx} y={cy + size * 0.075} textAnchor="middle" fontSize={fs2} fontWeight="800" fill="#1e293b" pointerEvents="none">{fmtShort(totalVal)}</text>
      </svg>
      {tooltip && (
        <div style={{
          position: 'absolute',
          left: tooltip.x + 14,
          top: tooltip.y - 14,
          background: 'white',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: '7px 14px',
          fontSize: 15,
          fontWeight: 600,
          color: '#1e293b',
          boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
          zIndex: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #f1f5f9' }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: tooltip.color, flexShrink: 0 }} />
            <span style={{ fontWeight: 700, fontSize: 17 }}>{tooltip.name}</span>
          </div>
          {[
            { label: '비중',   val: `${tooltip.pct}%`,  color: '#1e293b' },
            { label: '평가액', val: tooltip.val,         color: '#1e293b' },
            { label: '손익',   val: `${tooltip.pnl >= 0 ? '+' : '-'}${fmtCompact(Math.abs(tooltip.pnl))}`, color: parseFloat(tooltip.retPct) >= 0 ? '#16a34a' : '#dc2626' },
            { label: '수익률', val: `${parseFloat(tooltip.retPct) >= 0 ? '+' : ''}${tooltip.retPct}%`,     color: parseFloat(tooltip.retPct) >= 0 ? '#16a34a' : '#dc2626' },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, fontSize: 15, marginBottom: 4 }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>{label}</span>
              <span style={{ color, fontWeight: 600 }}>{val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
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

  return lines.map(l => `<p style="margin:0 0 12px;line-height:1.8;font-size:14px;color:#312e81">${l}</p>`).join('');
}

function WeightHistoryChart({ snapshots, prices }) {
  if (snapshots.length === 0) return (
    <div style={{ padding: '40px 16px', textAlign: 'center', color: '#cbd5e1', fontSize: 12 }}>
      스냅샷을 기록하면<br />비중 추이가 표시됩니다.
    </div>
  );

  const rows = [...snapshots].map(snap => {
    const { sorted, totalVal } = calcTotals(snap.holdings, prices);
    return { snap, sorted, totalVal };
  });

  const allIds = [...new Set(snapshots.flatMap(s => s.holdings.map(h => h.id)))];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {rows.map(({ snap, sorted, totalVal }) => {
        const maxVal = Math.max(...rows.map(r => r.totalVal));
        const barWidthPct = maxVal > 0 ? totalVal / maxVal * 100 : 0;
        const d = new Date(snap.datetime);
        const label = `${d.getFullYear()}.${d.getMonth()+1}.${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        return (
          <div key={snap.id}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>{label}</div>
            <div style={{ height: 20, overflow: 'hidden', position: 'relative' }}>
              <div style={{ width: `${barWidthPct}%`, height: '100%', display: 'flex' }}>
                {sorted.filter(h => h.curVal > 0).map(h => {
                  const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                  return (
                    <div
                      key={h.id}
                      title={`${h.info.name || h.id}: ${fmtCompact(h.curVal)} (${w.toFixed(1)}%)`}
                      style={{ width: `${w}%`, background: h.info.color || '#94a3b8', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0 }}
                    >
                      {w >= 10 && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.9)', pointerEvents: 'none', whiteSpace: 'nowrap' }}>
                          {w.toFixed(0)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ fontSize: 11, color: '#64748b', textAlign: 'right', marginTop: 3, fontWeight: 600 }}>{fmtCompact(totalVal)}</div>
          </div>
        );
      })}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', marginTop: 10, paddingTop: 12, borderTop: '1px solid #f1f5f9' }}>
        {allIds.map(id => {
          const info = ASSET_INFO[id] || {};
          return (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: info.color || '#94a3b8', flexShrink: 0, display: 'inline-block' }} />
              <span style={{ fontSize: 12, color: '#475569' }}>{info.name || id}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AssetDrawer({ holding, prices, onClose }) {
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const id = holding.id;
  const info = ASSET_INFO[id] || {};
  const isStock = !id.startsWith('KRW/');
  const cur = prices[id] ?? holding.snapshotPrice ?? 0;
  const curVal = holding.qty * cur;
  const cost = holding.qty * holding.avgPrice;
  const pnl = curVal - cost;
  const retPct = cost > 0 ? pnl / cost * 100 : 0;
  const pnlColor = pnl >= 0 ? '#16a34a' : '#dc2626';
  const logo = getLogo(id);
  const flag = getFlag(id);

  useEffect(() => {
    if (!isStock) return;
    setStatsLoading(true);
    fetch(`/api/v1/prices/${id}/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setStats(d); setStatsLoading(false); })
      .catch(() => setStatsLoading(false));
  }, [id]);

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 299, background: 'rgba(15,23,42,0.25)' }} />
      <div style={{
        position: 'fixed', right: 0, top: 0, width: 300, height: '100vh',
        background: 'white', boxShadow: '-8px 0 32px rgba(15,23,42,0.15)',
        zIndex: 300, display: 'flex', flexDirection: 'column',
        overflowY: 'auto', padding: '24px 20px',
      }}>
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {logo && <div style={{ width: 34, height: 34, borderRadius: 8, border: '1px solid #e8ecf0', overflow: 'hidden', background: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><img src={logo} alt={info.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} /></div>}
            {flag && <img src={flag} alt={info.name} style={{ width: 34, height: 24, borderRadius: 3, objectFit: 'cover', flexShrink: 0 }} />}
            <div>
              <div style={{ fontWeight: 700, fontSize: 17, color: '#1e293b' }}>{info.name || id}</div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>{info.sector} · {id}</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 22, color: '#94a3b8', padding: '0 4px', lineHeight: 1, flexShrink: 0 }}>×</button>
        </div>

        {/* 현재가 */}
        <div style={{ background: '#f8fafc', borderRadius: 10, padding: '14px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>현재가</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: '#1e293b' }}>{fmtCompact(cur)}</div>
        </div>

        {/* 보유 정보 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>보유 정보</div>
          {[
            { label: '수량',       val: `${fmt(holding.qty)}${info.unit || ''}` },
            { label: '평균 매입가', val: fmtCompact(holding.avgPrice) },
            { label: '평가액',     val: fmtCompact(curVal) },
            { label: '손익',       val: `${pnl >= 0 ? '+' : '-'}${fmtCompact(Math.abs(pnl))}`, color: pnlColor },
            { label: '수익률',     val: `${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%`, color: pnlColor },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f1f5f9', fontSize: 13 }}>
              <span style={{ color: '#64748b' }}>{label}</span>
              <span style={{ fontWeight: 600, color: color || '#1e293b' }}>{val}</span>
            </div>
          ))}
        </div>

        {/* 종목 정보 (주식만) */}
        {isStock && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>종목 정보</div>
            {statsLoading ? (
              <div style={{ fontSize: 13, color: '#94a3b8', textAlign: 'center', padding: '20px 0' }}>불러오는 중...</div>
            ) : stats ? (
              [
                { label: '52주 최고', val: stats.high52 ? fmtCompact(stats.high52) : '-' },
                { label: '52주 최저', val: stats.low52  ? fmtCompact(stats.low52)  : '-' },
                { label: 'PER',      val: stats.per != null ? `${stats.per}` : '적자' },
                { label: 'PBR',      val: stats.pbr != null ? `${stats.pbr}` : '-' },
                { label: '시가총액', val: stats.market_cap ? fmtShort(stats.market_cap) : '-' },
                { label: '거래량',   val: stats.volume  ? `${fmt(stats.volume)}주`  : '-' },
              ].map(({ label, val }) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f1f5f9', fontSize: 13 }}>
                  <span style={{ color: '#64748b' }}>{label}</span>
                  <span style={{ fontWeight: 600, color: '#1e293b' }}>{val}</span>
                </div>
              ))
            ) : null}
          </div>
        )}
      </div>
    </>
  );
}

function SnapshotCard({ snap, prices, onDelete }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [drawerHolding, setDrawerHolding] = useState(null);
  const { totalVal, totalCost, sorted } = calcTotals(snap.holdings, prices);
  const totalPnl = totalVal - totalCost;
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
  const pnlColor = totalPnl >= 0 ? '#16a34a' : '#dc2626';
  const aiHtml = buildAiHtml(sorted, totalVal, totalCost);

  return (
    <>
    {drawerHolding && (
      <AssetDrawer holding={drawerHolding} prices={prices} onClose={() => setDrawerHolding(null)} />
    )}
    <div className="snapshot-card">
      <div className="snapshot-card-header">
        <span className="snapshot-datetime">{fmtDatetime(snap.datetime)}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 6, padding: '2px 10px', fontSize: 11, color: '#64748b', cursor: 'pointer' }}
            onClick={() => setDetailOpen(true)}
          >
            자세히 보기
          </button>
          <button className="snapshot-delete-btn" onClick={() => onDelete(snap.id)} title="삭제">✕</button>
        </div>
      </div>

      {detailOpen && (
        <div className="modal-overlay" onClick={() => setDetailOpen(false)}>
          <div className="modal-box" style={{ width: 520, maxHeight: '80vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
            <div className="modal-title" style={{ fontSize: 14 }}>📋 {fmtDatetime(snap.datetime)} 종목 상세</div>
            <div className="snapshot-legend" style={{ maxHeight: 'none' }}>
              {sorted.map(h => {
                const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                const pnl = h.curVal - h.cost;
                const pnlPct = h.cost > 0 ? pnl / h.cost * 100 : 0;
                const pc = pnl >= 0 ? '#16a34a' : '#dc2626';
                return (
                  <div key={h.id} className="snapshot-legend-row" style={{ padding: '7px 0' }}>
                    <span className="snapshot-legend-dot" style={{ background: h.info.color || '#94a3b8' }} />
                    <span className="snapshot-legend-name" style={{ fontSize: 13 }}>{h.info.name || h.id}</span>
                    <span className="snapshot-legend-pct" style={{ width: 48 }}>{w.toFixed(1)}%</span>
                    <span className="snapshot-legend-val" style={{ width: 60 }}>{fmtCompact(h.curVal)}</span>
                    <span className="snapshot-legend-pnl" style={{ width: 60, color: pc }}>{pnl >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%</span>
                  </div>
                );
              })}
            </div>
            <div className="snapshot-summary" style={{ marginTop: 14, gridTemplateColumns: 'repeat(2, 1fr)' }}>
              {[
                { label: '총 매입 원가', val: fmtCompact(totalCost) },
                { label: '총 평가액',   val: fmtCompact(totalVal) },
                { label: '총 손익',     val: (totalPnl >= 0 ? '+' : '-') + fmtCompact(Math.abs(totalPnl)), color: pnlColor },
                { label: '수익률',      val: (totalPnlPct >= 0 ? '+' : '') + totalPnlPct.toFixed(2) + '%', color: pnlColor },
              ].map(({ label, val, color }) => (
                <div key={label} className="snapshot-summary-item">
                  <div className="snapshot-summary-label">{label}</div>
                  <div className="snapshot-summary-val" style={{ color: color || 'inherit' }}>{val}</div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDetailOpen(false)}>닫기</button>
            </div>
          </div>
        </div>
      )}

      <div className="snapshot-body">
        {/* 1열: AI 분석 */}
        <div className="snapshot-ai">
          <div className="snapshot-ai-header">
            <span className="ai-badge" style={{ fontSize: 11 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
            <span style={{ fontSize: 13, color: '#6d28d9', fontWeight: 600 }}>포트폴리오 분석</span>
          </div>
          <div dangerouslySetInnerHTML={{ __html: aiHtml }} />
        </div>

        {/* 2열: 도넛 차트 */}
        <div className="snapshot-chart-center">
          <DonutChart sorted={sorted} totalVal={totalVal} size={460} onSegmentClick={setDrawerHolding} />
        </div>

        {/* 3열: 요약 */}
        <div className="snapshot-right">
          <div className="snapshot-summary">
            {[
              { label: '총 매입 원가', val: fmtCompact(totalCost) },
              { label: '총 평가액',   val: fmtCompact(totalVal) },
              { label: '총 손익',     val: (totalPnl >= 0 ? '+' : '-') + fmtCompact(Math.abs(totalPnl)), color: pnlColor },
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
    </>
  );
}

export default function MyReportPage() {
  const [snapshots, setSnapshots] = useState([]);
  const [prices, setPrices] = useState({});
  const [pricesLoaded, setPricesLoaded] = useState(false);
  const [snapshotsLoaded, setSnapshotsLoaded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [holdings, setHoldings] = useState([]);
  const [addAsset, setAddAsset] = useState('005930');
  const [addQty, setAddQty] = useState('1');
  const [addPrice, setAddPrice] = useState('');
  const [generating, setGenerating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    fetchSnapshots().then(s => { setSnapshots(s); setSnapshotsLoaded(true); });
    loadPrices();
  }, []);

  async function loadPrices() {
    try {
      const [pr, fr] = await Promise.all([
        fetchWithAuth('/api/v1/prices/latest'),
        fetchWithAuth('/api/v1/exchange-rates/latest'),
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
      if (!pricesLoaded) alert('가격 데이터를 불러오는 중입니다. 잠시 후 다시 시도하거나 평균 매입가를 직접 입력해주세요.');
      else alert('평균 매입가를 직접 입력해주세요.');
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
    setTimeout(async () => {
      const snap = { id: 'snap_' + Date.now(), datetime: new Date().toISOString(), holdings: holdings.map(h => ({ ...h, snapshotPrice: getPrice(h.id) })) };
      try {
        await postSnapshot(snap);
      } catch (e) {
        console.error(e);
        alert(`스냅샷 저장 실패: ${e.message}`);
        setGenerating(false);
        return;
      }
      const next = await fetchSnapshots();
      setSnapshots(next);
      setHoldings([]);
      setAddQty('1'); setAddPrice(prices[addAsset] ? String(prices[addAsset]) : '');
      setFormOpen(false);
      setGenerating(false);
    }, 800);
  }

  function deleteSnapshot(id) { setDeleteTarget(id); }

  async function confirmDelete() {
    await deleteSnapshotApi(deleteTarget);
    setSnapshots(prev => prev.filter(s => s.id !== deleteTarget));
    setDeleteTarget(null);
  }

  if (!snapshotsLoaded) return <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>불러오는 중...</div>;

  const totalCount = snapshots.length;
  const formTotalVal = holdings.reduce((s, h) => s + h.qty * getPrice(h.id), 0);

  return (
    <>
    <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
      {/* 메인 콘텐츠 */}
      <div style={{ flex: 1, minWidth: 0, overflowX: 'auto' }}>
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
                placeholder={!pricesLoaded ? '가격 불러오는 중...' : prices[addAsset] ? String(prices[addAsset]) : '직접 입력'}
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
      </div>{/* end 메인 콘텐츠 */}

      {/* 오른쪽 고정 패널: 비중 추이 */}
      <div style={{ width: 280, flexShrink: 0, position: 'sticky', top: 16, alignSelf: 'flex-start' }}>
        <div className="other-card" style={{ padding: '16px 16px 14px', maxHeight: 'calc(100vh - 90px)', overflowY: 'auto' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#475569', marginBottom: 16 }}>
            자산 비중 추이
          </div>
          <WeightHistoryChart snapshots={snapshots} prices={prices} />
        </div>
      </div>
    </div>{/* end 2열 wrapper */}
    </>
  );
}
