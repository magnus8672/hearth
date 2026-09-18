const byId = id => document.getElementById(id);
const button = byId('check-browser');
const register = byId('register');
byId('trust-confirmed').addEventListener('change', event => { register.disabled = !event.target.checked; });
register.addEventListener('click', () => {
  if (!byId('trust-confirmed').checked) return;
  const target = new URL(register.dataset.url);
  if (target.protocol === 'https:' && target.hostname === location.hostname && !target.username && !target.password && target.pathname === '/auth/register') location.assign(target.href);
});
button.addEventListener('click', async () => {
  button.disabled = true;
  byId('browser-status').textContent = 'Checking secure connections from this browser…';
  try {
    const response = await fetch('/connection.json', {credentials:'omit', cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Setup information is not ready yet. Refresh this page in a moment.');
    const metadata = await response.json();
    const addresses = [['user', 'Workspace', metadata.base_url], ['admin', 'Administration', metadata.admin_url], ['identity', 'Sign-in', metadata.identity_url]];
    const results = await Promise.all(addresses.map(async ([id, label, origin]) => {
      const item = byId(`check-${id}`);
      item.textContent = `${label} · Checking…`; item.className = '';
      const url = new URL(origin);
      if (url.protocol !== 'https:' || url.hostname !== location.hostname || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Setup addresses do not match this hearth.');
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const probe = await fetch(`${url.origin}/health/browser`, {credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(5000)});
          const data = await probe.json();
          if (!probe.ok || data.service !== `hearth-${id}` || data.status !== 'ok') throw new Error('Unexpected service');
          item.textContent = `${label} · Secure connection verified`; item.className = 'passed';
          return true;
        } catch {
          if (attempt === 0) await new Promise(resolve => setTimeout(resolve, 1200));
        }
      }
      item.textContent = `${label} · Connection not verified`; item.className = 'failed';
      return false;
    }));
    byId('browser-status').textContent = results.every(Boolean)
      ? 'This browser can securely reach all three addresses. You’re ready to open hearth.'
      : 'A connection could not be verified. Open its check link below to see the browser error, review certificate trust and any local-network permission, then try again.';
    if (!results.every(Boolean)) byId('trust-help').open = true;
  } catch (error) {
    byId('browser-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
// No account tokens, passwords or application requests are sent by this page.
