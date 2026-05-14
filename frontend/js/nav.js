const NAV_ITEMS = [
  { key: 'dashboard', icon: '⊞', label: '대시보드',   href: 'dashboard.html' },
  { key: 'stock',     icon: '📈', label: '종목 분석', href: 'stock.html' },
  { key: 'analysis',  icon: '🔗', label: '복합 분석', href: 'analysis.html' },
  { key: 'news',      icon: '📰', label: '뉴스',       href: 'news.html' },
  { key: 'myreport',  icon: '📋', label: '내 리포트', href: 'my-report.html' },
];

const PAGE_TITLES = {
  dashboard: '대시보드',
  stock:     '종목 분석',
  analysis:  '복합 분석',
  news:      '뉴스',
  myreport:  '내 리포트',
};

const API_BASE = 'http://127.0.0.1:8000/api/v1';

function initLayout(pageKey) {
  requireAuth();
  const user = getUser();
  const initial = user ? user.name.charAt(0) : '?';

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
      <div style="position:relative">
        <div class="avatar" id="avatar-btn" onclick="toggleUserMenu(event)">${initial}</div>
        <div class="user-menu" id="user-menu">
          <div class="user-menu-header">
            <div class="user-menu-avatar">${initial}</div>
            <div>
              <div class="user-menu-name">${user ? user.name : ''}</div>
              <div class="user-menu-id">@${user ? user.id : ''}</div>
            </div>
          </div>
          <div class="user-menu-divider"></div>
          <div class="user-menu-item" onclick="openProfileModal()">👤 회원정보</div>
          <div class="user-menu-item" onclick="openPasswordModal()">🔑 비밀번호 변경</div>
          <div class="user-menu-divider"></div>
          <div class="user-menu-item user-menu-danger" onclick="logout()">↩ 로그아웃</div>
        </div>
      </div>
    </div>
  `;

  document.addEventListener('click', function (e) {
    const menu = document.getElementById('user-menu');
    const btn = document.getElementById('avatar-btn');
    if (menu && !menu.contains(e.target) && !btn.contains(e.target)) {
      menu.classList.remove('open');
    }
  });

  _injectModals();
}

function toggleUserMenu(e) {
  e.stopPropagation();
  document.getElementById('user-menu').classList.toggle('open');
}

// ── 회원정보 모달 ──
function openProfileModal() {
  document.getElementById('user-menu').classList.remove('open');
  const modal = document.getElementById('modal-profile');
  modal.style.display = 'flex';

  const user = getUser();
  const token = getToken();
  const body = document.getElementById('profile-body');

  const genderMap = { M: '남성', F: '여성', OTHER: '기타' };

  if (!token) {
    body.innerHTML = `
      <div class="modal-row"><span class="modal-label">이름</span><span class="modal-value">${user?.name || '-'}</span></div>
      <div class="modal-row"><span class="modal-label">아이디</span><span class="modal-value">${user?.id || '-'}</span></div>
      <div class="modal-row"><span class="modal-label">출생연도</span><span class="modal-value">미입력</span></div>
      <div class="modal-row"><span class="modal-label">성별</span><span class="modal-value">미입력</span></div>
    `;
    return;
  }

  body.innerHTML = '<div style="text-align:center;color:#94a3b8;padding:20px">불러오는 중...</div>';
  fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.json())
    .then(d => {
      body.innerHTML = `
        <div class="modal-row"><span class="modal-label">이름</span><span class="modal-value">${d.name}</span></div>
        <div class="modal-row"><span class="modal-label">아이디</span><span class="modal-value">${d.user_id}</span></div>
        <div class="modal-row"><span class="modal-label">출생연도</span><span class="modal-value">${d.birth_year || '미입력'}</span></div>
        <div class="modal-row"><span class="modal-label">성별</span><span class="modal-value">${genderMap[d.gender] || '미입력'}</span></div>
      `;
    })
    .catch(() => { body.innerHTML = '<div style="color:#dc2626;font-size:12px">정보를 불러오지 못했습니다.</div>'; });
}

// ── 비밀번호 변경 모달 ──
function openPasswordModal() {
  document.getElementById('user-menu').classList.remove('open');
  document.getElementById('modal-password').style.display = 'flex';
  document.getElementById('pw-current').value = '';
  document.getElementById('pw-new').value = '';
  document.getElementById('pw-new-confirm').value = '';
  document.getElementById('pw-change-msg').style.display = 'none';
}

async function submitPasswordChange() {
  const current = document.getElementById('pw-current').value;
  const next = document.getElementById('pw-new').value;
  const confirm = document.getElementById('pw-new-confirm').value;
  const msg = document.getElementById('pw-change-msg');
  msg.style.display = 'none';

  if (next !== confirm) {
    msg.textContent = '새 비밀번호가 일치하지 않습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
    return;
  }
  if (next.length < 5) {
    msg.textContent = '새 비밀번호는 5자 이상이어야 합니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
    return;
  }

  const btn = document.getElementById('pw-change-btn');
  btn.disabled = true;
  btn.textContent = '변경 중...';
  try {
    const res = await fetch(`${API_BASE}/auth/change-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.detail || '변경에 실패했습니다.';
      msg.className = 'modal-msg err';
    } else {
      msg.textContent = '비밀번호가 변경되었습니다.';
      msg.className = 'modal-msg ok';
    }
    msg.style.display = 'block';
  } catch {
    msg.textContent = '서버에 연결할 수 없습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '변경하기';
  }
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

function _injectModals() {
  if (document.getElementById('modal-profile')) return;
  const html = `
    <!-- 회원정보 모달 -->
    <div class="modal-overlay" id="modal-profile" style="display:none" onclick="if(event.target===this)closeModal('modal-profile')">
      <div class="modal-box">
        <div class="modal-title">👤 회원정보</div>
        <div id="profile-body"></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal('modal-profile')">닫기</button>
        </div>
      </div>
    </div>
    <!-- 비밀번호 변경 모달 -->
    <div class="modal-overlay" id="modal-password" style="display:none" onclick="if(event.target===this)closeModal('modal-password')">
      <div class="modal-box">
        <div class="modal-title">🔑 비밀번호 변경</div>
        <div class="modal-field">
          <div class="modal-label">현재 비밀번호</div>
          <div class="pw-wrap">
            <input class="modal-input" type="password" id="pw-current" maxlength="20" placeholder="현재 비밀번호 입력">
            <button type="button" class="eye-btn" onclick="toggleEye('pw-current', this)">👁</button>
          </div>
        </div>
        <div class="modal-field">
          <div class="modal-label">새 비밀번호</div>
          <div class="pw-wrap">
            <input class="modal-input" type="password" id="pw-new" maxlength="20" placeholder="5~20자">
            <button type="button" class="eye-btn" onclick="toggleEye('pw-new', this)">👁</button>
          </div>
        </div>
        <div class="modal-field">
          <div class="modal-label">새 비밀번호 확인</div>
          <div class="pw-wrap">
            <input class="modal-input" type="password" id="pw-new-confirm" maxlength="20" placeholder="새 비밀번호 재입력">
            <button type="button" class="eye-btn" onclick="toggleEye('pw-new-confirm', this)">👁</button>
          </div>
        </div>
        <div class="modal-msg" id="pw-change-msg" style="display:none"></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal('modal-password')">취소</button>
          <button class="btn btn-primary" id="pw-change-btn" onclick="submitPasswordChange()">변경하기</button>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
}
