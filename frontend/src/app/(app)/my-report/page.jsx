'use client';
import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { handleUnauthorized, fetchWithAuth } from '@/lib/auth';
import { ASSETS } from '@/lib/data';
import StockDetailModal from '@/components/StockDetailModal';
import LoadingSpinner from '@/components/LoadingSpinner';

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
  'USD': { name: 'USD/KRW', color: ASSETS['USD'].color, sector: '환율', unit: '원' },
};

const STOCK_IDS = ['005930','000660','005380','000270','079550','012450','105560','055550','051910','096770'];
const FX_IDS    = ['USD'];

const LOGO_MAP = {
  '005930': 'samsung.svg', '000660': 'skhynix.svg',
  '005380': 'hyundai.png', '000270': 'kia.png',
  '079550': 'lignex1.svg', '012450': 'hanwha.svg',
  '105560': 'kb.svg',      '055550': 'shinhan.svg',
  '051910': 'lgchem.svg',  '096770': 'skinnovation.svg',
};
const FLAG_MAP = {
  'USD': 'us',
};
const getLogo = id => LOGO_MAP[id] ? `/assets/logos/${LOGO_MAP[id]}` : null;
const getFlag = id => FLAG_MAP[id] ? `/assets/flags/${FLAG_MAP[id]}.png` : null;

const MAX_SNAPSHOTS = 10;

const fmt = n => Math.round(n).toLocaleString('ko-KR');
const fmtPrice = (id, n) => id === 'USD' ? n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',') : fmt(n);
function josa(word, type) {
  const last = word[word.length - 1];
  const code = last.charCodeAt(0);
  const hasBatchim = code >= 0xAC00 && code <= 0xD7A3 && (code - 0xAC00) % 28 !== 0;
  const batchimIdx = hasBatchim ? (code - 0xAC00) % 28 : 0;
  if (type === '이/가') return hasBatchim ? '이' : '가';
  if (type === '은/는') return hasBatchim ? '은' : '는';
  if (type === '을/를') return hasBatchim ? '을' : '를';
  if (type === '으로/로') return hasBatchim && batchimIdx !== 8 ? '으로' : '로';
  return type;
}
function initPrice(id, price) {
  if (!price) return '';
  const n = parseFloat(price);
  if (isNaN(n)) return '';
  return id === 'USD' ? n.toFixed(2) : String(Math.round(n));
}
function parseNumberInput(value) {
  return parseFloat(String(value).replace(/,/g, ''));
}
function formatNumberInput(value) {
  const raw = String(value ?? '').replace(/,/g, '');
  if (!raw) return '';
  const [intPart, decPart] = raw.split('.');
  const signed = intPart.startsWith('-');
  const digits = signed ? intPart.slice(1) : intPart;
  const formattedInt = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${signed ? '-' : ''}${formattedInt}${raw.includes('.') ? `.${decPart ?? ''}` : ''}`;
}
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

function darkenColor(hex, amount = 40) {
  if (!hex || !hex.startsWith('#')) return hex;
  const num = parseInt(hex.slice(1), 16);
  const r = Math.max(0, (num >> 16) - amount);
  const g = Math.max(0, ((num >> 8) & 0xff) - amount);
  const b = Math.max(0, (num & 0xff) - amount);
  return `rgb(${r},${g},${b})`;
}

function DonutChart({ sorted, totalVal, size = 180, onSegmentClick, hoveredStockId, onHoverStock }) {
  const [tooltip, setTooltip] = useState(null);
  const wrapRef = useRef(null);
  const chartId = useRef(`dc-${Math.random().toString(36).slice(2)}`).current;

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

  const fs1 = Math.round(size * 0.085), fs2 = Math.round(size * 0.104);

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size, display: 'block' }}
        onMouseLeave={() => setTooltip(null)}>
        <defs>
          {segments.map((seg, i) => {
            const base = seg.h.info.color || '#94a3b8';
            return (
              <linearGradient key={i} id={`${chartId}-${i}`} x1="0" y1="0" x2="0" y2={size} gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor={base} />
                <stop offset="100%" stopColor={darkenColor(base, 35)} />
              </linearGradient>
            );
          })}
        </defs>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
        {segments.map((seg, i) => (
          <path
            key={i}
            d={arcPath(seg.startAngle, seg.endAngle)}
            fill={`url(#${chartId}-${i})`}
            style={{ cursor: 'pointer', transition: 'opacity 0.2s, filter 0.2s', opacity: hoveredStockId !== null && hoveredStockId !== seg.h.id ? 0.55 : 1, filter: hoveredStockId === seg.h.id ? 'brightness(1.12)' : 'none' }}
            onMouseEnter={e => {
              onHoverStock?.(seg.h.id);
              const pnl = seg.h.curVal - seg.h.cost;
              const retPct = seg.h.cost > 0 ? pnl / seg.h.cost * 100 : 0;
              setTooltip({ name: seg.h.info.name || seg.h.id, pct: seg.w.toFixed(1), val: fmtCompact(seg.h.curVal), pnl, retPct: retPct.toFixed(2), color: seg.h.info.color || '#94a3b8', x: e.clientX, y: e.clientY });
            }}
            onMouseMove={e => {
              setTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null);
            }}
            onMouseLeave={() => {
              onHoverStock?.(null);
              setTooltip(null);
            }}
            onClick={() => { setTooltip(null); onSegmentClick && onSegmentClick(seg.h); }}
          />
        ))}
        <text x={cx} y={cy - size * 0.055} textAnchor="middle" fontSize={fs1} fontWeight="600" fill="#64748b" pointerEvents="none">총 평가액</text>
        <text x={cx} y={cy + size * 0.075} textAnchor="middle" fontSize={fs2} fontWeight="900" fill="#1e293b" pointerEvents="none">{fmtShort(totalVal)}</text>
      </svg>
      {tooltip && typeof document !== 'undefined' && createPortal(
        <div style={{
          position: 'fixed',
          left: tooltip.x > window.innerWidth - 240 ? tooltip.x - 218 : tooltip.x + 10,
          top: Math.max(8, Math.min(tooltip.y + 10, window.innerHeight - 178)),
          background: 'white',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: '7px 14px',
          fontSize: 16,
          fontWeight: 600,
          color: '#1e293b',
          boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
          zIndex: 9999,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #f1f5f9' }}>
            <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: tooltip.color, flexShrink: 0 }} />
            <span style={{ fontWeight: 700, fontSize: 18 }}>{tooltip.name}</span>
          </div>
          {[
            { label: '비중',   val: `${tooltip.pct}%`,  color: '#1e293b' },
            { label: '평가액', val: tooltip.val,         color: '#1e293b' },
            { label: '손익',   val: `${tooltip.pnl >= 0 ? '+' : '-'}${fmtCompact(Math.abs(tooltip.pnl))}`, color: parseFloat(tooltip.retPct) >= 0 ? '#dc2626' : '#2563eb' },
            { label: '수익률', val: `${parseFloat(tooltip.retPct) >= 0 ? '+' : ''}${tooltip.retPct}%`,     color: parseFloat(tooltip.retPct) >= 0 ? '#dc2626' : '#2563eb' },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 20, fontSize: 16, marginBottom: 4 }}>
              <span style={{ color: '#94a3b8', fontWeight: 500 }}>{label}</span>
              <span style={{ color, fontWeight: 600 }}>{val}</span>
            </div>
          ))}
        </div>,
        document.body
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
    lines.push(`<strong>✅ 분산 투자 양호</strong>: 최고 비중 종목인 <strong>${top.name}</strong>${josa(top.name, '이/가')} <strong>${top.w.toFixed(1)}%</strong>로 집중 위험이 낮습니다. 현재 비중 분산 수준은 안정적입니다.`);

  // 2. 섹터 분석
  if (sectorList.length === 1)
    lines.push(`<strong>🔍 섹터 단일 집중</strong>: 모든 자산이 <strong>${sectorList[0][0]}</strong> 섹터에 집중되어 있습니다. 섹터 리스크에 취약하므로 다른 섹터 편입을 검토하세요.`);
  else if (sectorList[0][1] > 70)
    lines.push(`<strong>🔍 섹터 쏠림 주의</strong>: <strong>${sectorList[0][0]}</strong> 섹터 비중이 <strong>${sectorList[0][1].toFixed(0)}%</strong>로 매우 높습니다. ${sectorList.slice(1, 3).map(([s]) => s).join(', ')} 등 타 섹터 비중을 늘려 균형을 맞추는 것이 좋습니다.`);
  else
    lines.push(`<strong>📂 섹터 구성</strong>: ${sectorList.map(([s, w]) => `<strong>${s}</strong> ${w.toFixed(0)}%`).join(', ')}으로 구성되어 있습니다.`);

  // 3. 수익/손실 종목
  if (gainers.length > 0 && losers.length > 0) {
    lines.push(`<strong>📈 성과 상위</strong>: <strong>${gainers[0].name}</strong>${josa(gainers[0].name, '이/가')} <span style="color:#dc2626">+${gainers[0].pnlPct.toFixed(1)}%</span>로 가장 높은 수익을 기록 중입니다.`);
    lines.push(`<strong>📉 손실 종목</strong>: <strong>${losers[0].name}</strong>${josa(losers[0].name, '이/가')} <span style="color:#2563eb">${losers[0].pnlPct.toFixed(1)}%</span> 손실 중입니다. 손절 기준 또는 추가 매수 여부를 점검해 보세요.`);
  } else if (gainers.length > 0) {
    lines.push(`<strong>📈 전 종목 수익</strong>: <strong>${gainers[0].name}</strong>${josa(gainers[0].name, '이/가')} <span style="color:#dc2626">+${gainers[0].pnlPct.toFixed(1)}%</span>로 최고 성과를 기록 중입니다.`);
  } else if (losers.length > 0) {
    lines.push(`<strong>📉 전 종목 손실</strong>: <strong>${losers[0].name}</strong>${josa(losers[0].name, '이/가')} <span style="color:#2563eb">${losers[0].pnlPct.toFixed(1)}%</span>로 가장 큰 손실입니다. 시장 상황과 보유 근거를 재검토하세요.`);
  }

  // 4. 종합 의견
  if (avgReturn > 15)
    lines.push(`<strong>💡 종합 의견</strong>: 포트폴리오 전체 수익률이 <span style="color:#dc2626">+${avgReturn.toFixed(1)}%</span>로 우수한 성과를 기록 중입니다. 수익 실현 시점을 고려하거나 이익을 재투자하는 전략을 검토해 보세요.`);
  else if (avgReturn > 0)
    lines.push(`<strong>💡 종합 의견</strong>: <span style="color:#dc2626">+${avgReturn.toFixed(1)}%</span>의 플러스 수익률을 유지하고 있습니다. 분산 투자 원칙을 지키며 꾸준히 운용하고 있는 것으로 보입니다.`);
  else
    lines.push(`<strong>💡 종합 의견</strong>: 현재 <span style="color:#2563eb">${avgReturn.toFixed(1)}%</span>의 손실 구간에 있습니다. 손실 원인을 분석하고 포트폴리오 재구성 여부를 검토해 보세요.`);

  // 5. 메모
  lines.push(`<strong>📝 메모</strong>: 포트폴리오 AI는 대시보드 AI보다는 좀 더 포트폴리오 쪽에 치중하도록! 나이대, 성별, 투자성향은 여기에 반영하는게 맞을까?`);

  return lines.map(l => `<p style="margin:0 0 14px;line-height:1.8;font-size:18px;color:#475569;font-weight:500">${l}</p>`).join('');
}

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// LLM이 생성한 구조화 분석(ai_analysis)을 HTML로 렌더링.
// 필드가 없으면(레거시 스냅샷/실패) 호출 측에서 buildAiHtml() fallback 사용.
function buildAiHtmlFromAnalysis(analysis) {
  const lines = [];
  const pStyle = 'margin:0 0 14px;line-height:1.8;font-size:18px;color:#475569;font-weight:500';

  if (analysis.overall_summary) {
    lines.push(
      `<p style="${pStyle}"><strong class="snapshot-ai-section-label">🧭 종합 요약</strong>: ${escapeHtml(analysis.overall_summary)}</p>`
    );
  }

  if (analysis.risk_alignment) {
    lines.push(
      `<p style="${pStyle}"><strong class="snapshot-ai-section-label">🎯 투자성향 적합도</strong>: ${escapeHtml(analysis.risk_alignment)}</p>`
    );
  }

  if (analysis.suggestions) {
    const sugText = Array.isArray(analysis.suggestions)
      ? analysis.suggestions.map((s, i) => `${i + 1}. ${escapeHtml(s)}`).join('<br/>')
      : escapeHtml(String(analysis.suggestions));
    lines.push(
      `<p style="${pStyle}"><strong class="snapshot-ai-section-label">💡 제안</strong>: ${sugText}</p>`
    );
  }

  if (Array.isArray(analysis.sources) && analysis.sources.length > 0) {
    const items = analysis.sources
      .filter(source => source?.url)
      .map(source => {
        const href = escapeHtml(String(source.url)).replace(/"/g, '&quot;');
        const title = escapeHtml(String(source.title || source.url));
        const ticker = source.ticker
          ? `<span style="color:#64748b;font-weight:600">${escapeHtml(String(source.ticker))}</span> `
          : '';
        return `<li style="margin:0 0 8px;line-height:1.7"><a href="${href}" target="_blank" rel="noopener noreferrer" style="color:#2563eb;text-decoration:none;font-size:16px">${ticker}${title}</a></li>`;
      });
    if (items.length > 0) {
      lines.push('<p style="margin:16px 0 8px"><strong class="snapshot-ai-section-label">📰 관련 최신 뉴스</strong></p>');
      lines.push(`<ul style="margin:0 0 14px;padding-left:20px">${items.join('')}</ul>`);
    }
  }

  return lines.join('');
}

function buildAiFooter(analysis) {
  const footerParts = [];
  if (typeof analysis.confidence === 'number') {
    footerParts.push(`분석 신뢰도 ${Math.round(analysis.confidence * 100)}%`);
  }
  footerParts.push('최근 30일 뉴스 요약 기반');
  return footerParts.join(' · ');
}

function WeightHistoryChart({ snapshots, prices, onSnapClick, selectedSnapId }) {
  const [tooltip, setTooltip] = useState(null);
  const [sortMode, setSortMode] = useState('value');
  const [hoveredId, setHoveredId] = useState(null);
  const containerRef = useRef(null);

  if (snapshots.length === 0) return (
    <div style={{ padding: '40px 16px', textAlign: 'center', color: '#cbd5e1', fontSize: 13 }}>
      스냅샷을 기록하면<br />비중 추이가 표시됩니다.
    </div>
  );

  const rows = [...snapshots].map(snap => {
    const { sorted, totalVal } = calcTotals(snap.holdings, prices);
    return { snap, sorted, totalVal };
  });

  const allIds = [...new Set(snapshots.flatMap(s => s.holdings.map(h => h.id)))];
  const rowCount = rows.length;
  const rowGap = rowCount >= 9 ? 8 : 12;
  const barHeight = rowCount >= 9 ? 'clamp(22px, 3.4vh, 34px)' : 'clamp(28px, 5vh, 48px)';

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', flex: 1, height: '100%', minHeight: 0, position: 'relative' }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 6, flexShrink: 0 }}>
        {[{ key: 'value', label: '금액순' }, { key: 'name', label: '가나다순' }].map(({ key, label }) => (
          <button key={key} onClick={() => setSortMode(key)} style={{
            padding: '3px 9px', fontSize: 13, fontWeight: 600, borderRadius: 6, cursor: 'pointer', border: 'none', fontFamily: 'inherit',
            background: sortMode === key ? '#2563eb' : '#f1f5f9',
            color: sortMode === key ? 'white' : '#64748b',
          }}>{label}</button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateRows: `repeat(${MAX_SNAPSHOTS}, minmax(0, 1fr))`, gap: rowGap }}>
      {rows.map(({ snap, sorted, totalVal }) => {
        const maxVal = Math.max(...rows.map(r => r.totalVal));
        const barWidthPct = maxVal > 0 ? totalVal / maxVal * 100 : 0;
        const d = new Date(snap.datetime);
        const label = `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        const displaySorted = sortMode === 'name'
          ? [...sorted].sort((a, b) => (a.info.name || a.id).localeCompare(b.info.name || b.id, 'ko'))
          : sorted;
        return (
          <div key={snap.id} onClick={() => onSnapClick?.(snap.id)} style={{ cursor: 'pointer', borderRadius: 7, padding: '4px 6px', margin: '0 -6px', minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', background: selectedSnapId === snap.id ? '#eff6ff' : 'transparent', outline: selectedSnapId === snap.id ? '1.5px solid #bfdbfe' : '1.5px solid transparent', transition: 'background 0.15s' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <span style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{label}</span>
              <span style={{ fontSize: 13, color: '#1e293b', fontWeight: 700 }}>{fmtCompact(totalVal)}</span>
            </div>
            <div style={{ height: barHeight, overflow: 'hidden', position: 'relative', borderRadius: 3 }}>
              <div style={{ width: `${barWidthPct}%`, height: '100%', display: 'flex', borderRadius: 3, overflow: 'hidden' }}>
                {displaySorted.filter(h => h.curVal > 0).map(h => {
                  const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                  const effectiveW = barWidthPct * w / 100;
                  return (
                    <div
                      key={h.id}
                      style={{ width: `${w}%`, background: h.info.color || '#94a3b8', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0, cursor: 'default', transition: 'opacity 0.2s, filter 0.2s', opacity: hoveredId !== null && hoveredId !== h.id ? 0.35 : 1, filter: hoveredId === h.id ? 'brightness(1.12)' : 'none' }}
                      onMouseEnter={e => {
                        setHoveredId(h.id);
                        setTooltip({ name: h.info.name || h.id, val: fmtCompact(h.curVal), pct: w.toFixed(1), color: h.info.color || '#94a3b8', x: e.clientX, y: e.clientY });
                      }}
                      onMouseMove={e => {
                        setTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null);
                      }}
                      onMouseLeave={() => { setHoveredId(null); setTooltip(null); }}
                    >
                      {effectiveW >= 8 && (
                        <span style={{ fontSize: 12, fontWeight: 700, color: 'rgba(255,255,255,0.9)', pointerEvents: 'none', whiteSpace: 'nowrap' }}>
                          {w.toFixed(0)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
      </div>{/* end rows flex */}

      {tooltip && (
        <div style={{
          position: 'fixed',
          left: Math.min(tooltip.x + 12, window.innerWidth - 160),
          top: tooltip.y - 52,
          background: 'white',
          borderRadius: 8,
          padding: '7px 11px',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
          zIndex: 10,
          boxShadow: '0 4px 14px rgba(0,0,0,0.13)',
          border: `1.5px solid ${tooltip.color}`,
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#1e293b', marginBottom: 2 }}>{tooltip.name}</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>{tooltip.val} <span style={{ color: tooltip.color, fontWeight: 600 }}>({tooltip.pct}%)</span></div>
        </div>
      )}
    </div>
  );
}

function AssetDrawer({ holding, prices, onClose }) {
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const id = holding.id;
  const info = ASSET_INFO[id] || {};
  const isStock = id !== 'USD';
  const cur = prices[id] ?? holding.snapshotPrice ?? 0;
  const curVal = holding.qty * cur;
  const cost = holding.qty * holding.avgPrice;
  const pnl = curVal - cost;
  const retPct = cost > 0 ? pnl / cost * 100 : 0;
  const pnlColor = pnl >= 0 ? '#dc2626' : '#2563eb';
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
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 299, background: 'rgba(15,23,42,0.35)' }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 600, background: 'white', borderRadius: 16,
        boxShadow: '0 8px 40px rgba(15,23,42,0.18)', zIndex: 300, padding: '24px 28px',
      }}>
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {logo && <div style={{ width: 34, height: 34, borderRadius: 8, border: '1px solid #e8ecf0', overflow: 'hidden', background: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><img src={logo} alt={info.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} /></div>}
            {flag && <img src={flag} alt={info.name} style={{ width: 34, height: 24, borderRadius: 3, objectFit: 'cover', flexShrink: 0 }} />}
            <div>
              <div style={{ fontWeight: 700, fontSize: 18, color: '#1e293b' }}>{info.name || id}</div>
              <div style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>{info.sector} · {id}</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 23, color: '#94a3b8', padding: '0 4px', lineHeight: 1, flexShrink: 0 }}>×</button>
        </div>

        {/* 현재가 */}
        <div style={{ background: '#f8fafc', borderRadius: 10, padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 6 }}>현재가</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 23, fontWeight: 800, color: '#1e293b' }}>{fmtCompact(cur)}</div>
            {stats?.change != null && (() => {
              const up = stats.change >= 0;
              const color = up ? '#dc2626' : '#2563eb';
              const arrow = up ? '▲' : '▼';
              return (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, fontSize: 14, fontWeight: 600, color }}>
                  <span>{arrow} {fmtCompact(Math.abs(stats.change))}</span>
                  <span style={{ fontSize: 13 }}>({up ? '+' : ''}{stats.change_pct}%)</span>
                </div>
              );
            })()}
          </div>
        </div>

        {/* 2열 레이아웃 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 56px' }}>
          {/* 보유 정보 */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>보유 정보</div>
            {[
              { label: '수량',        val: `${fmt(holding.qty)}${info.unit || ''}` },
              { label: '평균 매입가', val: fmtCompact(holding.avgPrice) },
              { label: '평가액',      val: fmtCompact(curVal) },
              { label: '손익',        val: `${pnl >= 0 ? '+' : '-'}${fmtCompact(Math.abs(pnl))}`, color: pnlColor },
              { label: '수익률',      val: `${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%`, color: pnlColor },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '11px 0', borderBottom: '1px solid #f1f5f9', fontSize: 14 }}>
                <span style={{ color: '#64748b' }}>{label}</span>
                <span style={{ fontWeight: 600, color: color || '#1e293b' }}>{val}</span>
              </div>
            ))}
          </div>

          {/* 종목 정보 (주식만) */}
          {isStock && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>종목 정보</div>
              {statsLoading ? (
                ['52주 최고', '52주 최저', 'PER', 'PBR', '시가총액', '거래량'].map(label => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 0', borderBottom: '1px solid #f1f5f9', fontSize: 14 }}>
                    <span style={{ color: '#64748b' }}>{label}</span>
                    <span className="loading-dots">···</span>
                  </div>
                ))
              ) : stats ? (
                [
                  { label: '52주 최고', val: stats.high52 ? fmtCompact(stats.high52) : '-' },
                  { label: '52주 최저', val: stats.low52  ? fmtCompact(stats.low52)  : '-' },
                  { label: 'PER',       val: stats.per != null ? `${stats.per}` : '적자' },
                  { label: 'PBR',       val: stats.pbr != null ? `${stats.pbr}` : '-' },
                  { label: '시가총액',  val: stats.market_cap ? fmtShort(stats.market_cap) : '-' },
                  { label: '거래량',    val: stats.volume  ? `${fmt(stats.volume)}주`  : '-' },
                ].map(({ label, val }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '11px 0', borderBottom: '1px solid #f1f5f9', fontSize: 14 }}>
                    <span style={{ color: '#64748b' }}>{label}</span>
                    <span style={{ fontWeight: 600, color: '#1e293b' }}>{val}</span>
                  </div>
                ))
              ) : null}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function SnapshotCard({ snap, prices, onDelete, hoveredStockId, onHoverStock }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [drawerHolding, setDrawerHolding] = useState(null);
  const [holdingTooltip, setHoldingTooltip] = useState(null);
  const { totalVal, totalCost, sorted } = calcTotals(snap.holdings, prices);

  const totalPnl = totalVal - totalCost;
  const totalPnlPct = totalCost > 0 ? totalPnl / totalCost * 100 : 0;
  const pnlColor = totalPnl >= 0 ? '#dc2626' : '#2563eb';
  // LLM 분석(ai_analysis)이 있으면 우선 사용, 없으면(레거시/실패) rule-based fallback
  const aiHtml = snap.ai_analysis
    ? buildAiHtmlFromAnalysis(snap.ai_analysis)
    : buildAiHtml(sorted, totalVal, totalCost);
  const aiFooter = snap.ai_analysis ? buildAiFooter(snap.ai_analysis) : null;

  return (
    <>
    {drawerHolding && (
      drawerHolding.id !== 'USD'
        ? <StockDetailModal stockId={drawerHolding.id} holding={drawerHolding} snapshotDate={snap.datetime} onClose={() => setDrawerHolding(null)} />
        : <AssetDrawer holding={drawerHolding} prices={prices} onClose={() => setDrawerHolding(null)} />
    )}
    <div className="snapshot-card">
      <div className="snapshot-card-header">
        <span className="snapshot-datetime">{fmtDatetime(snap.datetime)}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 6, padding: '2px 10px', fontSize: 14, color: '#64748b', cursor: 'pointer' }}
            onClick={() => setDetailOpen(true)}
          >
            자세히 보기
          </button>
          <button className="snapshot-delete-btn" onClick={() => onDelete(snap.id)} title="삭제">✕</button>
        </div>
      </div>

      {detailOpen && (
        <div className="modal-overlay" onClick={() => setDetailOpen(false)}>
          <div className="modal-box" style={{ width: 780, maxHeight: '80vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div className="modal-title" style={{ fontSize: 15, marginBottom: 0 }}>📋 {fmtDatetime(snap.datetime)} 종목 상세</div>
              <div style={{ fontSize: 12, color: '#94a3b8' }}>현재가·평가액·손익은 스냅샷 저장 시점의 시장 가격을 기준으로 산출됩니다.</div>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 4 }}>
              <thead>
                <tr>
                  {['종목', '수량', '평균 매입가', '현재가', '매입 원가', '평가액', '손익', '수익률'].map((label, i) => (
                    <th key={label} style={{ padding: '5px 7px', fontSize: 11, fontWeight: 700, color: '#94a3b8', borderBottom: '1px solid #f1f5f9', textAlign: i === 0 ? 'left' : 'right', whiteSpace: 'nowrap' }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map(h => {
                  const w = totalVal > 0 ? h.curVal / totalVal * 100 : 0;
                  const pnl = h.curVal - h.cost;
                  const pnlPct = h.cost > 0 ? pnl / h.cost * 100 : 0;
                  const pc = pnl >= 0 ? '#dc2626' : '#2563eb';
                  return (
                    <tr key={h.id}>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'left', whiteSpace: 'nowrap' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', display: 'inline-block', marginRight: 5, background: h.info.color || '#94a3b8', flexShrink: 0 }} />
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>{h.info.name || h.id}</span>
                        <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 5 }}>{w.toFixed(1)}%</span>
                      </td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: '#475569' }}>{fmt(h.qty)}{h.info.unit || ''}</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: '#475569' }}>{fmt(h.avgPrice)}원</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: '#475569' }}>{fmt(h.curPrice)}원</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: '#475569' }}>{fmtCompact(h.cost)}</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: '#1e293b', fontWeight: 600 }}>{fmtCompact(h.curVal)}</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: pc, fontWeight: 600 }}>{pnl >= 0 ? '+' : ''}{fmtCompact(Math.abs(pnl))}</td>
                      <td style={{ padding: '8px 7px', borderBottom: '1px solid #f8fafc', textAlign: 'right', color: pc, fontWeight: 700 }}>{pnl >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
              {[
                { label: '총 매입 원가', val: fmtCompact(totalCost) },
                { label: '총 평가액',   val: fmtCompact(totalVal) },
                { label: '총 손익',     val: (totalPnl >= 0 ? '+' : '-') + fmtCompact(Math.abs(totalPnl)), color: pnlColor },
                { label: '수익률',      val: (totalPnlPct >= 0 ? '+' : '') + totalPnlPct.toFixed(2) + '%', color: pnlColor },
              ].map(({ label, val, color }) => (
                <div key={label} className="snapshot-summary-item">
                  <div className="snapshot-summary-label">{label}</div>
                  <div className="snapshot-summary-val" style={{ color: color || 'inherit', fontSize: 17 }}>{val}</div>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span className="ai-badge" style={{ fontSize: 12 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
              <span className="dashboard-section-title">포트폴리오 분석</span>
            </div>
            {aiFooter && <span className="snapshot-ai-meta">{aiFooter}</span>}
          </div>
          <div className="snapshot-ai-scroll-wrap">
            <div className="snapshot-ai-scroll">
              <div className="snapshot-ai-content" dangerouslySetInnerHTML={{ __html: aiHtml }} />
              {/* 종목별 분석 — JSX로 렌더링해 클릭 핸들러 사용 */}
              {snap.ai_analysis?.per_holding?.length > 0 && (
                <div className="holding-analysis" style={{ marginTop: aiHtml ? 2 : 0 }}>
                  <div className="snapshot-ai-section-label holding-analysis-title">📊 종목별 분석</div>
                {snap.ai_analysis.per_holding.map(h => {
                  const info = ASSET_INFO[h.ticker] || {};
                  const name = info.name || h.ticker;
                  const color = info.color || '#94a3b8';
                  const holding = sorted.find(s => s.id === h.ticker);
                  const holdingPct = totalVal > 0 && holding ? holding.curVal / totalVal * 100 : 0;
                  const prefix = name.slice(0, Math.min(3, name.length));
                  const comment = (h.comment || '').startsWith(prefix)
                    ? (h.comment || '').replace(/^[^\s,.(]+[은는이가을를도]?\s+/, '').trim()
                    : (h.comment || '');
                  return (
                    <div key={h.ticker} className="holding-entry" style={{ marginBottom: 8 }}>
                      <button className="holding-name"
                        onClick={() => holding && setDrawerHolding(holding)}
                        onMouseEnter={e => {
                          if (!holding) return;
                          onHoverStock?.(h.ticker);
                          const pnl = holding.curVal - holding.cost;
                          const retPct = holding.cost > 0 ? pnl / holding.cost * 100 : 0;
                          setHoldingTooltip({
                            name: holding.info.name || holding.id,
                            pct: holdingPct.toFixed(1),
                            val: fmtCompact(holding.curVal),
                            pnl: pnl >= 0 ? `+${fmtCompact(pnl)}` : `-${fmtCompact(Math.abs(pnl))}`,
                            retPct: retPct.toFixed(2),
                            color: holding.info.color || '#94a3b8',
                            x: e.clientX,
                            y: e.clientY,
                          });
                        }}
                        onMouseMove={e => setHoldingTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)}
                        onMouseLeave={() => {
                          onHoverStock?.(null);
                          setHoldingTooltip(null);
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          fontSize: 18,
                          fontWeight: 700,
                          color,
                          cursor: holding ? 'pointer' : 'default',
                          flexShrink: 0,
                          fontFamily: 'inherit',
                          textDecoration: 'none',
                          lineHeight: 1.4,
                          opacity: hoveredStockId !== null && hoveredStockId !== h.ticker ? 0.75 : 1,
                          transition: 'opacity 0.2s',
                        }}
                      >
                        {name}
                      </button>
                      <span className="holding-comment" style={{ fontSize: 18, color: '#475569', lineHeight: 1.75, fontWeight: 500 }}>{comment}</span>
                    </div>
                  );
                })}
                {holdingTooltip && typeof document !== 'undefined' && createPortal(
                  <div style={{
                    position: 'fixed',
                    left: holdingTooltip.x > window.innerWidth - 240 ? holdingTooltip.x - 220 : holdingTooltip.x + 10,
                    top: Math.max(8, Math.min(holdingTooltip.y + 10, window.innerHeight - 178)),
                    background: 'white',
                    border: '1px solid #e2e8f0',
                    borderRadius: 8,
                    padding: '7px 14px',
                    fontSize: 16,
                    fontWeight: 600,
                    color: '#1e293b',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                    pointerEvents: 'none',
                    whiteSpace: 'nowrap',
                    zIndex: 9999,
                    minWidth: 200,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #f1f5f9' }}>
                      <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: holdingTooltip.color, flexShrink: 0 }} />
                      <span style={{ fontWeight: 700, fontSize: 18 }}>{holdingTooltip.name}</span>
                    </div>
                    <div style={{ fontSize: 16, color: '#475569', lineHeight: 1.6 }}>
                      <div>비중: <span style={{ marginLeft: 8 }}>{holdingTooltip.pct}%</span></div>
                      <div>평가액: <span style={{ marginLeft: 8 }}>{holdingTooltip.val}</span></div>
                      <div>손익: <span style={{ marginLeft: 8, color: holdingTooltip.pnl && holdingTooltip.pnl.startsWith('+') ? '#dc2626' : '#2563eb', fontWeight: 700 }}>{holdingTooltip.pnl}</span></div>
                      <div>수익률: <span style={{ marginLeft: 8, color: holdingTooltip.retPct && Number(holdingTooltip.retPct) >= 0 ? '#dc2626' : '#2563eb', fontWeight: 700 }}>{holdingTooltip.retPct}%</span></div>
                    </div>
                  </div>, document.body)
                }
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 2열: 도넛 차트 (상단) + 1행 4열 요약 (하단) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', alignItems: 'center' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0 }}>
            <DonutChart sorted={sorted} totalVal={totalVal} size={170} onSegmentClick={setDrawerHolding} hoveredStockId={hoveredStockId} onHoverStock={onHoverStock} />
          </div>
          <div className="snapshot-summary" style={{ width: '100%' }}>
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
  const [selectedSnapId, setSelectedSnapId] = useState(null);
  const [hoveredStockId, setHoveredStockId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editQty, setEditQty] = useState('');
  const [editPrice, setEditPrice] = useState('');

  useEffect(() => {
    fetchSnapshots().then(s => { setSnapshots(s); setSnapshotsLoaded(true); setSelectedSnapId(s[0]?.id ?? null); });
    loadPrices();
  }, []);

  async function loadPrices() {
    try {
      const pr = await fetchWithAuth('/api/v1/prices/latest');
      const next = {};
      if (pr.ok) { const d = await pr.json(); d.forEach(({ ticker, close }) => { next[ticker] = close; }); }
      setPrices(next);
      if (next['005930']) setAddPrice(initPrice('005930', next['005930']));
    } catch { /* silent */ }
    setPricesLoaded(true);
  }

  function getPrice(id) { return prices[id] ?? ASSET_INFO[id]?.avgPrice ?? 0; }

  function addHolding() {
    const qty = parseFloat(addQty);
    if (!qty || qty <= 0) { alert('수량을 입력해주세요.'); return; }
    const manualPrice = parseNumberInput(addPrice);
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
    setAddQty('1'); setAddPrice(initPrice(addAsset, prices[addAsset]));
  }

  function removeHolding(id) { setHoldings(holdings.filter(h => h.id !== id)); }

  async function saveSnapshot() {
    if (holdings.length === 0) { alert('자산을 1개 이상 추가해주세요.'); return; }
    setGenerating(true);
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
    setSelectedSnapId(next[0]?.id ?? null);
    setHoldings([]);
    setAddQty('1'); setAddPrice(initPrice(addAsset, prices[addAsset]));
    setFormOpen(false);
    setGenerating(false);
  }

  function deleteSnapshot(id) { setDeleteTarget(id); }

  async function confirmDelete() {
    const deletedId = deleteTarget;
    await deleteSnapshotApi(deletedId);
    setSnapshots(prev => {
      const next = prev.filter(s => s.id !== deletedId);
      if (selectedSnapId === deletedId) setSelectedSnapId(next[0]?.id ?? null);
      return next;
    });
    setDeleteTarget(null);
  }

  if (!snapshotsLoaded) return (
    <div className="dashboard-empty-state" style={{ flex: 1, minHeight: '100%', padding: '0 16px' }}>
      <LoadingSpinner label="포트폴리오를 불러오는 중..." size={36} />
    </div>
  );

  const totalCount = snapshots.length;
  const formTotalVal = holdings.reduce((s, h) => s + h.qty * getPrice(h.id), 0);

  return (
    <>
    <div style={{ display: 'flex', gap: 20, alignItems: 'stretch', flex: 1, minHeight: 0 }}>
      {/* 메인 콘텐츠 */}
      <div style={{ flex: 1, minWidth: 0, overflowX: 'auto', display: 'flex', flexDirection: 'column' }}>
      <div className="sec-header">
        <div>
          <div>
            <div className="sec-title">마이 포트폴리오</div>
            <div className="sec-sub">포트폴리오 스냅샷 · 최대 {MAX_SNAPSHOTS}개 보관 {totalCount > 0 ? `· 현재 ${totalCount}개` : ''}</div>
          </div>
        </div>
        <button className="btn btn-primary" style={{ fontSize: 15 }} onClick={() => { setFormOpen(o => !o); if (!formOpen) setHoldings((snapshots[0]?.holdings || []).map(({ id, qty, avgPrice }) => ({ id, qty, avgPrice }))); }}>
          {formOpen ? '✕ 취소' : '＋ 새 스냅샷 기록'}
        </button>
      </div>

      {/* 새 스냅샷 입력 폼 */}
      {formOpen && (
        <div className="other-card" style={{ marginBottom: 16, flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
          {generating && (
            <div style={{ position: 'absolute', inset: 0, background: 'white', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', borderRadius: 12, gap: 14 }}>
              <div style={{ width: 38, height: 38, border: '3.5px solid #e2e8f0', borderTopColor: '#2563eb', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
              <div style={{ fontSize: 14, fontWeight: 600, color: '#475569' }}>스냅샷 저장 중...</div>
            </div>
          )}
          {/* 스크롤 가능한 컨텐츠 영역 */}
          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>보유 자산 선택</div>

          {/* 주식 카드 그리드 */}
          <div style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', letterSpacing: 0.5, marginBottom: 3 }}>주식</div>
          <div className="asset-pick-grid" style={{ marginBottom: 6 }}>
            {STOCK_IDS.map(id => {
              const info = ASSET_INFO[id];
              const logo = getLogo(id);
              const sel = addAsset === id;
              return (
                <div key={id} className={`asset-pick-card${sel ? ' selected' : ''}`} onClick={() => { setAddAsset(id); setAddPrice(initPrice(id, prices[id])); }}>
                  <div className="asset-pick-logo">
                    {logo && <img src={logo} alt={info.name} />}
                  </div>
                  <span className="asset-pick-name">{info.name}<span className="asset-pick-label"> · {info.sector}</span></span>
                </div>
              );
            })}
          </div>

          {/* 외화 카드 그리드 */}
          <div style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', letterSpacing: 0.5, marginBottom: 3 }}>외화</div>
          <div className="asset-pick-grid asset-pick-fx" style={{ marginBottom: 8 }}>
            {FX_IDS.map(id => {
              const info = ASSET_INFO[id];
              const flag = getFlag(id);
              const sel = addAsset === id;
              const [code, ...rest] = info.name.split(' ');
              return (
                <div key={id} className={`asset-pick-card${sel ? ' selected' : ''}`} onClick={() => { setAddAsset(id); setAddPrice(initPrice(id, prices[id])); }}>
                  {flag && <img className="asset-pick-flag" src={flag} alt={info.name} />}
                  <span className="asset-pick-name">{code}<span className="asset-pick-label"> · {rest.join(' ')}</span></span>
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
                <div style={{ fontSize: 14, fontWeight: 700, color: '#1e293b' }}>{ASSET_INFO[addAsset]?.name}</div>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{ASSET_INFO[addAsset]?.sector} · {addAsset}</div>
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
              <label className="add-holding-label">평균 매입가 <span style={{ fontWeight: 400, color: '#94a3b8' }}>(현재가 자동 입력 · 수정 가능)</span></label>
              <div style={{ position: 'relative', width: 220 }}>
                <input className="form-input" type="text" inputMode="decimal"
                  placeholder={!pricesLoaded ? '가격 불러오는 중...' : prices[addAsset] ? formatNumberInput(initPrice(addAsset, prices[addAsset])) : '직접 입력'}
                  value={formatNumberInput(addPrice)}
                  onChange={e => setAddPrice(e.target.value.replace(/,/g, ''))}
                  style={{ width: '100%', paddingRight: 34 }} />
                <span style={{ position: 'absolute', right: 11, top: '50%', transform: 'translateY(-50%)', fontSize: 13, fontWeight: 700, color: '#94a3b8', pointerEvents: 'none' }}>원</span>
              </div>
            </div>

            <button className="btn btn-primary" style={{ alignSelf: 'flex-end', height: 36 }} onClick={addHolding}>＋ 추가</button>
          </div>

          {holdings.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 4 }}>
              <thead style={{ position: 'sticky', top: 0, background: 'white', zIndex: 1 }}>
                <tr>
                  {['종목', '수량', '평균 매입가', '현재가', '평가액', '예상 비중', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '5px 8px', fontSize: 11, fontWeight: 700, color: '#94a3b8', borderBottom: '1px solid #f1f5f9' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {holdings.map(h => {
                  const info = ASSET_INFO[h.id] || {};
                  const cur = getPrice(h.id);
                  const curVal = h.qty * cur;
                  const w = formTotalVal > 0 ? curVal / formTotalVal * 100 : 0;
                  const isEditing = editingId === h.id;
                  return (
                    <tr key={h.id}>
                      <td style={{ padding: '7px 8px', borderBottom: '1px solid #f8fafc', textAlign: 'left' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', display: 'inline-block', marginRight: 5, background: info.color || '#94a3b8' }} />
                        {info.name || h.id}
                      </td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>
                        {isEditing
                          ? <input type="number" min="1" value={editQty} onChange={e => setEditQty(e.target.value)} className="form-input" style={{ width: 70, textAlign: 'right', padding: '2px 6px', fontSize: 13 }} />
                          : <>{fmt(h.qty)}{info.unit || ''}</>}
                      </td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>
                        {isEditing
                          ? <input type="text" inputMode="decimal" value={formatNumberInput(editPrice)} onChange={e => setEditPrice(e.target.value.replace(/,/g, ''))} className="form-input" style={{ width: 100, textAlign: 'right', padding: '2px 6px', fontSize: 13 }} />
                          : <>{fmtPrice(h.id, h.avgPrice)}원</>}
                      </td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmtPrice(h.id, cur)}원</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{fmt(curVal)}원</td>
                      <td style={{ textAlign: 'right', padding: '7px 8px', borderBottom: '1px solid #f8fafc' }}>{w.toFixed(1)}%</td>
                      <td style={{ padding: '7px 8px', borderBottom: '1px solid #f8fafc', textAlign: 'center', whiteSpace: 'nowrap' }}>
                        {isEditing ? (
                          <>
                            <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontSize: 15, marginRight: 4 }} onClick={() => {
                              const q = parseFloat(editQty), p = parseNumberInput(editPrice);
                              if (q > 0 && p > 0) setHoldings(prev => prev.map(item => item.id === h.id ? { ...item, qty: q, avgPrice: p } : item));
                              setEditingId(null);
                            }}>✓</button>
                            <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 15 }} onClick={() => setEditingId(null)}>✕</button>
                          </>
                        ) : (
                          <>
                            <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 13, marginRight: 4 }} onClick={() => { setEditingId(h.id); setEditQty(String(h.qty)); setEditPrice(String(h.avgPrice)); }}>✎</button>
                            <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cbd5e1', fontSize: 16 }} onClick={() => removeHolding(h.id)}>×</button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          </div>{/* end 스크롤 영역 */}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, paddingTop: 10, borderTop: '1px solid #f1f5f9', marginTop: 4 }}>
            <button className="btn btn-ghost" style={{ color: '#ef4444', borderColor: '#fca5a5' }} onClick={() => setHoldings([])}>전체 초기화</button>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost" onClick={() => { setFormOpen(false); setHoldings([]); }}>취소</button>
              <button className="btn btn-primary" onClick={saveSnapshot} disabled={generating || holdings.length === 0} style={{ minWidth: 140 }}>
                {generating ? <><span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid rgba(255,255,255,0.4)', borderTopColor: 'white', borderRadius: '50%', animation: 'spin 0.8s linear infinite', verticalAlign: 'middle', marginRight: 6 }} />저장 중...</> : '▶ 스냅샷 저장'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal-box" onClick={e => e.stopPropagation()} style={{ width: 340 }}>
            <div className="modal-title">스냅샷 삭제</div>
            <p style={{ fontSize: 14, color: '#475569', lineHeight: 1.6, marginBottom: 20 }}>
              이 기록을 삭제하면 복구할 수 없습니다.<br />정말 삭제하시겠습니까?
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>취소</button>
              <button className="btn btn-danger" onClick={confirmDelete}>삭제</button>
            </div>
          </div>
        </div>
      )}

      {/* 스냅샷 뷰 — 폼이 열려 있을 때는 숨김 */}
      {!formOpen && (snapshots.length === 0 ? (
        <div className="other-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: 14 }}>
          📋 기록된 스냅샷이 없습니다.<br />
          <span style={{ fontSize: 13, marginTop: 6, display: 'block' }}>위의 버튼을 눌러 포트폴리오를 기록해보세요.</span>
        </div>
      ) : (() => {
        const selectedSnap = snapshots.find(s => s.id === selectedSnapId) ?? snapshots[0];
        return selectedSnap ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <SnapshotCard key={selectedSnap.id} snap={selectedSnap} prices={prices} onDelete={deleteSnapshot} hoveredStockId={hoveredStockId} onHoverStock={setHoveredStockId} />
          </div>
        ) : null;
      })())}
      </div>{/* end 메인 콘텐츠 */}

      {/* 오른쪽 고정 패널: 비중 추이 */}
      <div style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
        <div className="other-card" style={{ flex: 1, overflow: 'hidden', padding: '10px 12px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#475569', marginBottom: 8, flexShrink: 0 }}>
            자산 비중 추이
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <WeightHistoryChart snapshots={snapshots} prices={prices} onSnapClick={id => setSelectedSnapId(id)} selectedSnapId={selectedSnapId} />
          </div>
        </div>
      </div>
    </div>{/* end 2열 wrapper */}
    </>
  );
}
