const proof = location.hash.slice(1);
history.replaceState(null, '', '/');
const byId = id => document.getElementById(id);
let setupState = null;
let browserReady = false;
const addresses = [ ['admin', 'Administration', 8443], ['user', 'Workspace', 8444], ['identity', 'Sign-in', 8445] ];
async function call(action, payload = {}) {
  const response = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${proof}` }, body: JSON.stringify({ action, payload }) });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text); }
  if (!response.ok || data.error) throw new Error(data.error || 'Setup could not complete. Try again.');
  return data;
}
function render() {
  const data = setupState;
  if (!data) return;
  byId('fingerprint').textContent = data.fingerprint;
  byId('trust-panel').hidden = data.trusted;
  byId('browser-panel').hidden = false;
  byId('owner-form').hidden = !data.trusted || !browserReady || data.owner_created;
  byId('complete').hidden = !data.trusted || !browserReady || !data.owner_created;
  byId('status').textContent = !data.trusted ? 'Start by trusting this Hearth certificate on your Windows account.' : !browserReady ? 'Windows trust is installed. Checking this browser separately.' : data.owner_created ? 'Your Hearth already has an Owner. Browser connections are ready.' : 'Browser trust is ready. Let’s create your account.';
}
async function checkBrowser() {
  byId('check-browser').disabled = true;
  browserReady = false; render();
  byId('browser-status').textContent = 'Verifying all three HTTPS addresses…';
  const checks = await Promise.all(addresses.map(async ([id, label, port]) => {
    byId(`check-${id}`).textContent = `${label} · Checking…`;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch(`https://localhost:${port}/health/browser`, { credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(5000) });
        const data = await response.json();
        if (!response.ok || data.service !== `hearth-${id}` || data.status !== 'ok') throw new Error('Unexpected service');
        byId(`check-${id}`).textContent = `${label} · Secure connection verified`;
        return true;
      } catch {
        if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 1200));
      }
    }
    byId(`check-${id}`).textContent = `${label} · Connection not verified`;
    return false;
  }));
  browserReady = checks.every(Boolean);
  byId('browser-status').textContent = browserReady ? 'This browser can securely reach every Hearth address.' : 'This browser could not verify every connection. Check that the appliance is running and review the certificate help below.';
  byId('browser-help').open = !browserReady;
  byId('check-browser').disabled = false;
  render();
}
byId('check-browser').addEventListener('click', () => void checkBrowser());
byId('trust').addEventListener('click', async () => {
  byId('trust').disabled = true; byId('error').textContent = '';
  try { setupState = await call('trust'); render(); await checkBrowser(); } catch (error) { byId('error').textContent = error.message; }
  finally { byId('trust').disabled = false; }
});
byId('download-certificate').addEventListener('click', async () => {
  try {
    const data = await call('certificate');
    const url = URL.createObjectURL(new Blob([data.certificate], { type: 'application/x-pem-file' }));
    const link = document.createElement('a'); link.href = url; link.download = 'hearth-local-root.crt'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { byId('error').textContent = error.message; }
});
byId('owner-form').addEventListener('submit', async event => {
  event.preventDefault(); byId('error').textContent = '';
  if (!browserReady) return;
  if (byId('password').value !== byId('confirm').value) { byId('error').textContent = 'Your passwords do not match.'; return; }
  byId('create').disabled = true; byId('create').textContent = 'Creating your Hearth…';
  try {
    await call('owner', { farm_name: byId('farm-name').value, name: byId('name').value, username: byId('username').value, password: byId('password').value });
    setupState.owner_created = true;
    byId('password').value = ''; byId('confirm').value = ''; render();
  } catch (error) { byId('error').textContent = error.message; byId('create').disabled = false; byId('create').textContent = 'Create my Hearth'; }
});
if (!proof) { byId('status').textContent = 'Open setup using Start-Hearth.ps1. This page needs the one-time local setup proof.'; }
else call('status').then(data => { setupState = data; render(); return checkBrowser(); }).catch(error => { byId('status').textContent = 'Setup is not ready.'; byId('error').textContent = error.message; });
