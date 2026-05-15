const NAV_ITEMS = [
  { key: 'dashboard', icon: '🖥️', label: '대시보드',   href: 'dashboard.html' },
  { key: 'stock',     icon: '📊', label: '종목 분석', href: 'stock.html' },
  { key: 'analysis',  icon: '🧩', label: '복합 분석', href: 'analysis.html' },
  { key: 'news',      icon: '🗞️', label: '뉴스',       href: 'news.html' },
  { key: 'myreport',  icon: '📄', label: '내 리포트', href: 'my-report.html' },
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
  const profileImg = getProfileImage();
  const avatarInner = profileImg
    ? `<img src="${profileImg}" style="width:100%;height:100%;border-radius:50%;object-fit:cover">`
    : initial;
  const imgStyle = profileImg ? 'overflow:hidden;padding:0;' : '';

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
      데이터 기준: <span id="nav-data-date">—</span><br>
      <span style="color:#334155">KRX · Frankfurter (ECB)</span>
    </div>
  `;

  document.getElementById('main-header').innerHTML = `
    <div class="header-left">
      <div class="page-title">${PAGE_TITLES[pageKey] || ''}</div>
    </div>
    <div class="header-right">
      <span style="font-size:11px;color:#94a3b8" id="nav-update-time">마지막 업데이트: —</span>
      <div style="position:relative">
        <div class="avatar" id="avatar-btn" onclick="toggleUserMenu(event)" style="${imgStyle}">${avatarInner}</div>
        <div class="user-menu" id="user-menu">
          <div class="user-menu-header">
            <div class="user-menu-avatar" style="${imgStyle}">${avatarInner}</div>
            <div>
              <div class="user-menu-name">${user ? user.name : ''}</div>
              <div class="user-menu-id">@${user ? user.id : ''}</div>
            </div>
          </div>
          <div class="user-menu-divider"></div>
          <div class="user-menu-item" onclick="openProfileModal()">👤 회원정보</div>
          <div class="user-menu-item" onclick="openProfileImgModal()">📷 프로필 사진</div>
          <div class="user-menu-item" onclick="openPasswordModal()">🔑 비밀번호 변경</div>
          <div class="user-menu-divider"></div>
          <div class="user-menu-item user-menu-danger" onclick="logout()">🚪 로그아웃</div>
          <div class="user-menu-item user-menu-danger" onclick="openWithdrawalModal()">🗑️ 회원탈퇴</div>
        </div>
      </div>
    </div>
  `;

  if (profileImg) {
    [document.getElementById('avatar-btn'), document.querySelector('.user-menu-avatar')].forEach(el => {
      if (!el) return;
      const img = el.querySelector('img');
      if (img) img.onerror = function () {
        setProfileImage(null);
        el.innerHTML = initial;
        el.style.overflow = '';
        el.style.padding = '';
      };
    });
  }

  document.addEventListener('click', function (e) {
    const menu = document.getElementById('user-menu');
    const btn = document.getElementById('avatar-btn');
    if (menu && !menu.contains(e.target) && !btn.contains(e.target)) {
      menu.classList.remove('open');
    }
  });

  _injectModals();
  _loadNavDate();
  if (!getProfileImage()) _syncProfileImageFromServer();
}

async function _syncProfileImageFromServer() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) return;
    const data = await res.json();
    if (data.profile_image_url) {
      setProfileImage(data.profile_image_url);
      _applyAvatarImage(data.profile_image_url);
    }
  } catch { /* silent */ }
}

async function _loadNavDate() {
  try {
    const headers = getToken() ? { Authorization: `Bearer ${getToken()}` } : {};
    const res = await fetch(`${API_BASE}/prices/latest`, { headers });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.length) return;

    const latestDate = data.reduce((a, b) => a.date > b.date ? a : b).date;
    const dateEl = document.getElementById('nav-data-date');
    const timeEl = document.getElementById('nav-update-time');
    if (dateEl) dateEl.textContent = latestDate;
    if (timeEl) {
      const now = new Date();
      const hhmm = now.toLocaleTimeString('ko-KR', { hour:'2-digit', minute:'2-digit', hour12:false });
      timeEl.textContent = `마지막 업데이트: ${hhmm} KST`;
    }
  } catch { /* silent */ }
}

function toggleUserMenu(e) {
  e.stopPropagation();
  document.getElementById('user-menu').classList.toggle('open');
}

// ── 회원정보 모달 ──
const _INVEST_MAP = {
  SAFE: '안정형', STAB: '안정추구형', NEUT: '위험중립형', GROW: '적극투자형', AGGR: '공격투자형',
};
const _INVEST_VALS = ['SAFE', 'STAB', 'NEUT', 'GROW', 'AGGR'];

function openProfileModal() {
  document.getElementById('user-menu').classList.remove('open');
  const modal = document.getElementById('modal-profile');
  modal.style.display = 'flex';

  const body = document.getElementById('profile-body');
  const genderMap = { M: '남성', F: '여성', OTHER: '기타' };

  body.innerHTML = '<div style="text-align:center;color:#94a3b8;padding:20px">불러오는 중...</div>';
  document.getElementById('profile-save-btn').style.display = 'none';
  document.getElementById('profile-msg').style.display = 'none';

  fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${getToken()}` } })
    .then(r => r.json())
    .then(d => {
      const investOptions = _INVEST_VALS.map(v =>
        `<button type="button" class="invest-opt${d.invest_type === v ? ' selected' : ''}" data-val="${v}" onclick="_selectInvest(this)">${_INVEST_MAP[v]}</button>`
      ).join('');
      body.innerHTML = `
        <div class="modal-row">
          <span class="modal-label">이름</span>
          <input class="modal-input" id="profile-name-input" style="width:140px;text-align:right" value="${d.name}" maxlength="20">
        </div>
        <div class="modal-row"><span class="modal-label">아이디</span><span class="modal-value">${d.user_id}</span></div>
        <div class="modal-row"><span class="modal-label">출생연도</span><span class="modal-value">${d.birth_year || '미입력'}</span></div>
        <div class="modal-row"><span class="modal-label">성별</span><span class="modal-value">${genderMap[d.gender] || '미입력'}</span></div>
        <div style="margin-top:12px">
          <div class="modal-label" style="margin-bottom:8px">투자성향</div>
          <div id="invest-opts" style="display:flex;flex-wrap:wrap;gap:5px">${investOptions}</div>
        </div>
      `;
      document.getElementById('profile-save-btn').style.display = 'inline-block';
      document.getElementById('profile-name-input').addEventListener('input', () => {
        document.getElementById('profile-msg').style.display = 'none';
      });
    })
    .catch(() => { body.innerHTML = '<div style="color:#dc2626;font-size:12px">정보를 불러오지 못했습니다.</div>'; });
}

function _selectInvest(btn) {
  document.querySelectorAll('#invest-opts .invest-opt').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  document.getElementById('profile-msg').style.display = 'none';
}

async function saveProfile() {
  const nameInput = document.getElementById('profile-name-input');
  const selectedInvest = document.querySelector('#invest-opts .invest-opt.selected');
  const msg = document.getElementById('profile-msg');
  const btn = document.getElementById('profile-save-btn');

  const name = nameInput?.value.trim();
  if (!name) {
    msg.textContent = '이름을 입력해 주세요.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = '저장 중...';
  msg.style.display = 'none';

  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ name, invest_type: selectedInvest?.dataset.val ?? null }),
    });
    const data = await res.json();
    if (!res.ok) {
      msg.textContent = data.detail || '저장에 실패했습니다.';
      msg.className = 'modal-msg err';
      msg.style.display = 'block';
    } else {
      const user = getUser();
      if (user) {
        user.name = data.name;
        localStorage.setItem('whai_session', JSON.stringify(user));
        const nameEl = document.querySelector('.user-menu-name');
        if (nameEl) nameEl.textContent = data.name;
      }
      msg.textContent = '저장되었습니다.';
      msg.className = 'modal-msg ok';
      msg.style.display = 'block';
      setTimeout(() => closeModal('modal-profile'), 1200);
    }
  } catch {
    msg.textContent = '서버에 연결할 수 없습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '저장';
  }
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

function showToast(msg) {
  let el = document.getElementById('whai-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'whai-toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2200);
}

// ── 프로필 사진 모달 ──
function openProfileImgModal() {
  document.getElementById('user-menu').classList.remove('open');
  document.getElementById('modal-profile-img').style.display = 'flex';
  document.getElementById('profile-img-input').value = '';
  document.getElementById('profile-img-upload-btn').style.display = 'none';
  document.getElementById('profile-img-msg').style.display = 'none';
  _renderImgPreview(getProfileImage());
}

function _letterAvatar(initial) {
  return `<div style="width:90px;height:90px;border-radius:50%;background:linear-gradient(135deg,#2563eb,#7c3aed);display:flex;align-items:center;justify-content:center;color:white;font-size:32px;font-weight:700;margin:0 auto">${initial}</div>`;
}

function _renderImgPreview(url) {
  const wrap = document.getElementById('profile-img-preview');
  const deleteBtn = document.getElementById('profile-img-delete-btn');
  const initial = getUser()?.name?.charAt(0) || '?';
  if (url) {
    const img = document.createElement('img');
    img.src = url;
    img.style.cssText = 'width:90px;height:90px;border-radius:50%;object-fit:cover;border:3px solid #e2e8f0;display:block;margin:0 auto';
    img.onerror = function () {
      wrap.innerHTML = _letterAvatar(initial);
      if (deleteBtn) deleteBtn.style.display = 'none';
    };
    wrap.innerHTML = '';
    wrap.appendChild(img);
    if (deleteBtn) deleteBtn.style.display = 'inline-block';
  } else {
    wrap.innerHTML = _letterAvatar(initial);
    if (deleteBtn) deleteBtn.style.display = 'none';
  }
}

async function deleteProfileImage() {
  const msg = document.getElementById('profile-img-msg');
  const deleteBtn = document.getElementById('profile-img-delete-btn');
  deleteBtn.disabled = true;
  deleteBtn.textContent = '삭제 중...';
  msg.style.display = 'none';
  try {
    const res = await fetch(`${API_BASE}/auth/me/profile-image`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      msg.textContent = '삭제에 실패했습니다.';
      msg.className = 'modal-msg err';
      msg.style.display = 'block';
    } else {
      setProfileImage(null);
      const initial = getUser()?.name?.charAt(0) || '?';
      // 아바타 원래대로
      const avatarBtn = document.getElementById('avatar-btn');
      if (avatarBtn) { avatarBtn.innerHTML = initial; avatarBtn.style.overflow = ''; avatarBtn.style.padding = ''; }
      const menuAvatar = document.querySelector('.user-menu-avatar');
      if (menuAvatar) { menuAvatar.innerHTML = initial; menuAvatar.style.overflow = ''; menuAvatar.style.padding = ''; }
      _renderImgPreview(null);
      document.getElementById('profile-img-upload-btn').style.display = 'none';
      document.getElementById('profile-img-input').value = '';
      msg.textContent = '프로필 사진이 삭제되었습니다.';
      msg.className = 'modal-msg ok';
      msg.style.display = 'block';
    }
  } catch {
    msg.textContent = '서버에 연결할 수 없습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
  } finally {
    deleteBtn.disabled = false;
    deleteBtn.textContent = '삭제';
  }
}

function onProfileImgSelect(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const wrap = document.getElementById('profile-img-preview');
    wrap.innerHTML = `<img src="${e.target.result}" style="width:90px;height:90px;border-radius:50%;object-fit:cover;border:3px solid #2563eb;margin:0 auto;display:block">`;
  };
  reader.readAsDataURL(file);
  document.getElementById('profile-img-upload-btn').style.display = 'inline-block';
  document.getElementById('profile-img-msg').style.display = 'none';
}

async function uploadProfileImage() {
  const input = document.getElementById('profile-img-input');
  const file = input.files[0];
  if (!file) return;

  const msg = document.getElementById('profile-img-msg');
  const btn = document.getElementById('profile-img-upload-btn');
  btn.disabled = true;
  btn.textContent = '업로드 중...';
  msg.style.display = 'none';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/auth/me/profile-image`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    });
    if (!res.ok) {
      const data = await res.json();
      msg.textContent = data.detail || '업로드에 실패했습니다.';
      msg.className = 'modal-msg err';
      msg.style.display = 'block';
    } else {
      const data = await res.json();
      setProfileImage(data.profile_image_url);
      _applyAvatarImage(data.profile_image_url);
      msg.textContent = '프로필 사진이 업데이트되었습니다.';
      msg.className = 'modal-msg ok';
      msg.style.display = 'block';
      btn.style.display = 'none';
    }
  } catch {
    msg.textContent = '서버에 연결할 수 없습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = '업로드';
  }
}

function _applyAvatarImage(url) {
  const imgTag = `<img src="${url}" style="width:100%;height:100%;border-radius:50%;object-fit:cover">`;
  const avatarBtn = document.getElementById('avatar-btn');
  if (avatarBtn) { avatarBtn.innerHTML = imgTag; avatarBtn.style.cssText += ';overflow:hidden;padding:0'; }
  const menuAvatar = document.querySelector('.user-menu-avatar');
  if (menuAvatar) { menuAvatar.innerHTML = imgTag; menuAvatar.style.cssText += ';overflow:hidden;padding:0'; }
}

// ── 회원탈퇴 모달 ──
function openWithdrawalModal() {
  document.getElementById('user-menu').classList.remove('open');
  document.getElementById('modal-withdrawal').style.display = 'flex';
  document.getElementById('withdraw-pw').value = '';
  document.getElementById('withdraw-msg').style.display = 'none';
}

async function submitWithdrawal() {
  const pw = document.getElementById('withdraw-pw').value;
  const msg = document.getElementById('withdraw-msg');
  msg.style.display = 'none';

  if (!pw) {
    msg.textContent = '비밀번호를 입력해 주세요.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
    return;
  }

  const btn = document.getElementById('withdraw-btn');
  btn.disabled = true;
  btn.textContent = '처리 중...';

  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ password: pw }),
    });
    if (!res.ok) {
      const data = await res.json();
      msg.textContent = data.detail || '탈퇴에 실패했습니다.';
      msg.className = 'modal-msg err';
      msg.style.display = 'block';
      btn.disabled = false;
      btn.textContent = '탈퇴하기';
    } else {
      logout();
    }
  } catch {
    msg.textContent = '서버에 연결할 수 없습니다.';
    msg.className = 'modal-msg err';
    msg.style.display = 'block';
    btn.disabled = false;
    btn.textContent = '탈퇴하기';
  }
}

function _injectModals() {
  if (document.getElementById('modal-profile')) return;
  const html = `
    <!-- 회원정보 모달 -->
    <div class="modal-overlay" id="modal-profile" style="display:none" onclick="if(event.target===this)closeModal('modal-profile')">
      <div class="modal-box">
        <div class="modal-title">👤 회원정보</div>
        <div id="profile-body"></div>
        <div class="modal-msg" id="profile-msg" style="display:none"></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal('modal-profile')">닫기</button>
          <button class="btn btn-primary" id="profile-save-btn" style="display:none" onclick="saveProfile()">저장</button>
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
    <!-- 프로필 사진 모달 -->
    <div class="modal-overlay" id="modal-profile-img" style="display:none" onclick="if(event.target===this)closeModal('modal-profile-img')">
      <div class="modal-box" style="width:340px">
        <div class="modal-title">📷 프로필 사진</div>
        <div style="text-align:center;margin-bottom:16px">
          <div id="profile-img-preview" style="margin:0 auto 12px"></div>
          <input type="file" id="profile-img-input" accept="image/jpeg,image/png,image/webp,image/gif" style="display:none" onchange="onProfileImgSelect(this)">
          <div style="display:flex;justify-content:center;gap:8px">
            <button class="btn btn-ghost" onclick="document.getElementById('profile-img-input').click()">📁 사진 선택</button>
            <button class="btn btn-danger" id="profile-img-delete-btn" style="display:none" onclick="deleteProfileImage()">삭제</button>
          </div>
          <div style="font-size:11px;color:#94a3b8;margin-top:8px">JPG · PNG · WEBP · GIF &nbsp;·&nbsp; 최대 5MB</div>
        </div>
        <div class="modal-msg" id="profile-img-msg" style="display:none"></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal('modal-profile-img')">닫기</button>
          <button class="btn btn-primary" id="profile-img-upload-btn" style="display:none" onclick="uploadProfileImage()">업로드</button>
        </div>
      </div>
    </div>
    <!-- 회원탈퇴 모달 -->
    <div class="modal-overlay" id="modal-withdrawal" style="display:none" onclick="if(event.target===this)closeModal('modal-withdrawal')">
      <div class="modal-box">
        <div class="modal-title">🗑️ 회원탈퇴</div>
        <p style="font-size:13px;color:#64748b;margin-bottom:18px;line-height:1.6">탈퇴하시면 모든 데이터가 삭제되며 복구할 수 없습니다.<br>계속하려면 현재 비밀번호를 입력해 주세요.</p>
        <div class="modal-field">
          <div class="modal-label">현재 비밀번호</div>
          <div class="pw-wrap">
            <input class="modal-input" type="password" id="withdraw-pw" maxlength="20" placeholder="비밀번호 입력">
            <button type="button" class="eye-btn" onclick="toggleEye('withdraw-pw', this)">👁</button>
          </div>
        </div>
        <div class="modal-msg" id="withdraw-msg" style="display:none"></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal('modal-withdrawal')">취소</button>
          <button class="btn btn-danger" id="withdraw-btn" onclick="submitWithdrawal()">탈퇴하기</button>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', html);
}
