import { getToken } from './auth';

export const ASSETS = {
  '000000':  { label: 'KOSPI', color: '#94A3B8' },
  '005930':  { label: '삼성전자',   color: '#034EA2' },
  '000660':  { label: 'SK하이닉스', color: '#E8400A' },
  '005380':  { label: '현대차',     color: '#002C5F' },
  '000270':  { label: '기아',       color: '#C8102E' },
  '079550':  { label: 'LIG디펜스',  color: '#0077C8' },
  '012450':  { label: '한화에어로', color: '#FF9200' },
  '105560':  { label: 'KB금융',     color: '#FFB500' },
  '055550':  { label: '신한지주',   color: '#5BADD1' },
  '051910':  { label: 'LG화학',     color: '#A50034' },
  '096770':  { label: 'SK이노베',   color: '#E86500' },
  'USD': { label: 'USD',   color: '#3C3B6E' },
};

const _cache = {};

export async function fetchAssetData(id, period) {
  if (_cache[period]?.[id] !== undefined) return _cache[period][id];
  if (!_cache[period]) _cache[period] = {};

  try {
    const token = getToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(`/api/v1/prices/${encodeURIComponent(id)}/history?period=${period}`, { headers });
    const data = res.ok ? await res.json() : [];
    _cache[period][id] = data;
    return data;
  } catch {
    _cache[period][id] = [];
    return [];
  }
}

export function buildPeriodData(period, ids) {
  const cache = _cache[period] || {};

  const allDates = new Set();
  for (const id of ids) {
    if (cache[id]?.length > 0) cache[id].forEach(r => allDates.add(r.date));
  }
  if (allDates.size === 0) return null;

  const sortedDates = [...allDates].sort();
  const years = new Set(sortedDates.map(d => d.split('-')[0]));
  const multiYear = years.size > 1;
  const labels = sortedDates.map(date => {
    const [y, m, day] = date.split('-');
    return multiYear ? `${y}/${+m}/${+day}` : `${+m}/${+day}`;
  });

  const d = {};
  const closes = {};
  for (const id of ids) {
    const rows = cache[id];
    if (!rows?.length) continue;
    const byDate = Object.fromEntries(rows.map(r => [r.date, r.return_pct]));
    const byClose = Object.fromEntries(rows.map(r => [r.date, r.close ?? r.rate ?? null]));
    const firstDate = rows[0].date;
    const lastDate = rows[rows.length - 1].date;
    let last = 0, lastClose = null;
    d[id] = sortedDates.map(date => {
      if (date < firstDate || date > lastDate) return null;
      if (byDate[date] !== undefined) last = byDate[date];
      return last;
    });
    closes[id] = sortedDates.map(date => {
      if (date < firstDate || date > lastDate) return null;
      if (byClose[date] !== undefined) lastClose = byClose[date];
      return lastClose;
    });
  }

  return { labels, d, closes, isoLabels: sortedDates };
}
