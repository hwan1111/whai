'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { key: 'dashboard', icon: '🖥️', label: '대시보드',   href: '/dashboard' },
  { key: 'stock',     icon: '📊', label: '종목 분석', href: '/stock' },
  { key: 'analysis',  icon: '🧩', label: '복합 분석', href: '/analysis' },
  { key: 'news',      icon: '🗞️', label: '뉴스',       href: '/news' },
  { key: 'myreport',  icon: '📄', label: '내 리포트', href: '/my-report' },
];

export default function Sidebar({ dataDate }) {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="logo">
        <div className="logo-text">WH<span>Ai</span></div>
        <div className="logo-sub">다중 자산 지표 통합 분석 AI</div>
      </div>
      <nav>
        {NAV_ITEMS.map(item => (
          <Link
            key={item.key}
            href={item.href}
            className={`nav-item${pathname.startsWith(item.href) ? ' active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">
        데이터 기준: <span>{dataDate || '—'}</span><br />
        <span style={{ color: '#334155' }}>KRX · BOK ECOS</span>
      </div>
    </aside>
  );
}
