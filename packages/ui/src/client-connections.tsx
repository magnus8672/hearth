import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon } from './index';

type Key = { id: string; name: string; capabilities: string[]; allow_tools: boolean; expires_at: string; revoked_at: string | null; last_used_at: string | null };
type Connections = { items: Key[]; capabilities: string[]; base_url: string; mcp_url: string };

export function ClientConnections({ identity }: { identity: Identity }) {
  const [state, setState] = useState<Connections | null>(null);
  const [name, setName] = useState('');
  const [capabilities, setCapabilities] = useState<string[]>(['chat.general', 'code.implement']);
  const [tools, setTools] = useState(true);
  const [days, setDays] = useState(90);
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function refresh() { setState(await api<Connections>('/api/v1/client-keys')); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  async function action(work: () => Promise<void>) {
    setBusy(true); setError('');
    try { await work(); await refresh(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <div className="connections-layout">
    <div className="info-banner"><Icon name="nodes" /><p>Connect your local agent or editor to hearth. Choose a capability as its model. Your agent keeps its local file tools; hearth selects the resident model that answers.</p></div>
    {error && <p role="alert" className="error-notice">{error}</p>}
    <section className="panel"><h2>Your connection details</h2><dl className="connection-details"><dt>API base URL</dt><dd><code>{state?.base_url || '…'}</code></dd><dt>Shared tools (MCP)</dt><dd><code>{state?.mcp_url || '…'}</code></dd><dt>Authorization</dt><dd>Bearer API key</dd><dt>Model</dt><dd><code>auto</code> or a capability such as <code>code.implement</code></dd></dl><p className="small-copy">Use the OpenAI Chat Completions format in your client. Add the MCP connection with the same key to make hearth’s shared tools available there. The model list includes ready text capabilities permitted by that key.</p></section>
    <div className="tool-columns"><form className="panel tool-form" onSubmit={event => { event.preventDefault(); void action(async () => { const result = await api<{ key: string }>('/api/v1/client-keys', mutation(identity, { name, capabilities, allow_tools: tools, expires_days: days })); setSecret(result.key); setName(''); }); }}>
      <h2>Add a client</h2><label htmlFor="client-name">Name</label><input id="client-name" value={name} onChange={event => setName(event.target.value)} maxLength={120} required placeholder="Continue on my desktop" />
      <fieldset><legend>Allowed capabilities</legend>{state?.capabilities.map(capability => <label className="check-label" key={capability}><input type="checkbox" checked={capabilities.includes(capability)} onChange={event => setCapabilities(event.target.checked ? [...capabilities, capability] : capabilities.filter(value => value !== capability))} />{capability}</label>)}</fieldset>
      <label className="check-label"><input type="checkbox" checked={tools} onChange={event => setTools(event.target.checked)} />Allow tool calls and approved shared tools</label>
      <label htmlFor="client-expiry">Expires in</label><select id="client-expiry" value={days} onChange={event => setDays(Number(event.target.value))}><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>1 year</option></select>
      <button className="primary-button" disabled={busy || !capabilities.length || !!secret}>Create API key</button>
      {secret && <div className="key-reveal" role="status"><strong>Copy this key now. It is shown only once.</strong><p className="small-copy">This key acts as you, within the capabilities selected above. Save it in your client’s secret settings.</p><textarea aria-label="New API key" readOnly value={secret} rows={4} /><div className="tool-actions"><button type="button" className="quiet-button" onClick={() => { void navigator.clipboard.writeText(secret).catch(() => setError('Select and copy the key manually.')); }}>Copy key</button><button type="button" className="quiet-button" onClick={() => setSecret('')}>I saved it</button></div></div>}
    </form><section className="panel"><h2>Your API keys</h2>{state?.items.length === 0 && <p>No clients connected yet.</p>}{state?.items.map(key => <article className="tool-entry" key={key.id}><h3>{key.name}</h3><p className="small-copy">{key.capabilities.join(' · ')}</p><p>{key.revoked_at ? 'Revoked' : new Date(key.expires_at) <= new Date() ? 'Expired' : `Expires ${new Date(key.expires_at).toLocaleDateString()}`}{key.allow_tools && ' · Tools allowed'}</p><p className="small-copy">{key.last_used_at ? `Last used ${new Date(key.last_used_at).toLocaleString()}` : 'Not used yet'}</p>{!key.revoked_at && <button className="quiet-button" disabled={busy} onClick={() => void action(async () => { await api(`/api/v1/client-keys/${key.id}`, mutation(identity, undefined, 'DELETE')); })}>Revoke {key.name}</button>}</article>)}</section></div>
  </div>;
}
