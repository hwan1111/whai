'use client';
import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getUser, getToken } from '@/lib/auth';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';

const PAGE_TITLES = {
  '/dashboard': '대시보드',
  '/stock':     '종목 분석',
  '/analysis':  '복합 분석',
  '/news':      '뉴스',
  '/my-report': '내 리포트',
};

export default function AppLayout({ children }) {
  const router = useRouter();
  const pathname = usePathname();
  const [dataDate, setDataDate] = useState('');
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
        const latestDate = data.reduce((a, b) => a.date > b.date ? a : b).date;
        setDataDate(latestDate);
        const now = new Date();
        const hhmm = now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
        setUpdateTime(`마지막 업데이트: ${hhmm} KST`);
      } catch { /* silent */ }
    }
    loadDate();
  }, [checked]);

  if (!checked) return null;

  const pageTitle = PAGE_TITLES[pathname] || '';

  return (
    <div className="app">
      <Sidebar dataDate={dataDate} />
      <div className="main">
        <Header pageTitle={pageTitle} updateTime={updateTime} />
        <div className="content">
          {children}
        </div>
      </div>
    </div>
  );
}
