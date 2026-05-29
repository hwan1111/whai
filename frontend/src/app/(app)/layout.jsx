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
    async function loadDate() {
      try {
        const res = await fetchWithAuth('/api/v1/prices/latest');
        if (!res.ok) return;
        const data = await res.json();
        if (!data.length) return;
        const now = new Date();
        const hhmm = now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
        setUpdateTime(`마지막 업데이트: ${hhmm} KST`);
      } catch { /* silent */ }
    }
    loadDate();
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
