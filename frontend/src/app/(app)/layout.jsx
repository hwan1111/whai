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
        const res = await fetchWithAuth('/api/v1/prices/data-freshness', { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();
        const formatDate = value => {
          if (!value) return '—';
          const [year, month, day] = value.slice(0, 10).split('-');
          return year && month && day ? `${year}/${Number(month)}/${Number(day)} 00:00 (KST)` : '—';
        };
        const sources = [
          { label: '주가', value: data.price },
          { label: '뉴스', value: data.news },
          { label: '펀더멘털', value: data.fundamental },
        ].filter(source => source.value);
        const grouped = sources.reduce((groups, source) => {
          const date = source.value.slice(0, 10);
          const group = groups.find(item => item.date === date);
          if (group) group.labels.push(source.label);
          else groups.push({ date, labels: [source.label] });
          return groups;
        }, []);
        const freshnessText = grouped.length === 1 && sources.length > 1
          ? formatDate(grouped[0].date)
          : grouped
              .map(group => `${group.labels.join('·')} ${formatDate(group.date)}`)
              .join(' · ');
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
