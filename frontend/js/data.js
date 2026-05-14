// ── Seeded PRNG (mulberry32) ─────────────────────────────────
function _rng(seed) {
  let s = seed | 0;
  return function () {
    s += 0x6D2B79F5;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Brownian bridge: n points 0 → endVal, step std-dev = vol
function _gen(endVal, n, vol, seed) {
  const rand = _rng(seed);
  const arr = [0];
  for (let i = 1; i < n; i++)
    arr.push(arr[i - 1] + (rand() - 0.5) * 2 * vol);
  const drift = endVal - arr[n - 1];
  return arr.map((v, i) => +((v + (drift * i) / (n - 1)).toFixed(2)));
}

// ── Label generators ─────────────────────────────────────────
function _bizLabels(n) {
  const labels = [], d = new Date(2026, 4, 14);
  while (labels.length < n) {
    if (d.getDay() !== 0 && d.getDay() !== 6)
      labels.unshift(`${d.getMonth() + 1}/${d.getDate()}`);
    d.setDate(d.getDate() - 1);
  }
  return labels;
}

function _weekLabels(n) {
  const labels = [], d = new Date(2026, 4, 14);
  for (let i = n - 1; i >= 0; i--) {
    const w = new Date(d);
    w.setDate(d.getDate() - i * 7);
    labels.push(`${w.getMonth() + 1}/${w.getDate()}`);
  }
  return labels;
}

function _moLabels(n) {
  const labels = [], d = new Date(2026, 3, 1);
  for (let i = n - 1; i >= 0; i--) {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1);
    labels.push(`${m.getMonth() + 1}/${String(m.getFullYear()).slice(2)}`);
  }
  return labels;
}

function _qtrLabels(n) {
  const labels = [];
  let y = 2025, q = 4;
  for (let i = 0; i < n; i++) {
    labels.push(`${y}Q${q}`);
    q++; if (q > 4) { q = 1; y++; }
  }
  // Reverse to go from oldest to newest
  const startY = 2026 - Math.floor(n / 4), startQ = 4 - (n % 4) + 1;
  const result = [];
  let cy = startY, cq = (startQ < 1 ? 4 : startQ);
  if (startQ < 1) cy--;
  for (let i = 0; i < n; i++) {
    result.push(`${cy}Q${cq}`);
    cq++; if (cq > 4) { cq = 1; cy++; }
  }
  return result;
}

// ── Target endpoints (final cumulative return %) ─────────────
const _T = {
  '1W':  { KOSPI:4.5,  '005930':3.9,   '000660':9.8,   '005380':2.3,  '000270':1.5,
            '079550':9.8,  '012450':18.9,  '105560':2.1,  '055550':1.6,  '051910':-2.3,  '096770':1.4,
            'KRW/USD':-0.9,'KRW/JPY':1.9, 'KRW/EUR':1.1, 'KRW/CNY':-0.3,'KRW/CHF':-0.4,'KRW/GBP':1.8 },
  '1M':  { KOSPI:5.4,  '005930':6.2,   '000660':10.2,  '005380':2.7,  '000270':2.0,
            '079550':12.8, '012450':21.4,  '105560':3.4,  '055550':2.8,  '051910':-4.5,  '096770':2.5,
            'KRW/USD':-1.2,'KRW/JPY':2.4, 'KRW/EUR':1.9, 'KRW/CNY':-0.7,'KRW/CHF':-0.9,'KRW/GBP':2.7 },
  '3M':  { KOSPI:9.1,  '005930':11.5,  '000660':22.3,  '005380':6.5,  '000270':4.8,
            '079550':30.5, '012450':56.4,  '105560':8.2,  '055550':6.4,  '051910':-7.8,  '096770':5.8,
            'KRW/USD':-1.8,'KRW/JPY':7.2, 'KRW/EUR':4.1, 'KRW/CNY':-1.1,'KRW/CHF':-1.3,'KRW/GBP':4.2 },
  '6M':  { KOSPI:15.4, '005930':18.4,  '000660':28.5,  '005380':8.2,  '000270':6.1,
            '079550':38.5, '012450':82.1,  '105560':12.3, '055550':9.8,  '051910':-8.4,  '096770':5.2,
            'KRW/USD':-1.8,'KRW/JPY':9.8, 'KRW/EUR':5.1, 'KRW/CNY':-1.3,'KRW/CHF':-1.9,'KRW/GBP':5.8 },
  '1Y':  { KOSPI:19.8, '005930':23.1,  '000660':36.8,  '005380':16.5, '000270':13.8,
            '079550':72.5, '012450':142.5, '105560':17.8, '055550':15.2, '051910':-18.5, '096770':14.8,
            'KRW/USD':-3.5,'KRW/JPY':17.8,'KRW/EUR':11.2,'KRW/CNY':-2.8,'KRW/CHF':-4.2,'KRW/GBP':11.2 },
  '3Y':  { KOSPI:24.5, '005930':18.5,  '000660':78.5,  '005380':42.5, '000270':35.2,
            '079550':192.8,'012450':358.5, '105560':42.8, '055550':35.5, '051910':-58.2, '096770':28.5,
            'KRW/USD':-1.5,'KRW/JPY':25.8,'KRW/EUR':18.5,'KRW/CNY':12.5,'KRW/CHF':-1.8,'KRW/GBP':22.5 },
  '5Y':  { KOSPI:42.8, '005930':42.2,  '000660':152.8, '005380':98.5, '000270':82.8,
            '079550':285.5,'012450':458.5, '105560':78.5, '055550':65.8, '051910':-55.8, '096770':38.5,
            'KRW/USD':8.2, 'KRW/JPY':28.2,'KRW/EUR':25.2,'KRW/CNY':16.8,'KRW/CHF':8.5, 'KRW/GBP':30.8 },
  'ALL': { KOSPI:32.8, '005930':45.2,  '000660':168.5, '005380':115.8,'000270':98.2,
            '079550':332.8,'012450':512.5, '105560':95.5, '055550':78.8, '051910':-58.5, '096770':52.5,
            'KRW/USD':5.2, 'KRW/JPY':35.8,'KRW/EUR':28.5,'KRW/CNY':32.8,'KRW/CHF':4.5, 'KRW/GBP':35.5 },
};

// ── Per-asset base daily volatility (%) ──────────────────────
const _V = {
  KOSPI:0.8, '005930':1.2, '000660':1.8, '005380':1.0, '000270':1.2,
  '079550':2.5, '012450':3.2, '105560':0.8, '055550':0.8, '051910':1.5, '096770':1.2,
  'KRW/USD':0.35,'KRW/JPY':0.45,'KRW/EUR':0.38,'KRW/CNY':0.30,'KRW/CHF':0.38,'KRW/GBP':0.45,
};

// ── Build one period's data object ───────────────────────────
function _build(periodKey, n, volScale, labels) {
  const d = {};
  const ids = Object.keys(_T[periodKey]);
  ids.forEach((id, i) => {
    const vol = (_V[id] || 1.0) * volScale;
    // Deterministic seed per (period, asset)
    const seed = periodKey.split('').reduce((a, c) => a + c.charCodeAt(0), 0) * 31 + i * 17;
    d[id] = _gen(_T[periodKey][id], n, vol, seed);
  });
  return { labels, d };
}

// ── ASSETS ───────────────────────────────────────────────────
const ASSETS = {
  'KOSPI':   { label: 'KOSPI 지수', color: '#94A3B8' },  // 회색 점선
  '005930':  { label: '삼성전자',   color: '#034EA2' },  // Samsung 블루
  '000660':  { label: 'SK하이닉스', color: '#E31837' },  // SK 레드
  '005380':  { label: '현대차',     color: '#002C5F' },  // Hyundai 다크 네이비
  '000270':  { label: '기아',       color: '#C8102E' },  // Kia 레드
  '079550':  { label: 'LIG디펜스',  color: '#0077C8' },  // LIG 브라이트 블루
  '012450':  { label: '한화에어로', color: '#ED7100' },  // Hanwha 오렌지
  '105560':  { label: 'KB금융',     color: '#FFB500' },  // KB 골드
  '055550':  { label: '신한지주',   color: '#5BADD1' },  // Shinhan 라이트 블루
  '051910':  { label: 'LG화학',     color: '#A50034' },  // LG 와인 레드
  '096770':  { label: 'SK이노베',   color: '#F46F19' },  // SK Innovation 오렌지
  'KRW/USD': { label: 'KRW/USD',   color: '#3C3B6E' },  // 성조기 인디고 블루
  'KRW/JPY': { label: 'KRW/JPY',   color: '#BC002D' },  // 일장기 크림슨
  'KRW/EUR': { label: 'KRW/EUR',   color: '#003399' },  // EU기 로열 블루
  'KRW/CNY': { label: 'KRW/CNY',   color: '#FFDE00' },  // 오성홍기 별 노랑
  'KRW/CHF': { label: 'KRW/CHF',   color: '#FF0000' },  // 스위스 크로스 레드
  'KRW/GBP': { label: 'KRW/GBP',   color: '#012169' },  // 유니온잭 네이비
};

// ── DATA (generated) ─────────────────────────────────────────
// volScale: daily=1, weekly=√5≈2.2, monthly=√21≈4.6, quarterly=√63≈7.9
const DATA = {
  '1W':  _build('1W',  5,   1.0, _bizLabels(5)),
  '1M':  _build('1M',  22,  1.0, _bizLabels(22)),
  '3M':  _build('3M',  63,  1.0, _bizLabels(63)),
  '6M':  _build('6M',  126, 1.0, _bizLabels(126)),
  '1Y':  _build('1Y',  52,  2.2, _weekLabels(52)),
  '3Y':  _build('3Y',  36,  4.6, _moLabels(36)),
  '5Y':  _build('5Y',  60,  4.6, _moLabels(60)),
  'ALL': _build('ALL', 28,  7.9, _qtrLabels(28)),
};
