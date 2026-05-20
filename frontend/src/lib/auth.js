const SESSION_KEY = 'whai_session';
const PROFILE_IMG_KEY = 'whai_profile_img';
const REFRESH_KEY = 'whai_refresh';

export function getUser() {
  if (typeof window === 'undefined') return null;
  const s = localStorage.getItem(SESSION_KEY);
  return s ? JSON.parse(s) : null;
}

export function getToken() {
  return getUser()?.token ?? null;
}

export function getRefreshToken() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function login(name, id, token, refreshToken) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ name, id, token }));
  if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function setAccessToken(token) {
  const user = getUser();
  if (user) {
    user.token = token;
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  }
}

export function logout() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(PROFILE_IMG_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function updateUserName(name) {
  const user = getUser();
  if (user) {
    user.name = name;
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  }
}

export function getProfileImage() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(PROFILE_IMG_KEY);
}

export function setProfileImage(url) {
  if (url) localStorage.setItem(PROFILE_IMG_KEY, url);
  else localStorage.removeItem(PROFILE_IMG_KEY);
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function handleUnauthorized() {
  logout();
  window.location.href = '/login?expired=1';
}

let _refreshPromise = null;

async function tryRefresh() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const res = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setAccessToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

export async function fetchWithAuth(url, options = {}) {
  const token = getToken();
  const res = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (res.status === 401) {
    if (!_refreshPromise) {
      _refreshPromise = tryRefresh().finally(() => { _refreshPromise = null; });
    }
    const refreshed = await _refreshPromise;
    if (!refreshed) {
      handleUnauthorized();
      return res;
    }
    const newToken = getToken();
    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        ...(newToken ? { Authorization: `Bearer ${newToken}` } : {}),
      },
    });
  }
  return res;
}
