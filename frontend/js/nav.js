const NAV_ITEMS = [
  { key: 'dashboard', icon: '⊞', label: '대시보드',     href: 'dashboard.html' },
  { key: 'stock',     icon: '📈', label: '종목 분석',   href: 'stock.html' },
  { key: 'analysis',  icon: '🔗', label: '복합 분석',   href: 'analysis.html' },
  { key: 'news',      icon: '📰', label: '뉴스',          href: 'news.html' },
  { key: 'myreport',  icon: '📋', label: '내 리포트',   href: 'my-report.html' },
];

const PAGE_TITLES = {
  dashboard: '대시보드',
  stock:     '종목 분석',
  analysis:  '복합 분석',
  news:      '뉴스',
  myreport:  '내 리포트',
};

function initLayout(pageKey) {
  requireAuth();
  const user = getUser();

  document.getElementById('sidebar').innerHTML = `
    <div class="logo">
      <div class="logo-text">WH<span>Ai</span></div>
      <div class="logo-sub">다중 자산 지표 통합 분석 AI</div>
    </div>
    <nav>
      ${NAV_ITEMS.map(item => `
        <a class="nav-item ${item.key === pageKey ? 'active' : ''}" href="${item.href}">
          <span class="nav-icon">${item.icon}</span> ${item.label}
        </a>
      `).join('')}
    </nav>
    <div class="sidebar-footer">
      <button class="btn-logout" onclick="logout()">↩ 로그아웃</button>
      데이터 기준: 2026-05-07<br>
      <span style="color:#334155">KRX · Frankfurter (ECB)</span>
    </div>
  `;

  document.getElementById('main-header').innerHTML = `
    <div class="header-left">
      <div class="page-title">${PAGE_TITLES[pageKey] || ''}</div>
    </div>
    <div class="header-right">
      <span style="font-size:11px;color:#94a3b8">마지막 업데이트: 15:32 KST</span>
      <div class="avatar">${user ? user.name.charAt(0) : '?'}</div>
    </div>
  `;
}
