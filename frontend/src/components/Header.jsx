'use client';
import { useState, useEffect, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { getUser, getProfileImage, setProfileImage, logout, updateUserName, fetchWithAuth } from '@/lib/auth';

const INVEST_MAP = {
  SAFE: '안정형', STAB: '안정추구형', NEUT: '위험중립형', GROW: '적극투자형', AGGR: '공격투자형',
};
const INVEST_VALS = ['SAFE', 'STAB', 'NEUT', 'GROW', 'AGGR'];

export default function Header({ updateTime }) {
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [modal, setModal] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileMsg, setProfileMsg] = useState({ text: '', type: '' });
  const [profileName, setProfileName] = useState('');
  const [profileInvest, setProfileInvest] = useState('');
  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwMsg, setPwMsg] = useState({ text: '', type: '' });
  const [imgMsg, setImgMsg] = useState({ text: '', type: '' });
  const [imgFile, setImgFile] = useState(null);
  const [imgPreview, setImgPreview] = useState(null);
  const [withdrawPw, setWithdrawPw] = useState('');
  const [withdrawMsg, setWithdrawMsg] = useState({ text: '', type: '' });
  const [saving, setSaving] = useState(false);
  const [toastMsg, setToastMsg] = useState('');
  const [toastVisible, setToastVisible] = useState(false);
  const [profileImg, setProfileImg] = useState(null);
  const menuRef = useRef(null);
  const fileInputRef = useRef(null);

  const user = getUser();
  const initial = user?.name?.charAt(0) || '?';

  useEffect(() => {
    setProfileImg(getProfileImage());
  }, []);

  useEffect(() => {
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  function showToast(msg) {
    setToastMsg(msg);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 2200);
  }

  async function openProfileModal() {
    setMenuOpen(false);
    setModal('profile');
    setProfileMsg({ text: '', type: '' });
    setProfileLoading(true);
    try {
      const res = await fetchWithAuth('/api/v1/auth/me');
      if (!res.ok) throw new Error();
      const d = await res.json();
      setProfileData(d);
      setProfileName(d.name || '');
      setProfileInvest(d.invest_type || '');
    } catch {
      setProfileData(null);
    }
    setProfileLoading(false);
  }

  async function saveProfile() {
    if (!profileName.trim()) { setProfileMsg({ text: '이름을 입력해 주세요.', type: 'err' }); return; }
    setSaving(true);
    setProfileMsg({ text: '', type: '' });
    try {
      const res = await fetchWithAuth('/api/v1/auth/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: profileName.trim(), invest_type: profileInvest || null }),
      });
      const data = await res.json();
      if (!res.ok) {
        setProfileMsg({ text: data.detail || '저장에 실패했습니다.', type: 'err' });
      } else {
        updateUserName(data.name);
        setProfileMsg({ text: '저장되었습니다.', type: 'ok' });
        setTimeout(() => setModal(null), 1200);
      }
    } catch {
      setProfileMsg({ text: '서버에 연결할 수 없습니다.', type: 'err' });
    }
    setSaving(false);
  }

  function openPasswordModal() {
    setMenuOpen(false);
    setModal('password');
    setPwCurrent(''); setPwNew(''); setPwConfirm('');
    setPwMsg({ text: '', type: '' });
  }

  async function submitPasswordChange() {
    if (pwNew !== pwConfirm) { setPwMsg({ text: '새 비밀번호가 일치하지 않습니다.', type: 'err' }); return; }
    if (pwNew.length < 5) { setPwMsg({ text: '새 비밀번호는 5자 이상이어야 합니다.', type: 'err' }); return; }
    setSaving(true);
    setPwMsg({ text: '', type: '' });
    try {
      const res = await fetchWithAuth('/api/v1/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: pwCurrent, new_password: pwNew }),
      });
      const data = await res.json();
      setPwMsg({ text: res.ok ? '비밀번호가 변경되었습니다.' : (data.detail || '변경에 실패했습니다.'), type: res.ok ? 'ok' : 'err' });
    } catch {
      setPwMsg({ text: '서버에 연결할 수 없습니다.', type: 'err' });
    }
    setSaving(false);
  }

  function openProfileImgModal() {
    setMenuOpen(false);
    setModal('profileImg');
    setImgFile(null);
    setImgPreview(null);
    setImgMsg({ text: '', type: '' });
  }

  function onFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    setImgFile(file);
    setImgMsg({ text: '', type: '' });
    const reader = new FileReader();
    reader.onload = ev => setImgPreview(ev.target.result);
    reader.readAsDataURL(file);
  }

  async function uploadProfileImage() {
    if (!imgFile) return;
    setSaving(true);
    setImgMsg({ text: '', type: '' });
    const formData = new FormData();
    formData.append('file', imgFile);
    try {
      const res = await fetchWithAuth('/api/v1/auth/me/profile-image', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        setImgMsg({ text: data.detail || '업로드에 실패했습니다.', type: 'err' });
      } else {
        setProfileImage(data.profile_image_url);
        setProfileImg(data.profile_image_url);
        setImgFile(null);
        setImgMsg({ text: '프로필 사진이 업데이트되었습니다.', type: 'ok' });
      }
    } catch {
      setImgMsg({ text: '서버에 연결할 수 없습니다.', type: 'err' });
    }
    setSaving(false);
  }

  async function deleteProfileImage() {
    setSaving(true);
    setImgMsg({ text: '', type: '' });
    try {
      const res = await fetchWithAuth('/api/v1/auth/me/profile-image', { method: 'DELETE' });
      if (!res.ok) {
        setImgMsg({ text: '삭제에 실패했습니다.', type: 'err' });
      } else {
        setProfileImage(null);
        setProfileImg(null);
        setImgPreview(null);
        setImgFile(null);
        setImgMsg({ text: '프로필 사진이 삭제되었습니다.', type: 'ok' });
      }
    } catch {
      setImgMsg({ text: '서버에 연결할 수 없습니다.', type: 'err' });
    }
    setSaving(false);
  }

  function openWithdrawalModal() {
    setMenuOpen(false);
    setModal('withdrawal');
    setWithdrawPw('');
    setWithdrawMsg({ text: '', type: '' });
  }

  async function submitWithdrawal() {
    if (!withdrawPw) { setWithdrawMsg({ text: '비밀번호를 입력해 주세요.', type: 'err' }); return; }
    setSaving(true);
    setWithdrawMsg({ text: '', type: '' });
    try {
      const res = await fetchWithAuth('/api/v1/auth/me', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: withdrawPw }),
      });
      if (!res.ok) {
        const data = await res.json();
        setWithdrawMsg({ text: data.detail || '탈퇴에 실패했습니다.', type: 'err' });
      } else {
        logout();
        router.replace('/');
      }
    } catch {
      setWithdrawMsg({ text: '서버에 연결할 수 없습니다.', type: 'err' });
    }
    setSaving(false);
  }

  function handleLogout() {
    logout();
    router.replace('/');
  }

  const avatarContent = profileImg
    ? <img src={profileImg} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={() => { setProfileImage(null); setProfileImg(null); }} alt="" />
    : initial;

  const genderMap = { M: '남성', F: '여성', OTHER: '기타' };

  return (
    <>
      <header className="header">
        <div className="header-left">
          <Link href="/dashboard" className="header-logo">
            <span className="header-logo-text">WH<span>Ai</span></span>
            <span className="header-logo-sub">다중 자산 지표 통합 분석 AI</span>
          </Link>
        </div>
        <div className="header-right">
          {updateTime && <span style={{ fontSize: 11, color: '#94a3b8' }}>{updateTime}</span>}
          <Link href="/my-report" className={`header-report-btn${pathname?.startsWith('/my-report') ? ' active' : ''}`}>
            📄 마이 리포트
          </Link>
          <div className="user-menu-wrap" ref={menuRef}>
            <div
              className="avatar"
              onClick={e => { e.stopPropagation(); setMenuOpen(o => !o); }}
              style={profileImg ? { overflow: 'hidden', padding: 0 } : {}}
            >
              {avatarContent}
            </div>
            <div className={`user-menu${menuOpen ? ' open' : ''}`}>
              <div className="user-menu-header">
                <div className="user-menu-avatar" style={profileImg ? { overflow: 'hidden', padding: 0 } : {}}>
                  {avatarContent}
                </div>
                <div>
                  <div className="user-menu-name">{user?.name || ''}</div>
                  <div className="user-menu-id">@{user?.id || ''}</div>
                </div>
              </div>
              <div className="user-menu-divider" />
              <div className="user-menu-item" onClick={openProfileModal}>👤 회원정보</div>
              <div className="user-menu-item" onClick={openProfileImgModal}>📷 프로필 사진</div>
              <div className="user-menu-item" onClick={openPasswordModal}>🔑 비밀번호 변경</div>
              <div className="user-menu-divider" />
              <div className="user-menu-item user-menu-danger" onClick={handleLogout}>🚪 로그아웃</div>
              <div className="user-menu-item user-menu-danger" onClick={openWithdrawalModal}>🗑️ 회원탈퇴</div>
            </div>
          </div>
        </div>
      </header>

      {/* 회원정보 모달 */}
      {modal === 'profile' && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setModal(null); }}>
          <div className="modal-box">
            <div className="modal-title">👤 회원정보</div>
            {profileLoading ? (
              <div style={{ textAlign: 'center', color: '#94a3b8', padding: 20 }}>불러오는 중...</div>
            ) : profileData ? (
              <>
                <div className="modal-row">
                  <span className="modal-label">이름</span>
                  <input
                    className="modal-input"
                    style={{ width: 140, textAlign: 'right', color: '#94a3b8' }}
                    value={profileName}
                    onChange={e => setProfileName(e.target.value)}
                    maxLength={20}
                  />
                </div>
                <div className="modal-row">
                  <span className="modal-label">아이디</span>
                  <span className="modal-value">{profileData.user_id}</span>
                </div>
                <div className="modal-row">
                  <span className="modal-label">출생연도</span>
                  <span className="modal-value">
                    {profileData.birth_year
                      ? `${profileData.birth_year}년 (${new Date().getFullYear() - profileData.birth_year + 1}세)`
                      : '미입력'}
                  </span>
                </div>
                <div className="modal-row">
                  <span className="modal-label">성별</span>
                  <span className="modal-value">{genderMap[profileData.gender] || '미입력'}</span>
                </div>
                <div style={{ marginTop: 12 }}>
                  <div className="modal-label" style={{ marginBottom: 8 }}>투자성향</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {INVEST_VALS.map(v => (
                      <button
                        key={v}
                        type="button"
                        className={`invest-opt${profileInvest === v ? ' selected' : ''}`}
                        onClick={() => setProfileInvest(v)}
                      >
                        {INVEST_MAP[v]}
                      </button>
                    ))}
                  </div>
                </div>
                {profileMsg.text && <div className={`modal-msg ${profileMsg.type}`}>{profileMsg.text}</div>}
              </>
            ) : (
              <div style={{ color: '#dc2626', fontSize: 12 }}>정보를 불러오지 못했습니다.</div>
            )}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setModal(null)}>닫기</button>
              {profileData && (
                <button className="btn btn-primary" onClick={saveProfile} disabled={saving}>
                  {saving ? '저장 중...' : '저장'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 비밀번호 변경 모달 */}
      {modal === 'password' && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setModal(null); }}>
          <div className="modal-box">
            <div className="modal-title">🔑 비밀번호 변경</div>
            {[
              { label: '현재 비밀번호', val: pwCurrent, setter: setPwCurrent },
              { label: '새 비밀번호', val: pwNew, setter: setPwNew, hint: '5~20자' },
              { label: '새 비밀번호 확인', val: pwConfirm, setter: setPwConfirm },
            ].map(({ label, val, setter, hint }) => (
              <div className="modal-field" key={label}>
                <div className="modal-label">{label}</div>
                <input
                  className="modal-input"
                  type="password"
                  value={val}
                  onChange={e => setter(e.target.value)}
                  placeholder={hint || ''}
                  maxLength={20}
                />
              </div>
            ))}
            {pwMsg.text && <div className={`modal-msg ${pwMsg.type}`}>{pwMsg.text}</div>}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setModal(null)}>취소</button>
              <button className="btn btn-primary" onClick={submitPasswordChange} disabled={saving}>
                {saving ? '변경 중...' : '변경하기'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 프로필 사진 모달 */}
      {modal === 'profileImg' && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setModal(null); }}>
          <div className="modal-box" style={{ width: 340 }}>
            <div className="modal-title">📷 프로필 사진</div>
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}>
                {(imgPreview || profileImg) ? (
                  <img
                    src={imgPreview || profileImg}
                    style={{ width: 90, height: 90, borderRadius: '50%', objectFit: 'cover', border: imgPreview ? '3px solid #2563eb' : '3px solid #e2e8f0' }}
                    alt=""
                  />
                ) : (
                  <div style={{ width: 90, height: 90, borderRadius: '50%', background: 'linear-gradient(135deg,#2563eb,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontSize: 32, fontWeight: 700 }}>
                    {initial}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => fileInputRef.current?.click()}>📁 사진 선택</button>
                {profileImg && !imgPreview && (
                  <button className="btn btn-danger" onClick={deleteProfileImage} disabled={saving}>삭제</button>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                style={{ display: 'none' }}
                onChange={onFileSelect}
              />
              <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>JPG · PNG · WEBP · GIF &nbsp;·&nbsp; 최대 5MB</div>
            </div>
            {imgMsg.text && <div className={`modal-msg ${imgMsg.type}`}>{imgMsg.text}</div>}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setModal(null)}>닫기</button>
              {imgFile && (
                <button className="btn btn-primary" onClick={uploadProfileImage} disabled={saving}>
                  {saving ? '업로드 중...' : '업로드'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 회원탈퇴 모달 */}
      {modal === 'withdrawal' && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setModal(null); }}>
          <div className="modal-box">
            <div className="modal-title">🗑️ 회원탈퇴</div>
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 18, lineHeight: 1.6 }}>
              탈퇴하시면 모든 데이터가 삭제되며 복구할 수 없습니다.<br />계속하려면 현재 비밀번호를 입력해 주세요.
            </p>
            <div className="modal-field">
              <div className="modal-label">현재 비밀번호</div>
              <input
                className="modal-input"
                type="password"
                value={withdrawPw}
                onChange={e => setWithdrawPw(e.target.value)}
                placeholder="비밀번호 입력"
                maxLength={20}
              />
            </div>
            {withdrawMsg.text && <div className={`modal-msg ${withdrawMsg.type}`}>{withdrawMsg.text}</div>}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setModal(null)}>취소</button>
              <button className="btn btn-danger" onClick={submitWithdrawal} disabled={saving}>
                {saving ? '처리 중...' : '탈퇴하기'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className={`toast${toastVisible ? ' show' : ''}`}>{toastMsg}</div>
    </>
  );
}
