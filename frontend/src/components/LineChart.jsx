'use client';
import { useState, useEffect, useRef } from 'react';
import { ASSETS } from '@/lib/data';

export const SW = 860, SH = 300, ML = 52, MR = 16, MT = 22, MB = 38;
const CW = SW - ML - MR, CH = SH - MT - MB;

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

export function anomalyColor(count, total) {
  const ratio = count / Math.max(total, 1);
  if (ratio >= 0.6) return { star: '#eab308', border: '#eab308', bg: '#fefce8', text: '#713f12', badge: '#854d0e' };
  if (ratio >= 0.35) return { star: '#fbbf24', border: '#fbbf24', bg: '#fefce8', text: '#92400e', badge: '#a16207' };
  return { star: '#fef08a', border: '#fde047', bg: '#fefce8', text: '#a16207', badge: '#a16207' };
}

const ANOMALY_MAX = { '1W': 2, '1M': 4, '3M': 6, '6M': 10, '1Y': 15, '3Y': 25, 'ALL': 45 };
const ANOMALY_THRESH = id => id === 'USD' ? 0.8 : id === '000000' ? 1.5 : 3.0;

export function computeAnomalies(pd, activeAssets, period) {
  if (!pd?.isoLabels || activeAssets.length < 1) return [];
  const n = pd.isoLabels.length;
  if (n < 2) return [];
  const maxMarkers = ANOMALY_MAX[period] ?? 5;
  const candidates = [];
  for (let i = 1; i < n; i++) {
    const movers = [];
    for (const a of activeAssets) {
      const c = pd.closes?.[a];
      if (!c || c[i] == null || c[i - 1] == null) continue;
      const chg = (c[i] - c[i - 1]) / c[i - 1] * 100;
      if (Math.abs(chg) >= ANOMALY_THRESH(a)) movers.push({ id: a, chg });
    }
    if (movers.length >= 1) {
      const totalAbs = movers.reduce((s, m) => s + Math.abs(m.chg), 0);
      candidates.push({ idx: i, isoDate: pd.isoLabels[i], displayDate: pd.labels[i], movers, score: movers.length, totalAbs, totalAssets: activeAssets.length });
    }
  }
  candidates.sort((a, b) => b.score - a.score || b.totalAbs - a.totalAbs);
  const minGap = Math.max(2, Math.floor(n / (maxMarkers * 3)));
  const selected = [];
  for (const c of candidates) {
    if (selected.length >= maxMarkers) break;
    if (!selected.some(s => Math.abs(s.idx - c.idx) < minGap)) selected.push(c);
  }
  return selected.sort((a, b) => a.idx - b.idx);
}

export function findNewsForDate(newsArr, isoDate) {
  if (!newsArr?.length || !isoDate) return null;
  return newsArr.find(n => n.start_date <= isoDate && isoDate <= n.end_date) ?? null;
}

export default function LineChart({ activeAssets, pd, hoveredAsset, onHoverAsset, anomalies, onAnomalyHover, onAnomalyLeave, onAnomalyClick, showAssetName = true }) {
  const [tooltip, setTooltip] = useState(null);
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const svgRef = useRef(null);
  const [starYScale, setStarYScale] = useState(1);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setStarYScale((width / SW) / (height / SH));
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  if (!pd || activeAssets.length === 0) return null;
  const n = pd.labels.length;

  let allV = [0];
  activeAssets.forEach(a => { if (pd.d[a]) allV.push(...pd.d[a].filter(v => v !== null)); });
  let minV = Math.min(...allV), maxV = Math.max(...allV);
  const pad = Math.max((maxV - minV) * 0.12, 3);
  const lineAssets = [
    ...activeAssets.filter(id => id !== '000000' && id !== 'USD'),
    ...activeAssets.filter(id => id === '000000'),
    ...activeAssets.filter(id => id === 'USD'),
  ];
  minV -= pad; maxV += pad;

  const ticks = niceTicks(minV, maxV, 6);
  const step = Math.max(1, Math.ceil(n / 4));
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
      isFx: a === 'USD',
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
        zIndex: 9999, pointerEvents: 'none', minWidth: 200,
      }}>
        {showAssetName && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: tooltip.color, flexShrink: 0, display: 'inline-block' }} />
            <span style={{ fontWeight: 700, fontSize: 16, color: '#1e293b' }}>{tooltip.name}</span>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 14, marginBottom: 4 }}>
          <span style={{ color: '#94a3b8' }}>날짜</span>
          <span style={{ fontWeight: 600, color: '#374151' }}>{tooltip.date}</span>
        </div>
        {tooltip.close != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 14, marginBottom: 4 }}>
            <span style={{ color: '#94a3b8' }}>{tooltip.isFx ? '환율' : '주가'}</span>
            <span style={{ fontWeight: 700, color: '#1e293b' }}>
              {tooltip.isFx
                ? tooltip.close.toLocaleString('ko-KR', { maximumFractionDigits: 2 })
                : `${Number(tooltip.close).toLocaleString('ko-KR')}원`}
            </span>
          </div>
        )}
        {tooltip.dailyChgPct != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 14, marginBottom: 4 }}>
            <span style={{ color: '#94a3b8' }}>전일 대비</span>
            <span style={{ fontWeight: 700, color: tooltip.dailyChgPct >= 0 ? '#dc2626' : '#2563eb' }}>
              {tooltip.dailyChgPct >= 0 ? '▲' : '▼'} {Math.abs(tooltip.dailyChgPct).toFixed(2)}%
            </span>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 14 }}>
          <span style={{ color: '#94a3b8' }}>기간 변동률</span>
          <span style={{ fontWeight: 700, color: tooltip.periodVal >= 0 ? '#dc2626' : '#2563eb' }}>
            {tooltip.periodVal >= 0 ? '+' : ''}{Number(tooltip.periodVal).toFixed(2)}%
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
              stroke={isZero ? '#94a3b8' : '#f1f5f9'} strokeWidth={1} />
            <text x={ML - 5} y={(y + 4).toFixed(1)} textAnchor="end" fontSize={13}
              style={{ transformBox: 'fill-box', transformOrigin: 'center', transform: 'scaleY(0.75)' }}
              fill="#64748b" fontWeight={isZero ? 600 : 400}>{label}</text>
          </g>
        );
      })}

      {/* x축 라벨 */}
      {xLabelIndices.map(i => (
        <text key={i} x={toX(i, n).toFixed(1)} y={(MT + CH + 27).toFixed(1)}
          textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} fontSize={13} fill="#64748b"
          style={{ transformBox: 'fill-box', transformOrigin: 'center', transform: 'scaleY(0.75)' }}>{pd.labels[i]}</text>
      ))}

      {/* anomaly markers */}
      {anomalies?.map(a => {
        const x = toX(a.idx, n);
        const cy = MT + CH + 9;
        const starColor = anomalyColor(a.movers.length, a.totalAssets).star;
        return (
          <g key={a.idx} style={{ cursor: 'pointer' }}
            onMouseEnter={e => onAnomalyHover?.(a, e.clientX, e.clientY)}
            onMouseLeave={onAnomalyLeave}
            onClick={e => { e.stopPropagation(); onAnomalyClick?.(a, e.clientX, e.clientY); }}>
            <circle cx={x.toFixed(1)} cy={cy} r={10} fill="transparent" />
            <text x={x.toFixed(1)} y={cy + 5} textAnchor="middle" fontSize={12}
              fill={starColor} pointerEvents="none" style={{ userSelect: 'none' }}
              transform={`translate(${x.toFixed(1)},${cy}) scale(1,${starYScale.toFixed(4)}) translate(${(-x).toFixed(1)},${(-cy)})`}>★</text>
          </g>
        );
      })}

      {/* crosshair */}
      {hoveredIdx !== null && (
        <line
          x1={toX(hoveredIdx, n).toFixed(1)} y1={MT}
          x2={toX(hoveredIdx, n).toFixed(1)} y2={MT + CH}
          stroke="#cbd5e1" strokeWidth={1} strokeDasharray="3,3" pointerEvents="none"
        />
      )}

      {/* 라인 */}
      {lineAssets.map(a => {
        const vals = pd.d[a];
        if (!vals) return null;
        const col = ASSETS[a].color;
        const isFx = a === 'USD';
        const isKospi = a === '000000';
        const isDimmed = hoveredAsset !== null && hoveredAsset !== a;
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
        return (
          <g key={a} style={{ opacity: isDimmed ? 0.15 : 1, transition: 'opacity 0.2s' }}>
            {segments.map((pts, si) => (
              <polyline key={si} points={pts.join(' ')} fill="none" stroke={col}
                strokeLinejoin="round" strokeLinecap="round" strokeWidth={strokeWidth} />
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
