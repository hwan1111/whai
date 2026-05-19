'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getUser, getToken } from '@/lib/auth';
import Header from '@/components/Header';

export default function AppLayout({ children }) {
  const router = useRouter();
  const [updateTime, setUpdateTime] = useState('');
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!getUser()) {
      router.replace('/');
      return;
    }
    setChecked(true);
  }, [router]);

  useEffect(() => {
    if (!checked) return;
    async function loadDate() {
      try {
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch('/api/v1/prices/latest', { headers });
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
    <div className="app">
      <Header updateTime={updateTime} />
      <div className="content">
        {children}
      </div>
    </div>
  );
}
