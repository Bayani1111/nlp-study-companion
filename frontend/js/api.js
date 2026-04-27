/**
 * Shared API client.
 * - Uses same-origin secure cookies for authentication.
 * - Clears local user cache and redirects to login on 401 responses.
 */

const API_BASE = `${window.location.origin}/api`;

function clearClientSession() {
  localStorage.removeItem('user');
  if (window.reminderWS) {
    window.reminderWS.close();
    window.reminderWS = null;
  }
}

function readCookie(name) {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

async function request(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const isUnsafeMethod = !['GET', 'HEAD', 'OPTIONS'].includes(method);

  if (isUnsafeMethod) {
    const csrfToken = readCookie('study_companion_csrf');
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  const options = {
    method,
    headers,
    credentials: 'same-origin',
  };

  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(API_BASE + path, options);

  if (response.status === 401) {
    clearClientSession();
    window.location.hash = '#login';
    throw new Error('登录状态已失效，请重新登录。');
  }

  if (response.status === 204) {
    return null;
  }

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || '请求失败，请稍后再试。');
  }
  return data;
}

const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
  clearClientSession,
};
