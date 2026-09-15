import { useEffect, useState } from 'react';
import { api, mutation, type Identity } from './api';
import { Icon, Status } from './index';
import { CapabilityRoute } from './capability-route';

type Target = { allow_insecure_http?: boolean; connection_id?: string; residency_policy?: string; tls_ca_sha256?: string; tls_ca_pem?: string; protocol?: string; id: string; name: string; base_url: string; model_id: string; revision: number; state: string; expired: boolean; features: string[]; reason: string | null; pool_name: string; resource_pool_id: string; execution_state: string; active_run_id: string | null; lease_until: string | null; probed_at?: string | null; verified_until: string | null };

type CapabilityFocus = { capability_id: string; display_name: string; reason: string };

function networkHttp(value: string) {
  try {
    const address = new URL(value);
    return address.protocol === 'http:' && !['localhost', '[::1]'].includes(address.hostname) && !address.hostname.startsWith('127.');
  } catch { return false; }
}

const httpWarning = 'HTTP is unencrypted. People with access to this network could read or change prompts, replies, images, audio and API keys sent to this server. Only approve a network and server you trust.';

export function Providers({ identity, capability, onClear }: { identity: Identity; capability?: CapabilityFocus; onClear?: () => void }) {
  const imageFocus = capability?.capability_id === 'image.generate';
  const supported = true;
  const executable = !capability || ['chat.general', 'reason.plan', 'code.explain', 'code.implement', 'write.compose', 'text.summarize', 'data.extract', 'image.generate', 'vision.describe', 'audio.speak', 'audio.transcribe'].includes(capability.capability_id);
  const speechFocus = capability?.capability_id === 'audio.speak';
  const transcriptionFocus = capability?.capability_id === 'audio.transcribe';
  const focusedProtocol = transcriptionFocus ? 'hearth.transcription.v1' : speechFocus ? 'hearth.speech.v1' : imageFocus ? 'hearth.image.v1' : 'openai.chat.v1';
  const [items, setItems] = useState<Target[]>([]);
  const [protocol, setProtocol] = useState(focusedProtocol);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [model, setModel] = useState('');
  const [pool, setPool] = useState('');
  const [key, setKey] = useState('');
  const [ca, setCA] = useState('');
  const [editing, setEditing] = useState<Target | null>(null);
  const [adding, setAdding] = useState<Target | null>(null);
  const [residency, setResidency] = useState('unknown');
  const [residentConfirmed, setResidentConfirmed] = useState(false);
  const [allowHttp, setAllowHttp] = useState(false);
  const [clearKey, setClearKey] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [local, setLocal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  function reset(nextProtocol = focusedProtocol) {
    setEditing(null); setAdding(null); setName(''); setUrl(''); setModel(''); setPool('');
    setProtocol(nextProtocol); setKey(''); setCA(''); setClearKey(false); setLocal(false);
    setResidency('unknown'); setResidentConfirmed(false);
    setAllowHttp(false);
  }
  function focusForm() { document.querySelector('.provider-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  function useServer(item: Target, edit: boolean) {
    setEditing(edit ? item : null); setAdding(edit ? null : item);
    setName(item.name); setUrl(item.base_url); setModel(edit ? item.model_id : '');
    setProtocol(item.protocol || 'openai.chat.v1'); setPool(item.pool_name); setCA(item.tls_ca_pem || '');
    setKey(''); setClearKey(false); setLocal(false); setResidency(item.residency_policy || 'unknown');
    setResidentConfirmed(false); setError(''); setNotice(''); focusForm();
    setAllowHttp(item.allow_insecure_http || false);
  }
  async function refresh() { setItems((await api<{ items: Target[] }>('/api/v1/providers')).items); setRefreshKey(value => value + 1); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  const checkingStartup = items.some(item => item.state === 'configured' && item.reason === 'Checking the saved provider connection after startup.');
  useEffect(() => {
    if (!checkingStartup) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await api<{ items: Target[] }>('/api/v1/providers');
        if (!stopped) { setItems(response.items); setRefreshKey(value => value + 1); }
      } catch { /* Keep the saved state visible; a later check can recover. */ }
      if (!stopped) timer = setTimeout(() => void poll(), 2000);
    }
    timer = setTimeout(() => void poll(), 2000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [checkingStartup]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (reason) { setError((reason as Error).message); }
    finally { try { await refresh(); } catch (reason) { setError((reason as Error).message); } setBusy(false); }
  }
  async function verify(item: { id: string; revision: number; protocol?: string; features?: string[] }, checkVision = capability?.capability_id === 'vision.describe' || !!item.features?.includes('vision'), checkTools = !!item.features?.includes('tools')) {
    const image = (item.protocol || protocol) === 'hearth.image.v1';
    const speech = (item.protocol || protocol) === 'hearth.speech.v1';
    const transcription = (item.protocol || protocol) === 'hearth.transcription.v1';
    checkVision = !speech && !transcription && checkVision;
    setNotice(transcription ? 'Transcribing and checking a known recording…' : speech ? 'Generating and validating a test voice recording…' : checkVision ? 'Checking a real image-reading challenge on this model…' : image ? 'Rendering and validating a test image on this provider…' : 'Checking the model list and a short streamed reply…');
    const result = await api<{ state: string; reason: string | null }>(`/api/v1/providers/${item.id}/probe`, mutation(identity, { revision: item.revision, ...(checkVision ? { vision: true } : {}), ...(checkTools ? { tools: true } : {}) }));
    setNotice(result.state === 'ready' ? (checkVision && !result.reason ? 'Vision, text and streaming verified. Assign this model to Vision to use image attachments.' : transcription ? 'Transcription verified against a known recording. Saved speech input assignments can use this model.' : speech ? 'Speech verified. Saved speech assignments can use this model.' : image ? 'Image generation verified. Saved image assignments can use this model.' : 'Text and streaming verified. Saved capability assignments can use this model.') : 'Verification did not pass.');
    if (result.reason) throw new Error(result.reason);
    await refresh();
  }
  async function httpApproval(item: Target, allowed: boolean) {
    const result = await api<{ id: string; revision: number }>(`/api/v1/providers/${item.id}/http-consent`, mutation(identity, { revision: item.revision, allow_insecure_http: allowed }));
    if (allowed) await verify({ ...result, protocol: item.protocol });
    else setNotice('HTTP approval revoked for this server and its models. Configure HTTPS or approve HTTP again before verification.');
  }
  const visible = capability && executable ? items.filter(item => (item.protocol || 'openai.chat.v1') === focusedProtocol) : items;
  return <><div className="section-heading"><div><h2>Your model servers</h2><p>Keep specialists ready on their own machines. Add as many servers of each type as your farm needs, up to 32 model targets.</p></div><button className="primary-button" disabled={busy} onClick={() => { reset(); setError(''); setNotice(''); focusForm(); }}>Add server</button></div><div aria-live="polite">{notice && <p className="success-message">{notice}</p>}{error && <p className="error-notice" role="alert">{error}</p>}</div><CapabilityRoute identity={identity} selected={capability?.capability_id} models={items} refreshKey={refreshKey} verify={(item, id) => verify(item, id === 'vision.describe' ? true : undefined)} />{capability && <section className="info-banner provider-focus" aria-label="Selected capability"><Icon name={imageFocus ? 'image' : 'settings'} /><div><h2>{capability.display_name}</h2><p>{executable ? 'Assign existing models above, or connect and verify another provider below.' : 'Save an intended assignment above. The required adapter and feature verification are still being built.'}</p>{!executable && <p className="small-copy">{capability.reason}</p>}</div><button className="quiet-button" onClick={onClear}>Show all providers</button></section>}{supported && <div className="provider-layout"><section className="panel provider-form"><div className="section-heading"><h2>{editing ? 'Editing this model' : adding ? 'Add model to this server' : 'Add a server'}</h2><Icon name="nodes" /></div><p>Connect a server and its first model, then assign capabilities above. Register other machines using Add server. Each model is verified separately.</p>
    <form onSubmit={event => { event.preventDefault(); void perform(async () => {
      if (residency === 'lmstudio_loaded' && !residentConfirmed) throw new Error('Confirm the model server has automatic loading disabled.');
      const item = await api<{ id: string; revision: number }>(editing ? `/api/v1/providers/${editing.id}` : '/api/v1/providers', mutation(identity, { name, base_url: url, model_id: model, api_key: key, tls_ca_pem: ca, resource_pool: pool, local_only: local, protocol, residency_policy: residency, allow_insecure_http: allowHttp, ...(editing ? { revision: editing.revision, clear_api_key: clearKey } : {}) }, editing ? 'PUT' : 'POST'));
      const savedProtocol = protocol; reset(savedProtocol); await verify({ ...item, protocol: savedProtocol });
    }); }}>
      <label>Provider type<select value={protocol} disabled={busy || !!adding || (!!capability && executable && !editing)} onChange={event => { setProtocol(event.target.value); setResidency('unknown'); setResidentConfirmed(false); }}><option value="openai.chat.v1">OpenAI-compatible chat</option><option value="hearth.image.v1">hearth image provider</option><option value="hearth.speech.v1">hearth speech provider</option><option value="hearth.transcription.v1">hearth transcription provider</option></select></label>
      <label>Connection name<input value={name} placeholder="Office laptop" onChange={event => setName(event.target.value)} maxLength={120} required disabled={busy || !!adding} /></label>
      <label>Server address<input type="url" value={url} placeholder="http://192.168.1.40:1234" onChange={event => { setUrl(event.target.value); setAllowHttp(false); }} maxLength={2048} required disabled={busy || !!adding} /></label>
      {networkHttp(url) && <div className="http-risk"><p className="small-copy">{httpWarning}</p><label className="checkbox-label"><input type="checkbox" checked={allowHttp} onChange={event => setAllowHttp(event.target.checked)} required disabled={busy || !!adding} />I’m the administrator and I understand the risks. Allow HTTP for this server.</label><p className="small-copy">Approval applies to all models at this saved address. You can revoke it on the server card.</p></div>}
      <label>Model identifier<input value={model} placeholder={protocol === 'hearth.image.v1' ? 'Your image pipeline identifier' : 'Exact model or loaded instance identifier'} onChange={event => setModel(event.target.value)} maxLength={200} required disabled={busy} /></label>
      <label>API key <span className="muted">{adding ? 'using this server’s saved key' : editing ? 'leave blank to keep the saved key' : protocol !== 'openai.chat.v1' ? 'controller key' : 'optional'}</span><input type="password" autoComplete="off" value={key} onChange={event => setKey(event.target.value)} maxLength={2048} disabled={busy || !!adding} /></label>
      {editing && <label className="checkbox-label"><input type="checkbox" checked={clearKey} disabled={busy} onChange={event => setClearKey(event.target.checked)} />Remove the saved API key</label>}
      <details><summary>Private network certificate</summary><p className="small-copy">For the hearth connector, copy its public provider-ca.pem here and compare its SHA-256 fingerprint on that machine. Trust applies only to this connection. Never paste a private key.</p><label>Provider CA certificate<textarea value={ca} disabled={busy || !!adding} maxLength={16384} onChange={event => setCA(event.target.value)} placeholder="-----BEGIN CERTIFICATE-----" /></label></details>
      <label>Resource group<input value={pool} placeholder="Office GPU" list="provider-resource-groups" onChange={event => setPool(event.target.value)} maxLength={120} required disabled={busy} /></label><datalist id="provider-resource-groups">{[...new Set(items.map(item => item.pool_name))].map(value => <option key={value} value={value} />)}</datalist><p className="small-copy">Name the GPU this model uses. Separate machines need separate groups so they can run concurrently. Use an existing group only when models share hardware. Each group admits one generation at a time.</p>
      {pool && items.some(item => item.pool_name === pool && item.id !== editing?.id) && <p className="info-banner">This group already exists. Its models will share one queue with this model.</p>}
      {protocol === 'openai.chat.v1' && <><label>Loaded-model check<select value={residency} disabled={busy} onChange={event => { setResidency(event.target.value); setResidentConfirmed(false); }}><option value="unknown">Compatible service · residency unknown</option><option value="lmstudio_loaded">LM Studio · require a loaded instance</option></select></label>{residency === 'lmstudio_loaded' && <><p className="small-copy">hearth checks LM Studio before each text request and verification. Use the loaded instance identifier. Disable Just-in-Time loading and automatic unloading on that server; keep the chosen model loaded. The check observes memory state but cannot reserve it against other apps.</p><label className="checkbox-label"><input type="checkbox" checked={residentConfirmed} disabled={busy} required onChange={event => setResidentConfirmed(event.target.checked)} />I have disabled automatic model loading on this server.</label></>}</>}
      <label className="checkbox-label"><input type="checkbox" checked={local} onChange={event => setLocal(event.target.checked)} required disabled={busy} />I trust this local server and its operator to process workspace conversations without forwarding them to a cloud service.</label>
      <button className="primary-button" disabled={busy || !local || (networkHttp(url) && !allowHttp)}>{busy ? 'Working…' : editing ? 'Save & verify model' : protocol === 'hearth.transcription.v1' ? 'Connect & verify transcription' : protocol === 'hearth.speech.v1' ? 'Connect & verify speech' : protocol === 'hearth.image.v1' ? 'Connect & verify images' : 'Connect & verify chat'}</button>
      {(editing || adding) && <button className="quiet-button" type="button" disabled={busy} onClick={() => reset()}>Cancel {editing ? 'editing' : 'adding model'}</button>}
    </form><p className="small-copy">Connect directly using HTTPS or explicitly approved LAN HTTP. A hearth connector is optional. Cloud spending stays disabled. Verification sends a test prompt or recording and checks the returned text, image or audio.</p>
  </section><section aria-label="Configured models" className="provider-targets"><div className="section-heading"><h2>{capability ? `${capability.display_name} models` : 'Configured servers and models'}</h2><button className="quiet-button" disabled={busy} onClick={() => void perform(refresh)}>Refresh</button></div>
    {visible.length === 0 && <div className="panel empty-drafts"><Icon name="hearth" /><h3>The first connection starts here.</h3><p>Connect a model, verify its supported features, then assign it to a capability above.</p></div>}
    {visible.map(item => <article className="panel target-card" key={item.id}><div className="section-heading"><h3>{item.name}</h3><Status state={item.state === 'ready' ? 'ready' : item.state === 'configured' ? 'unassigned' : 'offline'}>{item.state}</Status></div><strong className="model-name">{item.model_id}</strong><p className="small-copy model-address">{item.base_url}</p><dl><dt>Connection security</dt><dd>{item.allow_insecure_http ? 'HTTP · admin accepted risks' : networkHttp(item.base_url) ? 'HTTP · approval required' : item.base_url.startsWith('https:') ? 'HTTPS · certificate checked on connection' : 'HTTP · loopback'}</dd><dt>Provider type</dt><dd>{item.protocol === 'hearth.transcription.v1' ? 'hearth transcription provider' : item.protocol === 'hearth.speech.v1' ? 'hearth speech provider' : item.protocol === 'hearth.image.v1' ? 'hearth image provider' : 'OpenAI-compatible chat'}</dd><dt>Loaded-model policy</dt><dd>{item.residency_policy === 'lmstudio_loaded' ? 'Check LM Studio before every text request; automatic loading disabled by operator' : 'Residency unknown'}</dd><dt>Managed by</dt><dd>{item.protocol === 'hearth.transcription.v1' ? 'Transcription provider' : item.protocol === 'hearth.speech.v1' ? 'Speech provider' : item.protocol === 'hearth.image.v1' ? 'Image provider' : 'Your existing app'}</dd>{item.tls_ca_sha256 && <><dt>Provider CA SHA-256</dt><dd className="model-address">{item.tls_ca_sha256}</dd></>}<dt>Resource group</dt><dd>{item.pool_name} · {item.execution_state}</dd><dt>Verified features</dt><dd>{item.features.join(', ') || 'None yet'}</dd><dt>Shared tool calling</dt><dd>{item.features.includes('tools') ? 'Verified' : 'Needs tool verification'}</dd><dt>Administration agent</dt><dd>In development</dd></dl>{item.state === 'ready' && <p className="small-copy">Verified{item.probed_at ? ` ${new Date(item.probed_at).toLocaleString()}` : ''}. Stays verified until a provider error or connection change. Connections are checked automatically when hearth starts.</p>}{item.reason && <p className="error-notice">{item.reason}</p>}{networkHttp(item.base_url) && !item.allow_insecure_http && <div className="http-risk"><p>{httpWarning}</p><p className="small-copy">This approval applies to all models at {item.base_url}.</p><button className="primary-button" disabled={busy || !!item.active_run_id} onClick={() => void perform(() => httpApproval(item, true))}>I understand the risks. Use HTTP</button></div>}<div className="target-actions">{(!item.protocol || item.protocol === 'openai.chat.v1') && <button className="quiet-button" disabled={busy || !!item.active_run_id} onClick={() => void perform(() => verify(item, item.features.includes('vision'), true))}>Verify tool calling</button>}{item.allow_insecure_http && <button className="quiet-button" disabled={busy || !!item.active_run_id} onClick={() => void perform(() => httpApproval(item, false))}>Revoke HTTP approval</button>}<button className="quiet-button" disabled={busy || !!item.active_run_id} onClick={() => { useServer(item, true); }}>Edit connection</button><button className="quiet-button" disabled={busy} onClick={() => useServer(item, false)}>Add model to this server</button><button className="primary-button" disabled={busy || !!item.active_run_id} onClick={() => void perform(() => verify(item))}>{item.protocol === 'hearth.transcription.v1' ? 'Verify transcription' : item.protocol === 'hearth.speech.v1' ? 'Verify speech' : item.protocol === 'hearth.image.v1' ? 'Verify images' : item.features.includes('vision') ? 'Verify chat & vision' : 'Verify chat'}</button>{(item.protocol || 'openai.chat.v1') === 'openai.chat.v1' && !item.features.includes('vision') && <button className="quiet-button" disabled={busy || !!item.active_run_id} onClick={() => void perform(() => verify(item, true))}>Verify vision</button>}<button className="quiet-button" disabled={busy || item.state === 'disabled'} onClick={() => void perform(async () => { await api(`/api/v1/providers/${item.id}/disable`, mutation(identity, { revision: item.revision })); })}>Disable</button>
      {item.active_run_id && (item.execution_state === 'unknown' || (item.lease_until && Date.parse(item.lease_until) < Date.now())) && <button className="quiet-button" disabled={busy} onClick={() => {
        if (window.confirm('Check the model server first. Has its previous generation finished? Confirming releases this resource group for another request.')) void perform(async () => { await api(`/api/v1/provider-pools/${item.resource_pool_id}/clear`, mutation(identity, { expected_run_id: item.active_run_id, confirm_backend_idle: true })); });
      }}>Confirm backend is idle</button>}
    </div></article>)}
  </section></div>}</>;
}
