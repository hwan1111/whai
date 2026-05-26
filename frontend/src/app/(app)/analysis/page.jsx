'use client';
import { useState } from 'react';
import { getToken } from '@/lib/auth';

const ALL_STOCKS = {
  '000000': 'KOSPI 지수',
  '005930': '삼성전자', '000660': 'SK하이닉스',
  '005380': '현대차',   '000270': '기아',
  '079550': 'LIG디펜스앤에어로스페이스', '012450': '한화에어로스페이스',
  '105560': 'KB금융',   '055550': '신한지주',
  '051910': 'LG화학',   '096770': 'SK이노베이션',
};

const ALL_FX = ['KRW/USD', 'KRW/JPY', 'KRW/EUR', 'KRW/CNY', 'KRW/CHF', 'KRW/GBP'];

const SHORT = {
  '000000': 'KOSPI',
  '005930': '삼성전자', '000660': 'SK하이닉스',
  '005380': '현대차',   '000270': '기아',
  '079550': 'LIG디펜스', '012450': '한화에어로',
  '105560': 'KB금융',   '055550': '신한지주',
  '051910': 'LG화학',   '096770': 'SK이노베',
  'KRW/USD': 'USD', 'KRW/JPY': 'JPY', 'KRW/EUR': 'EUR',
  'KRW/CNY': 'CNY', 'KRW/CHF': 'CHF', 'KRW/GBP': 'GBP',
};

const PERIOD_LABEL = { '1W': '1주', '1M': '1개월', '3M': '3개월', '6M': '6개월', '1Y': '1년', '3Y': '3년', 'ALL': '전체' };
const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

const dataCache = {};

async function fetchHistory(id, period) {
  const key = `${id}_${period}`;
  if (dataCache[key]) return dataCache[key];
  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const isFx = id.startsWith('KRW/');
  const url = isFx
    ? `/api/v1/exchange-rates/history?pair=${encodeURIComponent(id)}&period=${period}`
    : `/api/v1/prices/${id}/history?period=${period}`;
  try {
    const res = await fetch(url, { headers });
    if (!res.ok) return null;
    const rows = await res.json();
    if (rows.length < 2) return null;
    const dates = rows.map(r => r.date);
    const prices = rows.map(r => Number(isFx ? r.rate : r.close));
    const totalReturn = rows[rows.length - 1].return_pct;
    const dailyReturns = [];
    for (let i = 1; i < prices.length; i++)
      dailyReturns.push((prices[i] - prices[i - 1]) / prices[i - 1]);
    const dailyReturnDates = dates.slice(1);
    const result = { dates, closes: prices, dailyReturns, dailyReturnDates, totalReturn, sharpe: calcSharpe(dailyReturns) };
    dataCache[key] = result;
    return result;
  } catch { return null; }
}

function calcSharpe(dr) {
  if (dr.length < 2) return 0;
  const mean = dr.reduce((a, b) => a + b, 0) / dr.length;
  const std = Math.sqrt(dr.reduce((a, b) => a + (b - mean) ** 2, 0) / dr.length);
  return std === 0 ? 0 : parseFloat((mean / std * Math.sqrt(252)).toFixed(2));
}

function calcPearson(d1, d2) {
  const map1 = {}, map2 = {};
  d1.dailyReturnDates.forEach((d, i) => { map1[d] = d1.dailyReturns[i]; });
  d2.dailyReturnDates.forEach((d, i) => { map2[d] = d2.dailyReturns[i]; });
  const common = d1.dailyReturnDates.filter(d => map2[d] !== undefined);
  if (common.length < 2) return 0;
  const r1 = common.map(d => map1[d]);
  const r2 = common.map(d => map2[d]);
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
  const nr = 248, ng = 250, nb = 252;
  let r, g, b;
  if (t >= 0) {
    r = Math.round(nr + (30 - nr) * t);
    g = Math.round(ng + (64 - ng) * t);
    b = Math.round(nb + (175 - nb) * t);
  } else {
    const s = -t;
    r = Math.round(nr + (185 - nr) * s);
    g = Math.round(ng + (28 - ng) * s);
    b = Math.round(nb + (28 - nb) * s);
  }
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  const color = brightness < 140 ? 'white' : (t < 0 ? '#7f1d1d' : '#1e3a8a');
  return { background: `rgb(${r},${g},${b})`, color };
}

export default function AnalysisPage() {
  const [selected, setSelected] = useState([]);
  const [period, setPeriod] = useState('6M');
  const [stockData, setStockData] = useState({});

  async function toggleStock(id) {
    const next = selected.includes(id) ? selected.filter(s => s !== id) : [...selected, id];
    setSelected(next);
    if (next.length >= 2) {
      const results = await Promise.all(next.map(x => fetchHistory(x, period)));
      const sd = {};
      next.forEach((x, i) => { if (results[i]) sd[x] = results[i]; });
      setStockData(sd);
    }
  }

  async function changePeriod(p) {
    setPeriod(p);
    if (selected.length >= 2) {
      const results = await Promise.all(selected.map(x => fetchHistory(x, p)));
      const sd = {};
      selected.forEach((x, i) => { if (results[i]) sd[x] = results[i]; });
      setStockData(sd);
    }
  }

  const hasData = selected.length >= 2;

  function MatrixCell({ row, col }) {
    if (row === col) return <td className="mc" style={{ background: '#f1f5f9', border: '1px solid #e2e8f0' }} />;
    if (!stockData[row] || !stockData[col]) return <td className="mc" style={{ background: '#f8fafc', color: '#94a3b8' }}>—</td>;
    const v = calcPearson(stockData[row], stockData[col]);
    const { background, color } = corrStyle(v);
    return <td className="mc" style={{ background, color }}>{v.toFixed(2)}</td>;
  }

  const sharpeVals = selected.map(id => stockData[id]?.sharpe ?? 0);
  const maxS = Math.max(...sharpeVals.map(Math.abs), 1);

  let aiText = '';
  if (hasData) {
    const withData = selected.filter(id => stockData[id]);
    if (withData.length >= 2) {
      const best = withData.reduce((a, b) => stockData[a].totalReturn > stockData[b].totalReturn ? a : b);
      const worst = withData.reduce((a, b) => stockData[a].totalReturn < stockData[b].totalReturn ? a : b);
      const pairs = [];
      for (let i = 0; i < withData.length; i++)
        for (let j = i + 1; j < withData.length; j++)
          pairs.push([withData[i], withData[j], calcPearson(stockData[withData[i]], stockData[withData[j]])]);
      pairs.sort((a, b) => a[2] - b[2]);
      const lowCorr = pairs[0];
      const bestRet = stockData[best].totalReturn;
      const worstRet = stockData[worst].totalReturn;
      aiText = `${SHORT[best]}(${bestRet >= 0 ? '+' : ''}${bestRet.toFixed(1)}%)이 선택 종목 중 가장 높은 수익률을 기록했습니다. ` +
        `${SHORT[lowCorr[0]]}와 ${SHORT[lowCorr[1]]}의 상관계수는 ${lowCorr[2].toFixed(2)}로 가장 낮아 분산 효과가 큽니다. ` +
        (worstRet < 0
          ? `${SHORT[worst]}(${worstRet.toFixed(1)}%)은 유일하게 손실 구간에 있습니다.`
          : `전 종목이 플러스 수익률을 기록 중입니다.`);
    }
  }

  function AssetBtn({ id, label }) {
    const isSelected = selected.includes(id);
    return (
      <button
        className={`rbtn${isSelected ? ' active' : ''}`}
        onClick={() => toggleStock(id)}
      >
        {label}
      </button>
    );
  }

  return (
    <>
      <div className="other-card mb">
        <div className="other-card-title">분석 자산 선택</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: '#94a3b8', minWidth: 30, flexShrink: 0 }}>지수</span>
            <AssetBtn id="000000" label="KOSPI 지수" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: '#94a3b8', minWidth: 30, flexShrink: 0 }}>주식</span>
            {Object.entries(ALL_STOCKS).filter(([id]) => id !== '000000').map(([id, name]) => (
              <AssetBtn key={id} id={id} label={name} />
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: '#94a3b8', minWidth: 30, flexShrink: 0 }}>환율</span>
            {ALL_FX.map(id => <AssetBtn key={id} id={id} label={id} />)}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: '#64748b' }}>분석 기간:</span>
          <div className="range-sel">
            {PERIODS.map(p => (
              <div key={p} className={`rbtn${period === p ? ' active' : ''}`} onClick={() => changePeriod(p)}>
                {PERIOD_LABEL[p]}
              </div>
            ))}
          </div>
        </div>
      </div>

      {!hasData ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: 14 }}>
          <div style={{ fontSize: 40 }}>🧩</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#475569' }}>종목을 추가해주세요</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>2개 이상의 종목을 선택하면 상관계수·리스크 지표·AI 분석이 표시됩니다</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 6 }}>종목을 다시 클릭하면 선택 해제됩니다</div>
        </div>
      ) : (
        <>
          <div className="grid g21 mb">
            <div className="other-card">
              <div className="other-card-title">
                상관계수 매트릭스
                <span style={{ fontSize: 9, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>
                  Pearson · {PERIOD_LABEL[period]} 수익률
                </span>
              </div>
              <table className="matrix-table">
                <thead>
                  <tr>
                    <th className="mh" />
                    {selected.map(id => <th key={id} className="mh">{SHORT[id]}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {selected.map(row => (
                    <tr key={row}>
                      <th className="mh" style={{ textAlign: 'right', paddingRight: 5 }}>{SHORT[row]}</th>
                      {selected.map(col => <MatrixCell key={col} row={row} col={col} />)}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, fontSize: 10, color: '#64748b' }}>
                <span>-1.0</span>
                <div style={{ width: 140, height: 10, borderRadius: 4, background: 'linear-gradient(to right,rgb(185,28,28),rgb(248,250,252),rgb(30,64,175))' }} />
                <span>+1.0</span>
                <span style={{ marginLeft: 4, color: '#94a3b8' }}>· 빨강: 음의 상관 / 파랑: 양의 상관</span>
              </div>
            </div>

            <div className="other-card">
              <div className="other-card-title">리스크 · 수익 지표</div>
              <div style={{ fontSize: 10, color: '#64748b', marginBottom: 7 }}>{PERIOD_LABEL[period]} 수익률</div>
              <div className="grid g11" style={{ gap: 6, marginBottom: 12 }}>
                {selected.map(id => {
                  const d = stockData[id];
                  if (!d) return <div key={id} className="ret-box" style={{ background: '#f8fafc' }}><div className="ret-label">{SHORT[id]}</div><div className="ret-value" style={{ color: '#94a3b8' }}>—</div></div>;
                  const r = d.totalReturn, pos = r >= 0;
                  return (
                    <div key={id} className="ret-box" style={{ background: pos ? '#f0fdf4' : '#fef2f2' }}>
                      <div className="ret-label">{SHORT[id]}</div>
                      <div className={`ret-value ${pos ? 'positive' : 'negative'}`}>{pos ? '+' : ''}{r.toFixed(1)}%</div>
                    </div>
                  );
                })}
              </div>
              <div className="divider" />
              <div style={{ fontSize: 10, color: '#64748b', marginBottom: 9 }}>
                샤프 비율 <span style={{ fontWeight: 400, color: '#94a3b8', marginLeft: 4 }}>— 위험 대비 초과 수익</span>
              </div>
              {selected.map((id, i) => {
                if (!stockData[id]) return null;
                const s = sharpeVals[i], pos = s >= 0;
                const pct = Math.min(Math.abs(s) / maxS * 100, 100).toFixed(0);
                return (
                  <div key={id} className="factor-row" style={{ marginBottom: 7 }}>
                    <div className="factor-label" style={{ width: 80 }}>{SHORT[id]}</div>
                    <div className="factor-bar-bg"><div className="factor-fill" style={{ width: `${pct}%`, background: pos ? '#2563eb' : '#dc2626' }} /></div>
                    <div className={`factor-val${pos ? '' : ' negative'}`}>{pos ? '' : '-'}{Math.abs(s).toFixed(2)}</div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="other-card mb">
            <div className="other-card-title">AI 복합 분석</div>
            <div className="ai-box">
              <div className="ai-header">
                <span className="ai-badge">AI 복합 분석</span>
                <span className="ai-title">{selected.length}개 종목 통합 인사이트 — {PERIOD_LABEL[period]}</span>
              </div>
              <div className="ai-text" dangerouslySetInnerHTML={{ __html: aiText || '데이터를 불러오는 중입니다.' }} />
              <div className="ai-sources">
                <span className="ai-src-tag">📰 뉴스 5건</span>
                <span className="ai-src-tag">📄 리포트 3건</span>
                <span className="ai-src-tag">📊 {PERIOD_LABEL[period]} 데이터</span>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
