'use client';
import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { login, getUser, setProfileImage } from '@/lib/auth';

const INVEST_OPTS = [
  { val: '안정형', label: '안정형' },
  { val: '안정추구형', label: '안정추구형' },
  { val: '위험중립형', label: '위험중립형' },
  { val: '적극투자형', label: '적극투자형' },
  { val: '공격투자형', label: '공격투자형' },
];

function AuthPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState('login');
  const sessionExpired = searchParams.get('expired') === '1';

  const [loginId, setLoginId] = useState('');
  const [loginPw, setLoginPw] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);

  const [regFirstName, setRegFirstName] = useState('');
  const [regLastName, setRegLastName] = useState('');
  const [regId, setRegId] = useState('');
  const [regPw, setRegPw] = useState('');
  const [regPwConfirm, setRegPwConfirm] = useState('');
  const [regBirthYear, setRegBirthYear] = useState('');
  const [regGender, setRegGender] = useState('');
  const [regInvest, setRegInvest] = useState('');
  const [regError, setRegError] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const [regIdHint, setRegIdHint] = useState({ text: '', type: '' });
  const [regPwHint, setRegPwHint] = useState({ text: '', type: '' });
  const [regPwConfirmHint, setRegPwConfirmHint] = useState({ text: '', type: '' });
  const [showLoginPw, setShowLoginPw] = useState(false);
  const [showRegPw, setShowRegPw] = useState(false);

  useEffect(() => {
    if (getUser()) router.replace('/dashboard');
  }, [router]);

  async function prefetchDashboard(token) {
    try {
      const h = { Authorization: `Bearer ${token}` };
      const [favsRes, pricesRes] = await Promise.allSettled([
        fetch('/api/v1/favorites', { headers: h }),
        fetch('/api/v1/prices/latest', { headers: h }),
      ]);
      const cache = {};
      if (favsRes.status === 'fulfilled' && favsRes.value.ok) cache.favs = await favsRes.value.json();
      if (pricesRes.status === 'fulfilled' && pricesRes.value.ok) cache.prices = await pricesRes.value.json();
      if (Object.keys(cache).length) sessionStorage.setItem('whai_prefetch', JSON.stringify(cache));
    } catch { /* silent */ }
  }

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError('');
    if (!loginId.trim() || !loginPw) { setLoginError('아이디와 비밀번호를 입력해 주세요.'); return; }
    setLoginLoading(true);
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: loginId.trim(), password: loginPw }),
      });
      const data = await res.json();
      if (!res.ok) {
        setLoginError(data.detail || '로그인에 실패했습니다.');
      } else {
        login(data.name, data.user_id, data.access_token, data.refresh_token);
        if (data.profile_image_url) setProfileImage(data.profile_image_url);
        prefetchDashboard(data.access_token);
        router.replace('/dashboard');
      }
    } catch {
      setLoginError('서버에 연결할 수 없습니다.');
    }
    setLoginLoading(false);
  }

  const ID_RE = /^[a-zA-Z0-9]{5,20}$/;

  async function checkIdAvailability(id) {
    if (!id) { setRegIdHint({ text: '', type: '' }); return; }
    if (!ID_RE.test(id)) {
      setRegIdHint({ text: '영문, 숫자만 5~20자로 입력해 주세요.', type: 'err' });
      return;
    }
    setRegIdHint({ text: '확인 중...', type: 'checking' });
    try {
      const res = await fetch(`/api/v1/auth/check-id?user_id=${encodeURIComponent(id)}`);
      const data = await res.json();
      if (!res.ok) {
        setRegIdHint({ text: '', type: '' });
        return;
      }
      if (data.available) {
        setRegIdHint({ text: '사용 가능한 아이디입니다.', type: 'ok' });
      } else {
        setRegIdHint({ text: '이미 사용 중인 아이디입니다.', type: 'err' });
      }
    } catch {
      setRegIdHint({ text: '', type: '' });
    }
  }

  function onPwChange(val) {
    setRegPw(val);
    if (!val) { setRegPwHint({ text: '', type: '' }); return; }
    if (val.length < 5) setRegPwHint({ text: '5자 이상 입력해 주세요.', type: 'err' });
    else setRegPwHint({ text: '사용 가능한 비밀번호입니다.', type: 'ok' });
    if (regPwConfirm) {
      setRegPwConfirmHint(val === regPwConfirm
        ? { text: '비밀번호가 일치합니다.', type: 'ok' }
        : { text: '비밀번호가 일치하지 않습니다.', type: 'err' });
    }
  }

  function onPwConfirmChange(val) {
    setRegPwConfirm(val);
    if (!val) { setRegPwConfirmHint({ text: '', type: '' }); return; }
    setRegPwConfirmHint(val === regPw
      ? { text: '비밀번호가 일치합니다.', type: 'ok' }
      : { text: '비밀번호가 일치하지 않습니다.', type: 'err' });
  }

  async function handleRegister(e) {
    e.preventDefault();
    setRegError('');
    const name = `${regLastName}${regFirstName}`.trim();
    if (!name) { setRegError('이름을 입력해 주세요.'); return; }
    if (!ID_RE.test(regId)) { setRegError('아이디 형식을 확인해 주세요.'); return; }
    if (regIdHint.type === 'err') { setRegError('아이디를 확인해 주세요.'); return; }
    if (regPw.length < 5) { setRegError('비밀번호는 5자 이상이어야 합니다.'); return; }
    if (regPw !== regPwConfirm) { setRegError('비밀번호가 일치하지 않습니다.'); return; }
    if (!regInvest) { setRegError('투자성향을 선택해 주세요.'); return; }

    setRegLoading(true);
    try {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, user_id: regId, password: regPw, invest_type: regInvest,
          birth_year: regBirthYear ? parseInt(regBirthYear) : null,
          gender: regGender || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRegError(data.detail || '회원가입에 실패했습니다.');
      } else {
        setLoginId(regId);
        setTab('login');
      }
    } catch {
      setRegError('서버에 연결할 수 없습니다.');
    }
    setRegLoading(false);
  }

  return (
    <div className="auth-body">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="auth-logo-text">WH<span>Ai</span></div>
          <div className="auth-logo-sub">다중 자산 지표 통합 분석 AI</div>
        </div>

        {sessionExpired && (
          <div style={{ background: '#fef3cd', border: '1px solid #fbbf24', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 14, color: '#92400e', fontWeight: 500 }}>
            세션이 만료되었습니다. 다시 로그인해 주세요.
          </div>
        )}
        <div className="auth-tabs">
          <div className={`auth-tab${tab === 'login' ? ' active' : ''}`} onClick={() => { setTab('login'); setLoginError(''); }}>로그인</div>
          <div className={`auth-tab${tab === 'register' ? ' active' : ''}`} onClick={() => { setTab('register'); setRegError(''); }}>회원가입</div>
        </div>

        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <div className="auth-title">로그인</div>
            <div className="auth-sub">계정에 로그인하세요</div>
            <div className="form-group">
              <label className="form-label">아이디</label>
              <input className="form-input" value={loginId} onChange={e => setLoginId(e.target.value)} placeholder="아이디 입력" autoComplete="username" />
            </div>
            <div className="form-group">
              <label className="form-label">비밀번호</label>
              <div className="pw-wrap">
                <input
                  className="form-input"
                  type={showLoginPw ? 'text' : 'password'}
                  value={loginPw}
                  onChange={e => setLoginPw(e.target.value)}
                  placeholder="비밀번호 입력"
                  autoComplete="current-password"
                />
                <button type="button" className="eye-btn" onClick={() => setShowLoginPw(p => !p)} style={{ opacity: showLoginPw ? 1 : 0.4 }}>👁</button>
              </div>
            </div>
            {loginError && <div className="auth-error">{loginError}</div>}
            <button type="submit" className="btn-login" disabled={loginLoading}>
              {loginLoading ? '로그인 중...' : '로그인'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <div className="auth-title">회원가입</div>
            <div className="auth-sub">새 계정을 만들어 시작하세요</div>
            <div className="form-group form-row">
              <div style={{ flex: 1 }}>
                <label className="form-label">성 <span className="required">*</span></label>
                <input className="form-input" value={regLastName} onChange={e => setRegLastName(e.target.value)} placeholder="홍" maxLength={5} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="form-label">이름 <span className="required">*</span></label>
                <input className="form-input" value={regFirstName} onChange={e => setRegFirstName(e.target.value)} placeholder="길동" maxLength={10} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">아이디 <span className="required">*</span></label>
              <input
                className="form-input"
                value={regId}
                onChange={e => { setRegId(e.target.value); setRegIdHint({ text: '', type: '' }); }}
                onBlur={e => checkIdAvailability(e.target.value)}
                placeholder="영문/숫자 5~20자"
                maxLength={20}
                autoComplete="username"
              />
              {regIdHint.text && <div className={`field-hint ${regIdHint.type}`}>{regIdHint.text}</div>}
            </div>
            <div className="form-group">
              <label className="form-label">비밀번호 <span className="required">*</span></label>
              <div className="pw-wrap">
                <input
                  className="form-input"
                  type={showRegPw ? 'text' : 'password'}
                  value={regPw}
                  onChange={e => onPwChange(e.target.value)}
                  placeholder="5~20자"
                  maxLength={20}
                  autoComplete="new-password"
                />
                <button type="button" className="eye-btn" onClick={() => setShowRegPw(p => !p)} style={{ opacity: showRegPw ? 1 : 0.4 }}>👁</button>
              </div>
              {regPwHint.text && <div className={`field-hint ${regPwHint.type}`}>{regPwHint.text}</div>}
            </div>
            <div className="form-group">
              <label className="form-label">비밀번호 확인 <span className="required">*</span></label>
              <input
                className="form-input"
                type="password"
                value={regPwConfirm}
                onChange={e => onPwConfirmChange(e.target.value)}
                placeholder="비밀번호 재입력"
                maxLength={20}
                autoComplete="new-password"
              />
              {regPwConfirmHint.text && <div className={`field-hint ${regPwConfirmHint.type}`}>{regPwConfirmHint.text}</div>}
            </div>
            <div className="form-group form-row">
              <div style={{ flex: 1 }}>
                <label className="form-label">출생연도</label>
                <input
                  className="form-input"
                  type="number"
                  value={regBirthYear}
                  onChange={e => setRegBirthYear(e.target.value)}
                  placeholder="1990"
                  min={1900}
                  max={new Date().getFullYear()}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="form-label">성별</label>
                <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                  {[{ val: 'M', label: '남성' }, { val: 'F', label: '여성' }].map(o => (
                    <div
                      key={o.val}
                      className={`invest-option${regGender === o.val ? ' selected' : ''}`}
                      style={{ flex: 1, textAlign: 'center', padding: '7px 4px', fontSize: 13 }}
                      onClick={() => setRegGender(g => g === o.val ? '' : o.val)}
                    >
                      {o.label}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">투자성향 <span className="required">*</span></label>
              <div className="invest-group">
                {INVEST_OPTS.map(o => (
                  <div
                    key={o.val}
                    className={`invest-option${regInvest === o.val ? ' selected' : ''}`}
                    onClick={() => setRegInvest(o.val)}
                  >
                    {o.label}
                  </div>
                ))}
              </div>
            </div>
            {regError && <div className="auth-error">{regError}</div>}
            <button type="submit" className="btn-login" disabled={regLoading}>
              {regLoading ? '처리 중...' : '회원가입'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function AuthPage() {
  return (
    <Suspense fallback={<div className="auth-body"><div className="auth-card">로딩 중...</div></div>}>
      <AuthPageContent />
    </Suspense>
  );
}
