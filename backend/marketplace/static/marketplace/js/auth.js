// Bristol Food Network — shared frontend helpers.
// Loaded on every page via base.html. Keep this file free of
// page-specific logic; that belongs in each template's extra_js block.

/**
 * Read a cookie value by name. Works because CSRF_COOKIE_HTTPONLY = False
 * in settings.py, which deliberately allows this JS to read the token.
 */
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Make sure the browser has a csrftoken cookie before any POST/PATCH/DELETE.
 * Hits /api/csrf/, which exists purely to set this cookie.
 */
async function ensureCsrfCookie() {
  if (!getCookie('csrftoken')) {
    await fetch('/api/csrf/', { credentials: 'same-origin' });
  }
}

/**
 * Wrapper around fetch() that attaches the CSRF header and session
 * cookie automatically. Use this for every mutating API call.
 */
async function apiFetch(url, options = {}) {
  await ensureCsrfCookie();
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken'),
    ...(options.headers || {}),
  };
  return fetch(url, { ...options, headers, credentials: 'same-origin' });
}

/**
 * Where to send a user immediately after a successful login,
 * based on the "role" field returned by /api/auth/login/.
 */
function roleHomeUrl(role) {
  if (role === 'producer') return '/market/producer/';
  if (role === 'customer') return '/market/';
  return '/market/admin-dash/';
}

/**
 * Escape any user/producer-supplied text before it goes into innerHTML.
 * Product names, descriptions, etc. come from producer input and are
 * treated as untrusted in the browser, same as anywhere else.
 */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Pull a human-readable message out of a DRF error response, whatever
 * shape it comes in (detail / non_field_errors / a plain list / a
 * field-specific list).
 */
function extractErrorMessage(data, fallback = 'Something went wrong.') {
  if (!data) return fallback;
  if (data.detail) return data.detail;
  if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors[0];
  }
  if (Array.isArray(data) && data.length) return data[0];
  const firstKey = Object.keys(data)[0];
  if (firstKey && Array.isArray(data[firstKey])) return data[firstKey][0];
  return fallback;
}

document.addEventListener('DOMContentLoaded', () => {
  const logoutBtn = document.getElementById('logout-btn');
  if (!logoutBtn) return;

  logoutBtn.addEventListener('click', async () => {
    logoutBtn.disabled = true;
    try {
      const res = await apiFetch('/api/auth/logout/', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      if (res.ok) {
        window.location.href = '/market/login/';
      } else {
        logoutBtn.disabled = false;
      }
    } catch (err) {
      console.error('Logout failed:', err);
      logoutBtn.disabled = false;
    }
  });
});