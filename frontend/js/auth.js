const WHAI_SESSION_KEY = 'whai_session';

function _rootPath() {
  return window.location.pathname.includes('/pages/') ? '../' : './';
}

function login(name, id, token) {
  localStorage.setItem(WHAI_SESSION_KEY, JSON.stringify({ name, id, token }));
}

function logout() {
  localStorage.removeItem(WHAI_SESSION_KEY);
  localStorage.removeItem('whai_profile_img');
  window.location.href = _rootPath() + 'index.html';
}

function setProfileImage(url) {
  if (url) localStorage.setItem('whai_profile_img', url);
  else localStorage.removeItem('whai_profile_img');
}

function getProfileImage() {
  return localStorage.getItem('whai_profile_img');
}

function getUser() {
  const s = localStorage.getItem(WHAI_SESSION_KEY);
  return s ? JSON.parse(s) : null;
}

function getToken() {
  return getUser()?.token ?? null;
}

function requireAuth() {
  if (!getUser()) {
    window.location.replace(_rootPath() + 'index.html');
  }
}

function toggleEye(inputId, btn) {
  const input = document.getElementById(inputId);
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  btn.style.opacity = isHidden ? '1' : '0.4';
}
