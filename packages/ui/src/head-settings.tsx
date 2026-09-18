import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';

type Addresses = { base_url: string; admin_url: string; identity_url: string; welcome_url: string };
type Operation = { operation_id: string; state: string; message: string; target: Addresses; updated_at: string };
type HeadState = Addresses & { revision: string; operation: Operation | null; root_sha256: string | null };
type Preview = Addresses & { revision: string; addresses: string[]; previous: Addresses; trust_root_preserved: boolean };

function Links({ addresses }: { addresses: Addresses }) {
  return <dl className="head-addresses"><dt>Workspace</dt><dd><a href={addresses.base_url}>{addresses.base_url}</a></dd><dt>Administration</dt><dd><a href={`${addresses.admin_url}/#settings`}>{addresses.admin_url}</a></dd><dt>Sign-in</dt><dd>{addresses.identity_url}</dd><dt>Client API</dt><dd>{addresses.base_url}/v1</dd><dt>Welcome & certificates</dt><dd><a href={addresses.welcome_url}>{addresses.welcome_url}</a></dd></dl>;
}

export function HeadSettings({ identity }: { identity: Identity }) {
  const [state, setState] = useState<HeadState | null>(null);
  const [baseUrl, setBaseUrl] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [accepted, setAccepted] = useState<Operation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const allowed = identity.permissions.includes('farm.configure');
  async function refresh() {
    const value = await api<HeadState>('/api/v1/head/settings');
    setState(value); setBaseUrl(value.base_url); setError('');
  }
  useEffect(() => { if (allowed) void refresh().catch(reason => setError(reason.message)); }, [allowed]);
  async function prepare() {
    setBusy(true); setError(''); setPreview(null);
    try { setPreview(await api<Preview>('/api/v1/head/preview', mutation(identity, { base_url: baseUrl }))); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!preview) return;
    setBusy(true); setError('');
    const operationId = crypto.randomUUID();
    try {
      const result = await api<HeadState>('/api/v1/head/apply', mutation(identity, { base_url: preview.base_url, expected_revision: preview.revision, operation_id: operationId }));
      setAccepted(result.operation); setState(result); setPreview(null);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  if (!allowed) return <section className="panel"><h2>Head settings</h2><p>An Owner or FarmAdmin can change the head address.</p></section>;
  const operation = accepted || state?.operation;
  const active = operation && ['queued', 'applying', 'rolling_back'].includes(operation.state);
  return <section className="panel head-settings"><h2>Address & certificates</h2><p>Give your hearth a name on your network. Point DNS at this VM first, then preview the new address.</p>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {operation && <div className="info-banner" role="status"><div><strong>{operation.state === 'succeeded' ? 'Address updated' : operation.state === 'rolled_back' ? 'Previous address restored' : 'Address change'}</strong><p>{operation.message}</p>{active && <><p>This page may lose its connection during the restart. Wait a moment, then open the new Administration link and sign in.</p><Links addresses={operation.target} /></>}{operation.state === 'recovery_required' && <p>Use SSH to the VM to complete recovery before starting another change.</p>}</div></div>}
    {state && !active && <><Links addresses={state} /><p className="small-copy">Trusted root SHA-256: <code className="head-fingerprint">{state.root_sha256 || 'Not exported yet'}</code></p><a className="quiet-button button-link" href="/api/v1/head/certificates" download>Download certificate package</a></>}
    {!active && <form onSubmit={event => { event.preventDefault(); void prepare(); }}><label htmlFor="head-base-url">Workspace base URL</label><input id="head-base-url" type="url" required maxLength={300} value={baseUrl} disabled={busy} placeholder="https://hearth.home.arpa" onChange={event => { setBaseUrl(event.target.value); setPreview(null); }} /><p className="small-copy">Use HTTPS and a DNS name or VM IPv4 address, with an optional workspace port. Leave out /v1 and other paths. Administration and sign-in keep their separate ports.</p><button className="quiet-button" disabled={busy || !state}>Preview address</button></form>}
    {preview && <section className="head-preview" aria-label="Address change preview"><h3>{preview.base_url === state?.base_url ? 'Rebuild the certificate package' : 'Review the new addresses'}</h3><Links addresses={preview} /><p>DNS on the head resolves to {preview.addresses.join(', ')}.</p><p>The existing trust root, accounts and API keys are kept. The head briefly restarts and signs everyone out. Update agent and editor connection URLs after changing the address. If checks fail, hearth attempts to restore the previous address.</p><button className="primary-button" disabled={busy} onClick={() => void apply()}>{busy ? 'Submitting…' : 'Apply & rebuild certificates'}</button></section>}
    {!active && <p><button className="quiet-button" disabled={busy} onClick={() => { setAccepted(null); setPreview(null); void refresh().catch(reason => setError(reason.message)); }}>Refresh status</button></p>}
  </section>;
}
