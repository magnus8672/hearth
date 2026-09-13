const proof = location.hash.slice(1);
history.replaceState(null, '', '/');
const byId = id => document.getElementById(id);
let ownerCreated = false;
async function call(action, payload = {}) {
  const response = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${proof}` }, body: JSON.stringify({ action, payload }) });
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(text); }
  if (!response.ok || data.error) throw new Error(data.error || 'Setup could not complete. Try again.');
  return data;
}
function ready(data) {
  ownerCreated = data.owner_created;
  byId('fingerprint').textContent = data.fingerprint;
  byId('trust-panel').hidden = data.trusted;
  byId('owner-form').hidden = !data.trusted || ownerCreated;
  byId('complete').hidden = !data.trusted || !ownerCreated;
  byId('status').textContent = data.trusted ? ownerCreated ? 'Your Hearth already has an Owner.' : 'Browser trust is ready. Let’s create your account.' : 'Your appliance is ready. Start by confirming browser trust.';
}
byId('trust').addEventListener('click', async () => {
  byId('trust').disabled = true; byId('error').textContent = '';
  try { ready(await call('trust')); } catch (error) { byId('error').textContent = error.message; }
  finally { byId('trust').disabled = false; }
});
byId('owner-form').addEventListener('submit', async event => {
  event.preventDefault(); byId('error').textContent = '';
  if (byId('password').value !== byId('confirm').value) { byId('error').textContent = 'Your passwords do not match.'; return; }
  byId('create').disabled = true; byId('create').textContent = 'Creating your Hearth…';
  try {
    await call('owner', { farm_name: byId('farm-name').value, name: byId('name').value, username: byId('username').value, password: byId('password').value });
    byId('password').value = ''; byId('confirm').value = ''; byId('owner-form').hidden = true; byId('complete').hidden = false; byId('status').textContent = 'Your Owner account is ready.';
  } catch (error) { byId('error').textContent = error.message; byId('create').disabled = false; byId('create').textContent = 'Create my Hearth'; }
});
if (!proof) { byId('status').textContent = 'Open setup using Start-Hearth.ps1. This page needs the one-time local setup proof.'; }
else call('status').then(ready).catch(error => { byId('status').textContent = 'Setup is not ready.'; byId('error').textContent = error.message; });
