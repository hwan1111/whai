const SESSION_KEY = 'whai_session';
const PROFILE_IMG_KEY = 'whai_profile_img';

export function getUser() {
  if (typeof window === 'undefined') return null;
  const s = localStorage.getItem(SESSION_KEY);
  return s ? JSON.parse(s) : null;
}

export function getToken() {
  return getUser()?.token ?? null;
}

export function login(name, id, token) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ name, id, token }));
}

export function logout() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(PROFILE_IMG_KEY);
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
