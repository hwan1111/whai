'use client';
import { useState, useEffect } from 'react';
import { fetchWithAuth } from '@/lib/auth';
import { ASSETS, fetchAssetData, buildPeriodData } from '@/lib/data';
import LineChart, { computeAnomalies } from '@/components/LineChart';

export const STOCK_CONFIG = {
  '000000': { name: 'KOSPI', sector: null, meta: '한국종합주가지수', logoSrc: '/assets/flags/kr.png', color: '#16a34a',
    factors: [{ label: '외국인 순매수', pct: 45, color: '#2563eb', val: '+45%', desc: '외국인 투자자 순매수가 지수 상승 방향을 주도' },
              { label: '글로벌 증시 동조화', pct: 32, color: '#7c3aed', val: '+32%', desc: 'S&P500·나스닥 강세와 동반 상승 흐름' },
              { label: 'USD/KRW 환율', pct: 8, color: '#dc2626', val: '-8%', desc: '원화 강세 → 수출 기업 실적 부담으로 지수 하방 압력' }] },
  '005930': { name: '삼성전자', sector: '반도체', meta: '반도체', logo: 'samsung.svg', color: '#034EA2',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 수요 증가', pct: 42, color: '#7c3aed', val: '+42%', desc: 'AI 서버향 HBM3E 수요 급증' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000660': { name: 'SK하이닉스', sector: '반도체', meta: '반도체', logo: 'skhynix.svg', color: '#E31837',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 28, color: '#2563eb', val: '+28%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'HBM 공급 선도', pct: 55, color: '#7c3aed', val: '+55%', desc: 'HBM 독점 공급 구조 확립' },
              { label: '환율 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원화 강세 → 반도체 수출 수익 감소' }] },
  '005380': { name: '현대차', sector: '자동차', meta: '자동차', logo: 'hyundai.png', color: '#002C5F',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '전동화 전환 성과', pct: 38, color: '#7c3aed', val: '+38%', desc: 'EV 판매 증가 및 프리미엄화 전략' },
              { label: '환율 영향', pct: 12, color: '#dc2626', val: '-12%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '000270': { name: '기아', sector: '자동차', meta: '자동차', logo: 'kia.png', color: '#C8102E',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 44, color: '#2563eb', val: '+44%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: 'EV9 판매 호조', pct: 38, color: '#7c3aed', val: '+38%', desc: '북미·유럽 전기 SUV 수요 급증' },
              { label: '환율 영향', pct: 10, color: '#dc2626', val: '-10%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '079550': { name: 'LIG디펜스앤에어로스페이스', sector: '방산', meta: '방산', logo: 'lignex1.svg', color: '#0077C8',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 18, color: '#2563eb', val: '+18%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 확대', pct: 68, color: '#7c3aed', val: '+68%', desc: 'K2 전차·K9 자주포 수출 계약 증가' },
              { label: '환율 영향', pct: 5, color: '#dc2626', val: '-5%', desc: '원화 강세 → 수출 수익 환산 감소' }] },
  '012450': { name: '한화에어로스페이스', sector: '방산', meta: '방산', logo: 'hanwha.svg', color: '#ED7100',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 32, color: '#2563eb', val: '+32%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '방산 수주 이슈', pct: 52, color: '#7c3aed', val: '+52%', desc: '폴란드·루마니아 수출 계약 뉴스 영향' },
              { label: '환율 영향', pct: 6, color: '#dc2626', val: '-6%', desc: '원화 강세 → 수출 수익 환산 시 감소' }] },
  '105560': { name: 'KB금융', sector: '금융', meta: '금융', logo: 'kb.svg', color: '#D4960A',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 48, color: '#2563eb', val: '+48%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 38, color: '#7c3aed', val: '+38%', desc: '순이자마진(NIM) 개선 효과' },
              { label: '대손충당금 증가', pct: 8, color: '#dc2626', val: '-8%', desc: '부동산 PF 리스크 반영' }] },
  '055550': { name: '신한지주', sector: '금융', meta: '금융', logo: 'shinhan.svg', color: '#5BADD1',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 45, color: '#2563eb', val: '+45%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '금리 상승 수혜', pct: 35, color: '#7c3aed', val: '+35%', desc: '이자이익 증가 효과' },
              { label: '대출 부실 위험', pct: 9, color: '#dc2626', val: '-9%', desc: '기업 구조조정 관련 충당금 부담' }] },
  '051910': { name: 'LG화학', sector: '화학', meta: '화학', logo: 'lgchem.svg', color: '#A50034',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 42, color: '#2563eb', val: '+42%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 사업 부진', pct: 48, color: '#dc2626', val: '-48%', desc: 'EV 배터리 수요 둔화 및 가격 하락' },
              { label: '글로벌 수요 약세', pct: 18, color: '#dc2626', val: '-18%', desc: '화학 제품 수요 둔화' }] },
  '096770': { name: 'SK이노베이션', sector: '화학', meta: '화학', logo: 'skinnovation.svg', color: '#F46F19',
    factors: [{ label: '시장 전체 (KOSPI)', pct: 38, color: '#2563eb', val: '+38%', desc: 'KOSPI와 함께 움직인 비율' },
              { label: '배터리 수주 증가', pct: 45, color: '#7c3aed', val: '+45%', desc: '북미 배터리 공장 가동률 상승' },
              { label: '유가 변동 영향', pct: 8, color: '#dc2626', val: '-8%', desc: '원유 가격 하락 → 화학 부문 수익성 압박' }] },
};

function fmt(v) { return v ? Number(v).toLocaleString('ko-KR') : '—'; }
function fmtNewsPeriod(start, end) {
  if (!start) return '';
  if (!end || start === end) return start;
  return `${start} ~ ${end}`;
}

export default function StockDetailModal({ stockId, onClose, holding, snapshotDate }) {
  const [pd, setPd] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [anomalies, setAnomalies] = useState([]);
  const [anomalyPopup, setAnomalyPopup] = useState(null);
  const [period, setPeriod] = useState('1M');

  useEffect(() => {
    setLoading(true);
    setPd(null);
    setDetail(null);
    Promise.all([
      fetchAssetData(stockId, period).then(() => {
        const data = buildPeriodData(period, [stockId]);
        if (data) { setPd(data); setAnomalies(computeAnomalies(data, [stockId], period)); }
      }),
      fetchWithAuth('/api/v1/prices/latest')
        .then(r => r.ok ? r.json() : [])
        .then(all => {
          const row = all.find(r => r.ticker === stockId);
          return row ? { price: row.close, changePct: row.change_pct, change: row.change } : {};
        }),
      fetchWithAuth(`/api/v1/news?ticker=${stockId}&days=90`)
        .then(r => r.ok ? r.json() : []),
    ]).then(([, priceData, news]) => {
      setDetail({ ...priceData, news: news ?? [] });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [stockId, period]);

  const cfg = STOCK_CONFIG[stockId];


  // 스냅샷 날짜 → 차트 x 위치 (0~100%) + 변동률 계산
  const snapshotInfo = (() => {
    if (!snapshotDate || !pd?.isoLabels) return null;
    const isoDay = snapshotDate.slice(0, 10);
    const n = pd.isoLabels.length;
    let idx = pd.isoLabels.lastIndexOf(isoDay);
    if (idx < 0) idx = pd.isoLabels.filter(d => d <= isoDay).length - 1;
    if (idx < 0) return null;
    const ML = 52, MR = 16, SW = 860, CW = SW - ML - MR;
    const xPct = ((ML + (idx / Math.max(n - 1, 1)) * CW) / SW * 100).toFixed(2);
    const closes = pd.closes?.[stockId];
    const snapClose = closes?.[idx];
    const latestClose = closes?.[n - 1];
    const changePct = snapClose && latestClose
      ? ((latestClose - snapClose) / snapClose * 100)
      : null;
    return { xPct, changePct, snapClose, latestClose };
  })();

  const chgPct = detail?.changePct;
  const chgAmt = detail?.change;
  const chgColor = (chgPct ?? 0) >= 0 ? '#dc2626' : '#2563eb';
  const chgArrow = (chgPct ?? 0) >= 0 ? '▲' : '▼';
  const newsList = detail?.news ?? [];

  const holdingItems = holding ? (() => {
    const pnl = holding.curVal - holding.cost;
    const retPct = holding.cost > 0 ? pnl / holding.cost * 100 : 0;
    const pc = pnl >= 0 ? '#dc2626' : '#2563eb';
    const fmtN = v => Number(Math.round(v)).toLocaleString('ko-KR');
    return [
      { label: '보유 수량',   val: `${fmtN(holding.qty)}주` },
      { label: '평균 매입가', val: `${fmtN(holding.avgPrice)}원` },
      { label: '평가액',      val: `${fmtN(holding.curVal)}원` },
      { label: '취득원가',    val: `${fmtN(holding.cost)}원` },
      { label: '손익',        val: `${pnl >= 0 ? '+' : '-'}${fmtN(Math.abs(pnl))}원`, color: pc },
      { label: '수익률',      val: `${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%`, color: pc },
    ];
  })() : null;

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'white',
        borderRadius: 18,
        boxShadow: '0 20px 60px rgba(0,0,0,0.18)',
        width: 880,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>

        {/* ── 헤더 ── */}
        <div style={{ padding: '16px 20px 14px', borderBottom: '1px solid #f1f5f9', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {cfg && (
                <div style={{ width: 36, height: 36, borderRadius: 9, background: '#f8fafc', border: '1px solid #e2e8f0', padding: 4, overflow: 'hidden', flexShrink: 0 }}>
                  <img src={cfg.logoSrc ?? `/assets/logos/${cfg.logo}`} alt={cfg.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                </div>
              )}
              <div>
                <div style={{ fontSize: 16, fontWeight: 800, color: '#1e293b', lineHeight: 1.2 }}>{cfg?.name ?? stockId}</div>
                {stockId !== '000000' && <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{stockId} · {cfg?.meta}</div>}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {detail?.price != null && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#1e293b', lineHeight: 1 }}>
                    {fmt(detail.price)}
                    <span style={{ fontSize: 12, color: '#64748b', fontWeight: 400, marginLeft: 2 }}>원</span>
                  </div>
                  {chgPct != null && (
                    <div style={{ fontSize: 12, fontWeight: 600, color: chgColor, marginTop: 2 }}>
                      {chgArrow} {chgAmt != null ? `${fmt(Math.abs(chgAmt))}원` : ''} ({Math.abs(chgPct).toFixed(2)}%)
                    </div>
                  )}
                </div>
              )}
              <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#cbd5e1', lineHeight: 1, padding: 0 }}>✕</button>
            </div>
          </div>
        </div>

        {/* ── 중단: 미니 차트 + 보유 현황 ── */}
        <div style={{ display: 'flex', gap: 14, padding: '16px 20px', borderBottom: '1px solid #f1f5f9', flexShrink: 0 }}>

          {/* 미니 차트 (왼쪽) */}
          <div style={{ flex: '0 0 530px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8, gap: 4 }}>
              {['1W','1M','3M','6M','1Y','3Y','ALL'].map(p => (
                <button key={p} onClick={() => setPeriod(p)} style={{
                  fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                  border: period === p ? '1.5px solid #1e293b' : '1.5px solid #e2e8f0',
                  background: period === p ? '#1e293b' : 'white',
                  color: period === p ? 'white' : '#475569',
                  transition: 'all 0.13s',
                }}>{p === '1W' ? '1주' : p === '1M' ? '1개월' : p === '3M' ? '3개월' : p === '6M' ? '6개월' : p === '1Y' ? '1년' : p === '3Y' ? '3년' : '전체'}</button>
              ))}
            </div>
            <div style={{ height: 240, position: 'relative', background: '#fafafa', border: '1px solid #f1f5f9', borderRadius: 10, overflow: 'hidden' }}>
              {loading ? (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#cbd5e1', fontSize: 13 }}>···</div>
              ) : pd ? (
                <>
                  <LineChart
                    activeAssets={[stockId]}
                    pd={pd}
                    hoveredAsset={null}
                    onHoverAsset={() => {}}
                    anomalies={anomalies}
                    onAnomalyHover={(a, cx, cy) => setAnomalyPopup({ anomaly: a, cx, cy })}
                    onAnomalyLeave={() => setAnomalyPopup(null)}
                    onAnomalyClick={null}
                    showAssetName={false}
                    labelFontSize={20}
                  />
                  {snapshotInfo && (() => {
                    const { xPct, changePct } = snapshotInfo;
                    const isUp = (changePct ?? 0) >= 0;
                    const col = isUp ? '#dc2626' : '#2563eb';
                    // MT=22, SH=300, CH=240 → 차트 영역만 커버
                    return (
                      <div
                        style={{
                          position: 'absolute',
                          top: `${22/300*100}%`,
                          height: `${240/300*100}%`,
                          left: `${xPct}%`,
                          width: 20,
                          transform: 'translateX(-50%)',
                          cursor: 'crosshair',
                          zIndex: 10,
                        }}
                      >
                        {/* 실제 선 */}
                        <div style={{
                          position: 'absolute',
                          top: 0, bottom: 0,
                          left: '50%', transform: 'translateX(-50%)',
                          width: 1.5,
                          background: '#ef4444',
                          opacity: 0.75,
                          pointerEvents: 'none',
                        }} />
                      </div>
                    );
                  })()}
                </>
              ) : (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#cbd5e1', fontSize: 12 }}>데이터 없음</div>
              )}
            </div>
          </div>

          {/* 보유 현황 그리드 (오른쪽) */}
          {holdingItems && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>내 보유 현황</div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gridTemplateRows: 'repeat(3, minmax(0, 1fr))',
                gap: 5,
                flex: 1,
                minHeight: 0,
              }}>
                {holdingItems.map(({ label, val, color }) => (
                  <div key={label} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 10px' }}>
                    <div style={{ fontSize: 11, color: '#64748b', fontWeight: 500, marginBottom: 4 }}>{label}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: color || '#1e293b' }}>{val}</div>
                  </div>
                ))}
              </div>
              {snapshotInfo?.changePct != null && holding?.qty && (() => {
                const { changePct, snapClose, latestClose } = snapshotInfo;
                const isZero = Math.abs(changePct) < 0.005;
                const isUp = changePct > 0;
                const col = isZero ? '#94a3b8' : isUp ? '#dc2626' : '#2563eb';
                const bg = isZero ? '#f1f5f9' : isUp ? '#fff1f1' : '#eff6ff';
                const border = isZero ? '#cbd5e1' : isUp ? '#fecaca' : '#bfdbfe';
                const pnl = (latestClose - snapClose) * holding.qty;
                const fmtN = v => Number(Math.round(Math.abs(v))).toLocaleString('ko-KR');
                return (
                  <div style={{ marginTop: 'auto', paddingTop: 5 }}>
                    <div style={{ background: bg, border: `1.5px solid ${border}`, borderRadius: 8, minHeight: 68, padding: '11px 12px', boxSizing: 'border-box' }}>
                      <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, marginBottom: 6 }}>지금까지 안 팔았다면?</div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 16, fontWeight: 800, color: col }}>
                          {isZero ? '±' : isUp ? '▲' : '▼'} {Math.abs(changePct).toFixed(2)}%
                        </span>
                        <span style={{ fontSize: 14, fontWeight: 700, color: col }}>
                          {isZero ? '±' : isUp ? '+' : '-'}{fmtN(pnl)}원
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>


        {/* anomaly 팝업 */}
        {anomalyPopup && (() => {
          const { anomaly, cx, cy } = anomalyPopup;
          return (
            <div style={{
              position: 'fixed',
              left: Math.min(cx + 12, window.innerWidth - 210),
              top: Math.min(Math.max(8, cy - 16), window.innerHeight - 140),
              background: 'white', border: '1.5px solid #fbbf24', borderRadius: 10,
              padding: '8px 12px', boxShadow: '0 4px 16px rgba(15,23,42,0.12)',
              zIndex: 9999, minWidth: 170, pointerEvents: 'none',
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#92400e', marginBottom: 6 }}>{anomaly.isoDate} 급변 포착</div>
              {anomaly.movers.map(m => (
                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 700, color: m.chg >= 0 ? '#dc2626' : '#2563eb' }}>
                    {m.chg >= 0 ? '▲' : '▼'} {Math.abs(m.chg).toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          );
        })()}

        {/* ── 하단: WHAi 뉴스 ── */}
        <div style={{ flexShrink: 0, padding: '0 20px 18px', background: 'white' }}>
          <div style={{ border: '1.5px solid #c4b5fd', borderRadius: 12, overflow: 'hidden', background: 'linear-gradient(160deg,#f5f3ff 0%,#eef2ff 100%)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '12px 14px 14px' }}>
              <span className="ai-badge">WH<span style={{ color: '#93c5fd' }}>Ai</span> 분석</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: '#4c1d95' }}>관련 뉴스</span>
            </div>
            <div style={{ padding: '0 14px' }}>
              {loading ? (
                <div style={{ color: '#64748b', fontSize: 12, textAlign: 'center', padding: '14px 0' }}>···</div>
              ) : newsList.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: 12, textAlign: 'center', padding: '14px 0' }}>관련 뉴스가 없습니다.</div>
              ) : (
                newsList.slice(0, 3).map((n, i) => (
                  <div key={i} className="news-preview-item" style={{ borderBottom: 'none', margin: 0, padding: '4px 0' }}>
                    <div className="news-meta">
                      <span className={`regime-direction ${n.direction === '상승' ? 'up' : n.direction === '하락' ? 'down' : 'neutral'}`}>{n.direction || '혼조'}</span>
                      <span className="news-date" style={{ marginLeft: 'auto', whiteSpace: 'nowrap' }}>{fmtNewsPeriod(n.start_date, n.end_date)}</span>
                    </div>
                    <div className="news-title" style={{ fontSize: 12 }}>{n.cause}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
