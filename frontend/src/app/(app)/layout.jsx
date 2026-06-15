'use client';
import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { getUser, fetchWithAuth } from '@/lib/auth';
import Header from '@/components/Header';

const DESIGN_WIDTH = 1400;

export default function AppLayout({ children }) {
  const router = useRouter();
  const [updateTime, setUpdateTime] = useState('');
  const [checked, setChecked] = useState(false);
  const appRef = useRef(null);

  useEffect(() => {
    if (!getUser()) {
      router.replace('/');
      return;
    }
    setChecked(true);
  }, [router]);

  useEffect(() => {
    const el = appRef.current;
    if (!el) return;
    function updateScale() {
      const scale = window.innerWidth / DESIGN_WIDTH;
      el.style.transformOrigin = 'top left';
      el.style.transform = `scale(${scale})`;
      el.style.width = `${DESIGN_WIDTH}px`;
      const designHeight = Math.round(window.innerHeight / scale);
      el.style.height = `${designHeight}px`;
      document.documentElement.style.setProperty('--design-height', `${designHeight}px`);
    }
    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, []);

  useEffect(() => {
    if (!checked) return;
    async function loadDataFreshness() {
      try {
        const res = await fetchWithAuth('/api/v1/prices/data-freshness');
        if (!res.ok) return;
        const data = await res.json();
        const formatDate = value => {
          if (!value) return '—';
          const [year, month, day] = value.slice(0, 10).split('-');
          return year && month && day ? `${Number(month)}/${Number(day)}` : '—';
        };
        const sources = [
          { label: '주가·KOSPI·환율', value: data.price },
          { label: '펀더멘털', value: data.fundamental },
          { label: '뉴스 분석', value: data.news },
        ];
        const grouped = sources.reduce((acc, source) => {
          const date = source.value?.slice(0, 10);
          if (!date) return acc;
          const existing = acc.find(group => group.date === date);
          if (existing) existing.labels.push(source.label);
          else acc.push({ date, labels: [source.label] });
          return acc;
        }, []);
        const freshnessText = grouped
          .map(group => `${group.labels.join('·')} ${formatDate(group.date)}`)
          .join(' | ');
        setUpdateTime(freshnessText ? `최신 데이터 기준: ${freshnessText}` : '');
      } catch { /* silent */ }
    }
    loadDataFreshness();
  }, [checked]);

  if (!checked) return null;

  return (
    <div className="app" ref={appRef}>
      <Header updateTime={updateTime} />
      <div className="content">
        {children}
      </div>
    </div>
  );
}
