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
      el.style.height = `${window.innerHeight / scale}px`;
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
        const dates = [data.price, data.news, data.fundamental].map(formatDate);
        const allSame = dates.every(d => d === dates[0]);
        setUpdateTime(
          allSame
            ? `최신 데이터 기준: ${dates[0]}`
            : `최신 데이터 기준 · 주가 ${dates[0]} · 뉴스 ${dates[1]} · 펀더멘털 ${dates[2]}`
        );
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
