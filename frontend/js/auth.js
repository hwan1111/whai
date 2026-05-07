const WHAI_SESSION_KEY = 'whai_session';

function _rootPath() {
  return window.location.pathname.includes('/pages/') ? '../' : './';
}

function login(name, id) {
  localStorage.setItem(WHAI_SESSION_KEY, JSON.stringify({ name, id }));
}

function logout() {
  localStorage.removeItem(WHAI_SESSION_KEY);
  window.location.href = _rootPath() + 'index.html';
}

function getUser() {
  const s = localStorage.getItem(WHAI_SESSION_KEY);
  return s ? JSON.parse(s) : null;
}

function requireAuth() {
  if (!getUser()) {
    window.location.replace(_rootPath() + 'index.html');
  }
}
