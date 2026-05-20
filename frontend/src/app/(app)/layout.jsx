'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getUser, getToken } from '@/lib/auth';
import Header from '@/components/Header';
import Sidebar from '@/components/Sidebar';

export default function AppLayout({ children }) {
  const router = useRouter();
  const [dataDate, setDataDate] = useState('');
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!getUser()) {
      router.replace('/login');
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
        const d = new Date(data[0].date || data[0].created_at);
        if (!isNaN(d)) {
          setDataDate(d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }));
        }
      } catch { /* silent */ }
    }
    loadDate();
  }, [checked]);

  if (!checked) return null;

  return (
    <div className="app">
      <Header />
      <div className="app-body">
        <Sidebar dataDate={dataDate} />
        <div className="content">
          {children}
        </div>
      </div>
    </div>
  );
}
