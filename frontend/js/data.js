// ── Asset metadata (colors, display labels) ──────────────────
const ASSETS = {
  '000000':  { label: 'KOSPI 지수', color: '#94A3B8' },
  '005930':  { label: '삼성전자',   color: '#034EA2' },
  '000660':  { label: 'SK하이닉스', color: '#E31837' },
  '005380':  { label: '현대차',     color: '#002C5F' },
  '000270':  { label: '기아',       color: '#C8102E' },
  '079550':  { label: 'LIG디펜스',  color: '#0077C8' },
  '012450':  { label: '한화에어로', color: '#ED7100' },
  '105560':  { label: 'KB금융',     color: '#FFB500' },
  '055550':  { label: '신한지주',   color: '#5BADD1' },
  '051910':  { label: 'LG화학',     color: '#A50034' },
  '096770':  { label: 'SK이노베',   color: '#F46F19' },
  'KRW/USD': { label: 'KRW/USD',   color: '#3C3B6E' },
  'KRW/JPY': { label: 'KRW/JPY',   color: '#BC002D' },
  'KRW/EUR': { label: 'KRW/EUR',   color: '#003399' },
  'KRW/CNY': { label: 'KRW/CNY',   color: '#FFDE00' },
  'KRW/CHF': { label: 'KRW/CHF',   color: '#FF0000' },
  'KRW/GBP': { label: 'KRW/GBP',   color: '#012169' },
};

const EXCHANGE_PAIRS = new Set([
  'KRW/USD', 'KRW/JPY', 'KRW/EUR', 'KRW/CNY', 'KRW/CHF', 'KRW/GBP',
]);

// Cache: _cache[period][id] = [{date, return_pct}, ...]
const _cache = {};

async function fetchAssetData(id, period) {
  if (_cache[period]?.[id] !== undefined) return _cache[period][id];
  if (!_cache[period]) _cache[period] = {};

  try {
    const headers = getToken() ? { Authorization: `Bearer ${getToken()}` } : {};
    const url = EXCHANGE_PAIRS.has(id)
      ? `${API_BASE}/exchange-rates/history?pair=${encodeURIComponent(id)}&period=${period}`
      : `${API_BASE}/prices/${id}/history?period=${period}`;
    const res = await fetch(url, { headers });
    const data = res.ok ? await res.json() : [];
    _cache[period][id] = data;
    return data;
  } catch {
    _cache[period][id] = [];
    return [];
  }
}

function buildPeriodData(period, ids) {
  const cache = _cache[period] || {};

  // x축: 모든 종목 날짜의 합집합
  const allDates = new Set();
  for (const id of ids) {
    if (cache[id]?.length > 0) cache[id].forEach(r => allDates.add(r.date));
  }
  if (allDates.size === 0) return null;

  const sortedDates = [...allDates].sort();
  const labels = sortedDates.map(date => {
    const [, m, day] = date.split('-');
    return `${+m}/${+day}`;
  });

  const d = {};
  for (const id of ids) {
    const rows = cache[id];
    if (!rows?.length) continue;
    const byDate = Object.fromEntries(rows.map(r => [r.date, r.return_pct]));
    const firstDate = rows[0].date;
    const lastDate = rows[rows.length - 1].date;
    // 데이터 범위 밖은 null, 범위 내 누락은 forward-fill
    let last = 0;
    d[id] = sortedDates.map(date => {
      if (date < firstDate || date > lastDate) return null;
      if (byDate[date] !== undefined) last = byDate[date];
      return last;
    });
  }

  return { labels, d };
}
