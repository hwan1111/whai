'use client';
import { useState, useEffect } from 'react';
import { getToken } from '@/lib/auth';
import LoadingSpinner from '@/components/LoadingSpinner';

export default function NewsPage() {
  const [ticker, setTicker] = useState('');
  const [days, setDays] = useState('30');
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => { fetchNews(); }, []);

  async function fetchNews() {
    setLoading(true);
    setError(false);
    try {
      const params = new URLSearchParams({ days });
      if (ticker) params.set('ticker', ticker);
      const token = getToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`/api/v1/news?${params}`, { headers });
      if (!res.ok) throw new Error();
      setNews(await res.json());
    } catch {
      setError(true);
      setNews([]);
    }
    setLoading(false);
  }

  return (
    <>
      <div className="other-card mb">
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 3 }}>지수 / 종목 / 환율</div>
            <select className="fsel" value={ticker} onChange={e => setTicker(e.target.value)}>
              <option value="">전체</option>
              <optgroup label="지수">
                <option value="000000">KOSPI</option>
              </optgroup>
              <optgroup label="KRX 주요 종목">
                <option value="005930">삼성전자</option>
                <option value="000660">SK하이닉스</option>
                <option value="005380">현대차</option>
                <option value="000270">기아</option>
                <option value="079550">LIG디펜스앤에어로스페이스</option>
                <option value="012450">한화에어로스페이스</option>
                <option value="105560">KB금융</option>
                <option value="055550">신한지주</option>
                <option value="051910">LG화학</option>
                <option value="096770">SK이노베이션</option>
              </optgroup>
              <optgroup label="환율">
                <option value="USD">USD/KRW</option>
              </optgroup>
            </select>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 3 }}>기간</div>
            <select className="fsel" value={days} onChange={e => setDays(e.target.value)}>
              <option value="7">최근 7일</option>
              <option value="30">최근 30일</option>
              <option value="90">최근 90일</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={fetchNews}>검색</button>
        </div>
      </div>

      <div className="other-card">
        <div className="other-card-title">
          뉴스 목록
          <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 400, textTransform: 'none' }}>
            {!loading && !error && `총 ${news.length}건`}
          </span>
        </div>
        {loading ? (
          <div style={{ padding: '32px 0' }}><LoadingSpinner label="뉴스를 불러오는 중..." /></div>
        ) : error ? (
          <div style={{ color: '#dc2626', fontSize: 13, padding: '16px 0', textAlign: 'center' }}>뉴스를 불러오지 못했습니다.</div>
        ) : news.length === 0 ? (
          <div style={{ color: '#94a3b8', fontSize: 13, padding: '16px 0', textAlign: 'center' }}>해당 조건의 뉴스가 없습니다.</div>
        ) : (
          news.map((n, i) => (
            <div key={i} className="news-item" style={{ padding: '14px 0' }}>
              <div className="news-meta">
                <span className="ticker-tag">{n.ticker}</span>
                <span className="news-date">{n.date_str}</span>
                <span className="news-source">{n.source}</span>
              </div>
              <div className="news-title" style={{ fontSize: 15 }}>{n.title}</div>
              <div className="news-body" style={{ marginTop: 4 }}>{n.body}</div>
              {n.ai_summary && (
                <div className="ai-box" style={{ marginTop: 8, padding: '10px 12px' }}>
                  <div className="ai-header" style={{ marginBottom: 6 }}>
                    <span className="ai-badge" style={{ fontSize: 10 }}>WH<span style={{ color: '#93c5fd' }}>Ai</span> 3줄 요약</span>
                  </div>
                  <div className="ai-text" style={{ fontSize: 12 }}>{n.ai_summary}</div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </>
  );
}
