'use client';
import { useState, useEffect, useRef } from 'react';
import { fetchWithAuth } from '@/lib/auth';
import { ASSETS, EXCHANGE_PAIRS, fetchAssetData, buildPeriodData } from '@/lib/data';
import { STOCK_CONFIG } from '@/components/StockDetailModal';

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
            <span style={{ fontWeight: 700, color: tooltip.dailyChgPct >= 0 ? '#dc2626' : '#2563eb' }}>
              {tooltip.dailyChgPct >= 0 ? '▲' : '▼'} {Math.abs(tooltip.dailyChgPct).toFixed(2)}%
            </span>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, fontSize: 13 }}>
          <span style={{ color: '#94a3b8' }}>기간 변동률</span>
          <span style={{ fontWeight: 700, color: tooltip.periodVal >= 0 ? '#dc2626' : '#2563eb' }}>
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

const CORR_PAIR_DESCRIPTIONS = {
  'semiconductor:semiconductor': {
    pos: 'AI 서버·HBM 수요 급증으로 동일한 반도체 업황 사이클에 노출되어 동반 등락',
    neg: '메모리 시장 점유율 경쟁 심화로 이익률 방향이 엇갈려 역행',
  },
  'auto:auto': {
    pos: '현대차그룹 완성차 계열사로 북미 수출 호조와 원/달러 환율 영향을 함께 반영',
    neg: '차종 구성 및 생산 일정 차이로 분기 실적이 엇갈리는 구간 발생',
  },
  'defense:defense': {
    pos: 'K-방산 수출 수주 모멘텀과 국방예산 증액 기대를 동일하게 공유하며 동반 상승',
    neg: '수주 경쟁 및 사업 부문 구성 차이로 수익성 방향이 다르게 나타남',
  },
  'finance:finance': {
    pos: '기준금리 변화와 NIM 방향성에 국내 대형 시중은행이 동시에 반응',
    neg: '대출 포트폴리오·충당금 적립 차이로 실적 방향이 상이하게 나타남',
  },
  'chemical:chemical': {
    pos: '국제 납사 가격과 배터리 소재 수요 변화가 동시에 영향을 미쳐 함께 움직임',
    neg: '석유화학 vs 배터리 소재 사업 비중 차이로 유가 수혜 방향이 엇갈림',
  },
  'auto:semiconductor': {
    pos: '글로벌 경기 회복 기대에 국내 수출 대형주가 함께 강세를 보임',
    neg: '전기차 가속 시 반도체 수혜 증가, 완성차 전환 비용 증가로 방향이 엇갈림',
  },
  'defense:semiconductor': {
    pos: '지정학 리스크 고조·기술 안보 투자 확대에 반도체·방산 동반 매수세 유입',
    neg: '방산 예산 확대가 IT 민수 설비 투자 위축을 동반하는 국면에서 역행',
  },
  'finance:semiconductor': {
    pos: 'KOSPI 대형주 동반 강세 장세에서 반도체·금융주가 함께 상승',
    neg: '금리 인상 구간에서 반도체(성장주) 하락, 은행은 NIM 확대로 강세 역행',
  },
  'chemical:semiconductor': {
    pos: '글로벌 제조업 PMI 개선 기대에 소재·IT 대형주 동반 매수세 유입',
    neg: '에너지 비용 상승이 화학 마진을 압박하는 반면 반도체는 수요 호조로 상반',
  },
  'auto:defense': {
    pos: '경기 회복·정부 지출 확대 기대에 수출·방산 종목이 동반 상승',
    neg: '원자재 비용 변동 방향이 달라 수익성 기대치가 다르게 나타남',
  },
  'auto:finance': {
    pos: '국내 경기 회복 기대에 소비·금융 관련 대형주가 동반 강세를 보임',
    neg: '금리 인상이 자동차 할부 수요를 억제하는 반면 은행은 NIM 개선으로 역행',
  },
  'auto:chemical': {
    pos: '전기차 전환 가속으로 배터리 화학과 완성차가 동반 수혜를 기대',
    neg: '유가 상승 시 화학 원재료 부담 증가 vs 완성차 연비 수요로 방향이 상충',
  },
  'defense:finance': {
    pos: '지정학 리스크 대응 수요·안정 배당 기대에 방산·금융주 동반 매수',
    neg: '금리 급등기에 방산 성장주 밸류에이션 하락 vs 은행 NIM 개선이 상충',
  },
  'chemical:defense': {
    pos: '글로벌 공급망 재편 수혜 기대로 방산·소재 종목이 동반 모멘텀을 받음',
    neg: '유가 급등이 화학 마진을 압박하는 반면 방산 수주는 무관하여 역행',
  },
  'chemical:finance': {
    pos: '경기 민감 업종 동반 강세 장세에서 화학·금융주가 함께 상승',
    neg: '유가 상승 시 화학 원가 압박 우려 vs 은행 NIM 개선 기대로 방향이 엇갈림',
  },
  'eur:semiconductor': {
    pos: '글로벌 경기 회복 기대에 유로 강세와 반도체 수출 수요 증가가 동반 반영',
    neg: '유로 약세(유럽 경기 부진)가 반도체 유럽향 수요에 부정적으로 작용',
  },
  'auto:eur': {
    pos: '유로 강세가 유럽 수출 차량의 원화 환산 이익을 높여 동반 상승',
    neg: '유로 약세(유럽 소비 둔화)와 국내 완성차 유럽 판매 감소가 동반',
  },
  'eur:finance': {
    pos: '유럽 금리 인상 사이클이 국내 채권 금리 상승을 유도하며 동반 강세',
    neg: '유로존 불안 시 금융 리스크 프리미엄이 높아지며 국내 은행주 약세',
  },
  'defense:eur': {
    pos: '유럽 방위비 증액 기대와 K-방산 수출 호조가 동반 강세로 반영',
    neg: '유로 약세(유럽 재정 우려)로 방산 수출 원화 환산 수익이 감소',
  },
  'chemical:eur': {
    pos: '유럽 제조업 회복과 국내 화학 수출 수요 증가가 동반 반영',
    neg: '유로 약세가 화학 수출 마진을 압박하며 동반 약세',
  },
  'semiconductor:usd': {
    pos: '달러 강세로 반도체 수출 원화 환산 실적이 개선되며 동반 상승',
    neg: '달러 약세(글로벌 위험선호)와 반도체 수요 기대가 상충하는 구간',
  },
  'auto:usd': {
    pos: '달러 강세가 미국 수출 차량의 원화 환산 이익을 높여 동반 상승',
    neg: '달러 약세 시 수출 자동차 마진 압박과 원화 강세가 동반',
  },
  'finance:usd': {
    pos: '달러 강세 구간에서 외화 자산 평가이익이 금융사 실적에 우호적으로 반영',
    neg: '달러 약세(글로벌 위험선호)와 금융주 강세가 방향 상충',
  },
  'defense:usd': {
    pos: '달러 강세 구간에서 방산 수출 계약의 원화 환산 이익 증가',
    neg: '달러 약세(지정학 긴장 완화)와 방산 수요 기대 약화가 동반',
  },
  'chemical:usd': {
    pos: '달러 강세 시 수출 화학 제품의 원화 환산 수익이 개선되어 동반',
    neg: '달러 강세로 납사·원자재 달러 비용이 늘어나 화학 마진 압박',
  },
  'jpy:semiconductor': {
    pos: '엔화 약세로 일본 반도체 경쟁사의 가격 경쟁력이 약화되어 국내 반사 수혜',
    neg: '엔화 강세(안전자산 선호)와 반도체 업황 위축이 동시에 나타남',
  },
  'auto:jpy': {
    pos: '엔화 약세로 일본 완성차의 수출 경쟁력이 약화되어 현대·기아 반사 수혜',
    neg: '엔화 강세(글로벌 리스크 오프)와 자동차 수요 위축이 동반',
  },
  'cny:semiconductor': {
    pos: '위안화 강세(중국 경기 회복)가 반도체 최대 수출국 수요 개선과 동반',
    neg: '위안화 약세(중국 경기 부진)와 반도체 대중 수출 감소가 동반',
  },
  'auto:cny': {
    pos: '위안화 강세(중국 소비 회복)가 국내 완성차 중국 판매 수요 개선과 동반',
    neg: '위안화 약세와 중국 내수 부진으로 완성차 중국 판매 감소가 동반',
  },
  'index:semiconductor': {
    pos: 'KOSPI 시총 1·2위 반도체 대형주가 지수 방향을 주도하며 함께 상승',
    neg: '반도체 업황 부진이 KOSPI 지수 하락을 견인하는 국면',
  },
  'auto:index': {
    pos: '완성차 수출 호조가 KOSPI 지수 방향과 동반 상승',
    neg: '자동차 섹터 부진이 KOSPI 지수와 역행하는 국면',
  },
  'finance:index': {
    pos: '시중은행 대형주의 NIM 수혜가 KOSPI 지수와 동반 상승',
    neg: '금융 섹터 부진이 KOSPI 지수와 역행하는 국면',
  },
};

function getPairDesc(idA, idB, isPos, absR) {
  const SECTOR = {
    '005930': 'semiconductor', '000660': 'semiconductor',
    '005380': 'auto',          '000270': 'auto',
    '079550': 'defense',       '012450': 'defense',
    '105560': 'finance',       '055550': 'finance',
    '051910': 'chemical',      '096770': 'chemical',
    '000000': 'index',
    'KRW/USD': 'usd', 'KRW/EUR': 'eur',
    'KRW/JPY': 'jpy', 'KRW/CNY': 'cny',
    'KRW/CHF': 'chf', 'KRW/GBP': 'gbp',
  };
  const typeA = SECTOR[idA] ?? 'other';
  const typeB = SECTOR[idB] ?? 'other';
  const key = [typeA, typeB].sort().join(':');
  const entry = CORR_PAIR_DESCRIPTIONS[key];
  if (!entry) {
    const intensity = absR >= 0.7 ? '강하게' : absR >= 0.3 ? '중간 정도로' : '약하게';
    return isPos ? `${intensity} 같은 방향으로 움직이는 경향` : `${intensity} 반대 방향으로 움직이는 경향`;
  }
  return isPos ? entry.pos : entry.neg;
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
  const [complexData, setComplexData] = useState({});
  const [rightOpen, setRightOpen] = useState(false);
  const [newsDrawerOpen, setNewsDrawerOpen] = useState(false);
  const [selectedStockId, setSelectedStockId] = useState(null);
  const [selectedFxId, setSelectedFxId] = useState(null);
  const [favDetail, setFavDetail] = useState(null);
  const [favDetailLoading, setFavDetailLoading] = useState(false);
  const [favNewsExpanded, setFavNewsExpanded] = useState(null);
  const [showMatrix, setShowMatrix] = useState(false);
  const [expandedPairKey, setExpandedPairKey] = useState(null);
  const matrixColRef = useRef(null);
  const [panelWidth, setPanelWidth] = useState(400);
  const [matrixColWidth, setMatrixColWidth] = useState(250);
  const PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', 'ALL'];

  useEffect(() => {
    const update = () => {
      if (matrixColRef.current) {
        const rect = matrixColRef.current.getBoundingClientRect();
        setPanelWidth(window.innerWidth - rect.left);
        setMatrixColWidth(rect.width);
      }
    };
    update();
    const ro = new ResizeObserver(update);
    if (matrixColRef.current) ro.observe(matrixColRef.current);
    window.addEventListener('resize', update);
    return () => { ro.disconnect(); window.removeEventListener('resize', update); };
  }, []);

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
      if (firstStock) setSelectedStockId(firstStock);
    });
    loadLatestPrices();
    loadLatestRates();
  }, []);

  useEffect(() => {
    if (selectedStockId) loadFavDetail(selectedStockId);
  }, [selectedStockId]);

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
    const absT = Math.abs(t);
    const sign = t >= 0 ? 1 : -1;
    // 비-대각선 셀은 최소 13% 색 강도 보장 → 0.01도 연한 틴트로 표시
    const intensity = absT > 0 ? Math.max(0.13, absT) : 0;
    const sc = sign * intensity;
    const nr = 245, ng = 247, nb = 250;
    let r, g, b;
    if (sc >= 0) {
      r = Math.round(nr + (30 - nr) * sc); g = Math.round(ng + (64 - ng) * sc); b = Math.round(nb + (175 - nb) * sc);
    } else {
      const u = -sc;
      r = Math.round(nr + (185 - nr) * u); g = Math.round(ng + (28 - ng) * u); b = Math.round(nb + (28 - nb) * u);
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

  function selectStock(id) {
    setActiveAssets(prev => prev.includes(id) ? prev : [...prev, id]);
    setSelectedStockId(id);
    setSelectedFxId(null);
  }

  function selectFx(id) {
    setActiveAssets(prev => prev.includes(id) ? prev : [...prev, id]);
    setSelectedFxId(id);
    setSelectedStockId(null);
  }

  async function toggleAsset(id) {
    setActiveAssets(prev => {
      if (prev.includes(id)) {
        const next = prev.filter(a => a !== id);
        // 제거된 종목이 현재 선택된 상세 종목이면 다른 주식으로 전환
        if (id === selectedStockId) {
          const nextStock = next.find(a => STOCK_CONFIG[a]);
          setSelectedStockId(nextStock ?? null);
        }
        return next;
      } else {
        // 추가 시 상세 패널에 종목이 없으면 자동 선택
        if (!selectedStockId && STOCK_CONFIG[id]) setSelectedStockId(id);
        return [...prev, id];
      }
    });
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
              onClick={e => { e.stopPropagation(); selectStock(id); }}
              title="대시보드에서 상세 보기"
            >상세</button>
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
          <div className="tk-card-acts">
            <button
              className={`tk-card-star${starred ? ' starred' : ''}`}
              onClick={e => toggleFav(id, e)}
            >{starred ? '★' : '☆'}</button>
            <button
              className="tk-card-det"
              onClick={e => { e.stopPropagation(); selectFx(id); }}
              title="대시보드에서 상세 보기"
            >상세</button>
          </div>
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

  const cfg = selectedStockId ? STOCK_CONFIG[selectedStockId] : null;
  const s = favDetail?.stats;
  const chgPct = favDetail?.changePct;
  const chgAmt = favDetail?.change;
  const chgColor = (chgPct ?? 0) >= 0 ? '#dc2626' : '#2563eb';
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
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      <NewsDrawer open={newsDrawerOpen} onClose={() => setNewsDrawerOpen(false)} />
      {showMatrix && showComplex && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          onClick={() => setShowMatrix(false)}
        >
          <div
            style={{ background: 'white', borderRadius: 16, padding: '20px 24px 24px', boxShadow: '0 20px 60px rgba(15,23,42,0.3)', maxWidth: '92vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}
          >
            {/* 헤더 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexShrink: 0 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 800, color: '#1e293b' }}>상관계수 히트맵</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>Pearson · {complexIds.length}개 종목</div>
              </div>
              <button
                onClick={() => setShowMatrix(false)}
                style={{ width: 28, height: 28, borderRadius: '50%', border: '1px solid #e2e8f0', background: '#f8fafc', cursor: 'pointer', fontSize: 13, color: '#64748b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >✕</button>
            </div>

            {/* 테이블 */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              {(() => {
                const n = complexIds.length;
                const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
                const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
                // 셀 크기: 뷰포트 기준 계산 + 최대 70px 상한 (종목 수 적어도 너무 커지지 않게)
                const cellH = Math.max(22, Math.min(70, Math.floor((vh * 0.90 - 178 - n * 3) / n)));
                const cellW = Math.max(44, Math.min(96, Math.floor((vw * 0.88 - 110 - n * 3) / n)));
                const minDim = Math.min(cellW, cellH);
                // 셀이 클수록 글자도 크게
                const fs = minDim >= 60 ? 17 : minDim >= 50 ? 15 : minDim >= 40 ? 13 : 11;
                const lbl = id => { const l = shortLabel(id); return cellW < 54 ? l.slice(0, 3) : l; };
                return (
                  <table style={{ borderCollapse: 'separate', borderSpacing: 3 }}>
                    <thead><tr>
                      <th style={{ minWidth: 60 }} />
                      {complexIds.map(id => (
                        <th key={id} style={{ width: cellW, fontSize: fs - 1, fontWeight: 600, color: '#475569', textAlign: 'center', padding: '0 2px 8px', whiteSpace: 'nowrap' }}>
                          {lbl(id)}
                        </th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {complexIds.map(row => (
                        <tr key={row}>
                          <th style={{ fontSize: fs - 1, fontWeight: 600, color: '#475569', textAlign: 'right', paddingRight: 8, whiteSpace: 'nowrap' }}>
                            {lbl(row)}
                          </th>
                          {complexIds.map(col => {
                            if (row === col) return (
                              <td key={col} style={{ width: cellW, height: cellH, background: '#f1f5f9', borderRadius: 6, textAlign: 'center', verticalAlign: 'middle' }}>
                                <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#cbd5e1', margin: '0 auto' }} />
                              </td>
                            );
                            const v = calcPearson(complexData[row], complexData[col]);
                            const { background, color } = corrStyle(v);
                            return (
                              <td key={col} style={{ width: cellW, height: cellH, background, borderRadius: 6, textAlign: 'center', verticalAlign: 'middle', color, fontWeight: 700, fontSize: fs }}>
                                {v.toFixed(2)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              })()}
            </div>

            {/* 컬러 스케일 (고정) */}
            <div style={{ flexShrink: 0, marginTop: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#94a3b8' }}>
                <span>-1.0</span>
                <div style={{ flex: 1, height: 7, borderRadius: 4, background: 'linear-gradient(to right,rgb(185,28,28),rgb(248,250,252),rgb(30,64,175))' }} />
                <span>+1.0</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontWeight: 600, color: '#475569', marginTop: 5, padding: '0 24px' }}>
                <span>강한 음의 상관관계</span>
                <span>강한 양의 상관관계</span>
              </div>
            </div>
          </div>
        </div>
      )}
      <div className={`dash-layout${rightOpen ? ' panel-open' : ''}`}>

        <div className="left-wrapper">
          <div className="chart-controls">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginRight: 4 }}>기간</div>
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'white', border: '1px solid var(--border)', borderRadius: 8, padding: '4px 10px' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8', flexShrink: 0 }}>즐겨찾기</span>
              <div className="active-chips" style={{ margin: 0, padding: 0 }}>
                {[...favs].filter(id => ASSETS[id]).map(id => {
                  const isSelected = id === selectedStockId;
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
                      onClick={() => setSelectedStockId(id)}
                    >
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: isSelected ? 'white' : color, display: 'inline-block' }} />
                      {ASSETS[id].label}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', flex: 1, gap: 14, minHeight: 0 }}>
        {/* LEFT: Chart */}
        <div className="chart-panel">

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
                      const col = last >= 0 ? '#dc2626' : '#2563eb';
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
          </div>
        </div>

        {/* 종목/환율 상세 패널 */}
        <div className="ai-main-panel">
          <div className="ai-main-card" style={{ flex: 1, overflowY: 'auto' }}>
            {/* ── 환율 상세 ── */}
            {selectedFxId ? (() => {
              const fxInfo = FX_INFO[selectedFxId];
              const fxPrice = prices[selectedFxId];
              const fxChgPct = fxPrice?.change_pct;
              const fxChgAmt = fxPrice?.change;
              const fxChgColor = (fxChgPct ?? 0) >= 0 ? '#dc2626' : '#2563eb';
              const fxChgArrow = (fxChgPct ?? 0) >= 0 ? '▲' : '▼';
              const currency = selectedFxId.split('/')[1];
              return (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <img src={fxInfo.flag} alt={currency} style={{ width: 32, height: 22, borderRadius: 4, objectFit: 'cover', border: '1px solid #e8ecf0', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 800, color: '#1e293b' }}>{fxInfo.desc} <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>{currency}</span></div>
                      <div style={{ fontSize: 10, color: '#94a3b8' }}>{selectedFxId} · 원화 기준</div>
                    </div>
                    {fxPrice ? (
                      <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                        <div style={{ fontSize: 15, fontWeight: 800 }}>{Number(fxPrice.price).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}<span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>원</span></div>
                        {fxChgPct != null && (
                          <div style={{ fontSize: 11, fontWeight: 600, color: fxChgColor }}>{fxChgArrow} {fxChgAmt != null ? Math.abs(fxChgAmt).toFixed(2) : ''} ({Math.abs(fxChgPct).toFixed(2)}%)</div>
                        )}
                      </div>
                    ) : (
                      <div style={{ marginLeft: 'auto' }}>
                        <span className="skeleton" style={{ width: 80, height: 18, display: 'block', marginBottom: 5 }} />
                        <span className="skeleton" style={{ width: 60, height: 13, display: 'block' }} />
                      </div>
                    )}
                  </div>
                  <div style={{ borderTop: '1px solid #f1f5f9', marginBottom: 8 }} />
                  <div className="ai-main-title" style={{ marginBottom: 6 }}>환율 정보</div>
                  <div className="grid g11" style={{ gap: 5 }}>
                    {[
                      { label: '현재 환율', value: fxPrice ? `${Number(fxPrice.price).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}원` : '—' },
                      { label: '전일 대비', value: fxChgAmt != null ? `${fxChgAmt >= 0 ? '+' : ''}${fxChgAmt.toFixed(2)}` : '—', color: fxChgAmt != null ? fxChgColor : undefined },
                      { label: '변동률', value: fxChgPct != null ? `${fxChgPct >= 0 ? '+' : ''}${fxChgPct.toFixed(2)}%` : '—', color: fxChgPct != null ? fxChgColor : undefined },
                      { label: '기준통화', value: 'KRW (원화)' },
                      { label: '대상통화', value: currency },
                      { label: '통화권', value: fxInfo.desc },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                        <div className="metric-label">{label}</div>
                        <div className="metric-value" style={{ whiteSpace: 'nowrap', ...(color ? { color } : {}) }}>{value}</div>
                      </div>
                    ))}
                  </div>
                </>
              );
            })() : (
            /* ── 주식 상세 ── */
            <>
            {cfg && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 7, background: '#fff', border: '1px solid #e8ecf0', padding: 3, overflow: 'hidden', flexShrink: 0 }}>
                    <img src={cfg.logoSrc ?? `/assets/logos/${cfg.logo}`} alt={cfg.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: '#1e293b' }}>{cfg.name} <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>{selectedStockId}</span></div>
                    <div style={{ fontSize: 10, color: '#94a3b8' }}>{cfg.meta}</div>
                  </div>
                  {favDetailLoading ? (
                    <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                      <span className="skeleton" style={{ width: 90, height: 18, display: 'block', marginBottom: 5 }} />
                      <span className="skeleton" style={{ width: 70, height: 13, display: 'block' }} />
                    </div>
                  ) : favDetail?.price ? (
                    <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                      <div style={{ fontSize: 15, fontWeight: 800 }}>{Number(favDetail.price).toLocaleString('ko-KR')}<span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 400 }}>원</span></div>
                      {chgPct != null && (
                        <div style={{ fontSize: 11, fontWeight: 600, color: chgColor }}>{chgArrow} {chgAmt != null ? `${fmt(Math.abs(chgAmt))}원` : ''} ({Math.abs(chgPct).toFixed(2)}%)</div>
                      )}
                    </div>
                  ) : null}
                </div>
                <div style={{ borderTop: '1px solid #f1f5f9', marginBottom: 8 }} />
              </>
            )}
            <div className="ai-main-title" style={{ marginBottom: 6 }}>주요 지표</div>
            {favDetailLoading ? (
              <div className="grid g11" style={{ gap: 5 }}>
                {['거래량', '시가총액', '52주 최고', '52주 최저', 'PER', 'PBR'].map(label => (
                  <div key={label} className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div className="metric-label">{label}</div>
                    <span className="skeleton" style={{ width: '65%', height: 18, marginTop: 5 }} />
                  </div>
                ))}
              </div>
            ) : !cfg ? (
              <div style={{ color: '#94a3b8', fontSize: 12, textAlign: 'center', padding: '8px 0' }}>관심종목을 선택해주세요</div>
            ) : (
              <>
                <div className="grid g11" style={{ gap: 5, flex: 1, alignContent: 'stretch' }}>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">거래량</div><div className="metric-value">{fmtVol(s?.volume)}</div></div>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">시가총액</div><div className="metric-value" style={{ whiteSpace: 'nowrap' }}>{fmtCap(s?.market_cap)}</div></div>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">52주 최고</div><div className="metric-value" style={{ whiteSpace: 'nowrap', color: '#dc2626' }}>{s?.high52 ? `${fmt(s.high52)}원` : '—'}</div></div>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">52주 최저</div><div className="metric-value" style={{ whiteSpace: 'nowrap', color: '#2563eb' }}>{s?.low52 ? `${fmt(s.low52)}원` : '—'}</div></div>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">PER</div><div className="metric-value">{s?.per != null ? <>{s.per.toFixed(2)}<span style={{ fontSize: 10, fontWeight: 400 }}>배</span></> : <span style={{ fontSize: 12, color: '#94a3b8' }}>적자</span>}</div></div>
                  <div className="metric-box" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div className="metric-label">PBR</div><div className="metric-value">{s?.pbr != null ? <>{s.pbr.toFixed(2)}<span style={{ fontSize: 10, fontWeight: 400 }}>배</span></> : '—'}</div></div>
                </div>

                {/* 52주 가격 위치 바 */}
                {s?.high52 && s?.low52 && favDetail?.price && (() => {
                  const price = Number(favDetail.price);
                  const range = s.high52 - s.low52;
                  const pct = range > 0 ? Math.round(((price - s.low52) / range) * 100) : 50;
                  const safePct = Math.max(0, Math.min(100, pct));
                  return (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 600, color: '#64748b', marginBottom: 3 }}>52주 가격 위치</div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#94a3b8', marginBottom: 3 }}>
                        <span>최저 {fmt(s.low52)}원</span>
                        <span>최고 {fmt(s.high52)}원</span>
                      </div>
                      <div style={{ position: 'relative', height: 6, borderRadius: 3, background: 'linear-gradient(to right, #2563eb, #dc2626)' }}>
                        <div style={{ position: 'absolute', top: '50%', left: `${safePct}%`, transform: 'translate(-50%, -50%)', width: 11, height: 11, borderRadius: '50%', background: safePct >= 50 ? '#dc2626' : '#2563eb', border: '2px solid white', boxShadow: '0 1px 4px rgba(0,0,0,0.25)' }} />
                      </div>
                      <div style={{ position: 'relative', marginTop: 4, height: 13 }}>
                        <span style={{ position: 'absolute', left: `${Math.min(Math.max(safePct, 6), 94)}%`, transform: 'translateX(-50%)', fontSize: 9, fontWeight: 700, color: safePct >= 50 ? '#dc2626' : '#2563eb', whiteSpace: 'nowrap' }}>{safePct}%</span>
                      </div>
                    </div>
                  );
                })()}

                {/* PER 업종 평균 비교
                    출처: KRX 업종별 PER (한국거래소 정보데이터시스템 · fnguide.com)
                    기준: 2026년 1분기 (분기 실적 시즌마다 수동 업데이트)
                    업데이트 방법: https://data.krx.co.kr → 주식 → 업종 → 업종PER/PBR
                */}
                {s?.per != null && cfg?.sector && (() => {
                  const SECTOR_PER = {
                    '반도체': 23,  // KRX IT지수 구성종목 평균, 2026 Q1
                    '자동차': 7,   // KRX 자동차지수 구성종목 평균, 2026 Q1
                    '방산':   28,  // KRX 방산지수 구성종목 평균, 2026 Q1
                    '금융':   8,   // KRX 은행지수 구성종목 평균, 2026 Q1
                    '화학':   16,  // KRX 화학지수 구성종목 평균, 2026 Q1
                  };
                  const avg = SECTOR_PER[cfg.sector];
                  if (!avg) return null;
                  const diff = s.per - avg;
                  const isAbove = diff > 0;
                  const diffColor = isAbove ? '#dc2626' : '#2563eb';
                  return (
                    <div style={{ marginTop: 8, padding: '7px 10px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                        <span style={{ fontSize: 10, fontWeight: 600, color: '#64748b' }}>PER 업종 평균 비교</span>
                        <span style={{ fontSize: 8, color: '#cbd5e1' }}>KRX · 2026 Q1</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <div style={{ flex: 1, textAlign: 'center' }}>
                          <div style={{ fontSize: 9, fontWeight: 600, color: '#64748b', marginBottom: 2 }}>PER</div>
                          <div style={{ fontSize: 15, fontWeight: 800, color: diffColor, lineHeight: 1 }}>{s.per.toFixed(1)}<span style={{ fontSize: 10, fontWeight: 600 }}>배</span></div>
                        </div>
                        <div style={{ width: 1, height: 28, background: '#e2e8f0', flexShrink: 0 }} />
                        <div style={{ flex: 1, textAlign: 'center' }}>
                          <div style={{ fontSize: 9, fontWeight: 600, color: '#64748b', marginBottom: 2 }}>{cfg.sector} 업종 평균</div>
                          <div style={{ fontSize: 15, fontWeight: 800, color: '#334155', lineHeight: 1 }}>{avg}<span style={{ fontSize: 10, fontWeight: 600 }}>배</span></div>
                        </div>
                      </div>
                      <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: diffColor }}>{isAbove ? '▲' : '▼'} {isAbove ? '+' : ''}{diff.toFixed(1)}배</span>
                        <span style={{ fontSize: 9, fontWeight: 500, color: '#64748b' }}>업종 평균 대비 {isAbove ? '높음' : '낮음'}</span>
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
            </>
            )}
          </div>
        </div>
          </div>
          {cfg && !selectedFxId && (
            <div className="ai-main-card">
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

        {/* MATRIX column */}
        <div className="matrix-col" ref={matrixColRef}>
          {showComplex ? (() => {
            const allPairs = [];
            for (let i = 0; i < complexIds.length; i++)
              for (let j = i + 1; j < complexIds.length; j++) {
                const v = calcPearson(complexData[complexIds[i]], complexData[complexIds[j]]);
                allPairs.push({ a: complexIds[i], b: complexIds[j], v });
              }
            function corrColor(v) {
              const a = Math.abs(v);
              if (a >= 0.7) return v > 0 ? '#1e3a8a' : '#7f1d1d';
              if (a >= 0.3) return v > 0 ? '#2563eb' : '#dc2626';
              return '#94a3b8';
            }
            const isTiny = complexIds.length <= 3;
            const isCompact = complexIds.length === 4;
            const pairCount = isCompact ? 3 : 5;
            const sortedDesc = [...allPairs].sort((a, b) => b.v - a.v);
            const topPairs = sortedDesc.slice(0, pairCount);
            const topKeys = new Set(topPairs.map(p => `${p.a}|${p.b}`));
            const bottomPairs = [...sortedDesc].reverse().filter(p => !topKeys.has(`${p.a}|${p.b}`)).slice(0, pairCount);
            const globalMaxAbs = Math.max(...allPairs.map(p => Math.abs(p.v)), 0.01);

            /* ── 히트맵 JSX ── */
            const HeatmapView = () => {
              const n = complexIds.length;
              const availW = Math.max(80, matrixColWidth - 28);
              const CW = Math.max(24, Math.floor(availW / (n + 1.5)));
              // isTiny: 셀을 정사각형으로 만들어 넓어 보이게 / 그 외: 행 높이 ~90px 고정
              const cellH = isTiny ? CW : Math.max(16, Math.min(30, Math.floor(90 / n)));
              const mcFs = CW >= 50 ? 12 : CW >= 38 ? 11 : 10;
              const cellStyle = { height: cellH, lineHeight: `${cellH}px`, width: CW, minWidth: CW, maxWidth: CW };
              // 행 레이블 열은 데이터 셀보다 좁게 → 색상 셀이 더 왼쪽에서 시작
              const labelW = Math.max(20, Math.round(CW * 0.9));
              const labelStyle = { height: cellH, lineHeight: `${cellH}px`, width: labelW, minWidth: labelW, maxWidth: labelW };
              const lbl = id => {
                const l = shortLabel(id);
                return CW < 30 ? l.slice(0, 1) : CW < 38 ? l.slice(0, 2) : CW < 48 ? l.slice(0, 3) : CW < 60 ? l.slice(0, 4) : l;
              };
              return (
                <>
                  <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                    <table className="matrix-table" style={{ tableLayout: 'fixed' }}>
                      <thead><tr>
                        <th className="mh" style={{ ...labelStyle, height: 'auto', lineHeight: 'normal', paddingBottom: 5 }} />
                        {complexIds.map(id => <th key={id} className="mh" style={{ ...cellStyle, height: 'auto', lineHeight: 'normal', paddingBottom: 5 }}>{lbl(id)}</th>)}
                      </tr></thead>
                      <tbody>
                        {complexIds.map(row => (
                          <tr key={row}>
                            <th className="mh" style={{ ...labelStyle, textAlign: 'right', paddingRight: 5 }}>{lbl(row)}</th>
                            {complexIds.map(col => {
                              if (row === col) return <td key={col} className="mc" style={{ ...cellStyle, fontSize: mcFs, background: '#f1f5f9', border: '1px solid #e2e8f0' }} />;
                              const v = calcPearson(complexData[row], complexData[col]);
                              const { background, color } = corrStyle(v);
                              return <td key={col} className="mc" style={{ ...cellStyle, fontSize: mcFs, background, color }}>{v.toFixed(2)}</td>;
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: isTiny ? 12 : 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, color: '#94a3b8' }}>
                      <span>-1.0</span>
                      <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'linear-gradient(to right,rgb(30,64,175),rgb(248,250,252),rgb(185,28,28))' }} />
                      <span>+1.0</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, fontWeight: 600, color: '#475569', marginTop: 4 }}>
                      <span>강한 음의 상관관계</span>
                      <span>강한 양의 상관관계</span>
                    </div>
                  </div>
                </>
              );
            };

            /* ── 바 차트 JSX ── */
            const BarView = ({ pairs, maxAbs = globalMaxAbs, showFull = false }) => {
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: showFull ? 10 : 7 }}>
                  {pairs.map(({ a, b, v }, idx) => {
                    const barW = Math.abs(v) / maxAbs * 100;
                    const barCol = corrStyle(v).background;
                    const textCol = corrColor(v);
                    const isPos = v > 0;
                    const abs = Math.abs(v);
                    const desc = abs >= 0.3
                      ? getPairDesc(a, b, isPos, abs)
                      : `|r| = ${abs.toFixed(2)} · 0.3 미만으로 통계적으로 유의미한 상관관계가 없습니다.`;
                    const pairKey = `${a}|${b}`;
                    const isExpanded = showFull || expandedPairKey === pairKey;
                    return (
                      <div key={idx}
                        onClick={showFull ? undefined : () => setExpandedPairKey(isExpanded ? null : pairKey)}
                        style={{ cursor: showFull ? 'default' : 'pointer' }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: showFull ? 4 : 3 }}>
                          <span style={{ fontSize: showFull ? 12 : 11, color: '#312e81', fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{shortLabel(a)} · {shortLabel(b)}</span>
                          <span style={{ fontSize: showFull ? 12 : 11, fontWeight: 800, color: textCol, flexShrink: 0 }}>{isPos ? '▲' : '▼'} {v.toFixed(2)}</span>
                        </div>
                        <div style={{ height: 6, borderRadius: 3, background: '#f1f5f9', overflow: 'hidden', marginBottom: showFull ? 4 : 3 }}>
                          <div style={{ width: `${barW}%`, height: '100%', borderRadius: 3, background: barCol, transition: 'width 0.3s' }} />
                        </div>
                        <div style={{
                          fontSize: showFull ? 11 : 10, color: '#6d28d9', lineHeight: 1.5, fontWeight: 500,
                          ...(isExpanded ? {} : { overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }),
                        }}>{desc}</div>
                      </div>
                    );
                  })}
                </div>
              );
            };


            return (
              <div className="matrix-side">
                <div className="matrix-side-title">
                  상관계수 분석
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400 }}>Pearson</span>
                    {/* 5개 이상일 때만 돋보기 노출 */}
                    {!isCompact && (
                      <button
                        onClick={() => setShowMatrix(true)}
                        title="전체 히트맵 팝업"
                        style={{ background: 'none', border: '1px solid #e2e8f0', borderRadius: 5, padding: '3px 6px', cursor: 'pointer', color: '#475569', display: 'flex', alignItems: 'center' }}
                      >
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="22" y2="22"/>
                        </svg>
                      </button>
                    )}
                  </div>
                </div>

                {(() => {
                  const EmptySection = ({ isTop }) => (
                    <div style={{ flex: 1, minHeight: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, background: '#f8fafc', borderRadius: 8, border: '1px dashed #e2e8f0', padding: '12px 16px', textAlign: 'center' }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8' }}>해당 쌍 없음</div>
                      <div style={{ fontSize: 10, color: '#cbd5e1', lineHeight: 1.7 }}>
                        {isTop
                          ? '모든 쌍이 하위 3개에 포함되어 있습니다.'
                          : '종목 수가 적어 상위 3쌍이 전부입니다.'}
                      </div>
                    </div>
                  );
                  const TopHeader = () => (
                    <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 10, flexShrink: 0 }}>
                      <span style={{ color: '#2563eb' }}>▲ 높은 상관계수</span> TOP {pairCount}
                    </div>
                  );
                  const BottomHeader = () => (
                    <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 10, flexShrink: 0 }}>
                      <span style={{ color: '#dc2626' }}>▼ 낮은 상관계수</span> TOP {pairCount}
                    </div>
                  );

                  const topSection = (
                    <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                      <TopHeader />
                      {topPairs.length > 0 ? <BarView pairs={topPairs} /> : <EmptySection isTop />}
                    </div>
                  );
                  const bottomSection = (
                    <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                      <BottomHeader />
                      {bottomPairs.length > 0 ? <BarView pairs={bottomPairs} /> : <EmptySection isTop={false} />}
                    </div>
                  );

                  const divider = <div style={{ height: 1, background: '#e2e8f0', flexShrink: 0, margin: `${isCompact ? 14 : 8}px 0` }} />;

                  return isTiny ? (
                    /* 3개 이하: 히트맵 + 전체 쌍 나열 (TOP N 없이, 설명 전체 표시) */
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ flexShrink: 0 }}>
                        <HeatmapView />
                        <div style={{ height: 1, background: '#e2e8f0', margin: '18px 0' }} />
                      </div>
                      <BarView pairs={sortedDesc} showFull />
                    </div>
                  ) : isCompact ? (
                    /* 4개: 히트맵 + TOP 3 split */
                    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
                      <div style={{ flexShrink: 0 }}>
                        <HeatmapView />
                        <div style={{ height: 1, background: '#e2e8f0', margin: '12px 0' }} />
                      </div>
                      {topSection}
                      {divider}
                      {bottomSection}
                    </div>
                  ) : (
                    /* 5개 이상: TOP 5 split */
                    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
                      {topSection}
                      {divider}
                      {bottomSection}
                    </div>
                  );
                })()}

              </div>
            );
          })() : (
            <div style={{ flex: 1, background: 'white', border: '1px solid var(--border)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#cbd5e1', fontSize: 11, textAlign: 'center', padding: 20 }}>
              종목 2개 이상<br/>선택 시 표시
            </div>
          )}
        </div>

        {/* NEWS column */}
        <div className="news-col">
          <div className="news-preview-card" style={{ flex: 1, overflow: 'hidden' }}>
            <div className="news-preview-header">
              <div className="news-preview-title">
                <span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
                관련 뉴스
              </div>
              <button className="news-preview-more" onClick={() => setNewsDrawerOpen(true)}>전체 보기 →</button>
            </div>
            <div className="news-preview-body">
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
                  {selectedStockId && STOCK_CONFIG[selectedStockId] ? '관련 뉴스가 없습니다.' : '관심종목을 선택해주세요'}
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
              ) : favDetail.news.map((n, i) => (
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
        </div>

        {/* Sidebar toggle tab */}
        <button
          className="sidebar-tab"
          onClick={() => setRightOpen(o => !o)}
          title={rightOpen ? '패널 닫기' : '패널 열기'}
          style={rightOpen ? { right: panelWidth } : {}}
        >
          {rightOpen ? '‹' : '›'}
        </button>

        {/* RIGHT panel */}
        <div className={`right-panel${rightOpen ? '' : ' right-panel-closed'}`} style={{ width: panelWidth }}>
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
                  <div className="tk-card-acts">
                    <button
                      className={`tk-card-star${favs.has('000000') ? ' starred' : ''}`}
                      onClick={e => toggleFav('000000', e)}
                    >{favs.has('000000') ? '★' : '☆'}</button>
                    <button
                      className="tk-card-det"
                      onClick={e => { e.stopPropagation(); selectStock('000000'); }}
                      title="대시보드에서 상세 보기"
                    >상세</button>
                  </div>
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
