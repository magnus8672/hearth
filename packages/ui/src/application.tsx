import { useEffect, useState } from 'react';
import { Brand, Icon, Status, ThemeControl, useControlConnection } from './index';

type Audience = 'admin' | 'user';
type Identity = { id: string; display_name: string; roles: string[]; permissions: string[]; csrf_token: string; admin_origin: string; user_origin: string };
type Capability = { capability_id: string; display_name: string; description: string; icon: string; state: 'unassigned'; input_modalities: string[]; output_modalities: string[]; reason: string };
type Draft = { id: string; title: string; revision: number; content?: string };
type Workspace = { workspace: { name: string; locality: string }; drafts: Draft[] };
type Farm = { farm: { name: string }; members: { id: string; display_name: string; roles: string[]; state: string }[] };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store' });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || 'Hearth could not complete this request. Try again.');
  return value as T;
}

export function Application({ audience }: { audience: Audience }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    fetch('/api/v1/session', { credentials: 'same-origin', cache: 'no-store' }).then(async response => {
      if (response.ok) setIdentity(await response.json() as Identity);
      else if (response.status !== 401) setError((await response.json()).error?.message || 'Account connection unavailable.');
    }).catch(() => setError('Hearth is not reachable. Start the appliance and try again.')).finally(() => setLoaded(true));
  }, []);
  async function logout() {
    if (!identity) return;
    try {
      const response = await fetch('/api/v1/logout', { method: 'POST', headers: { 'X-Hearth-CSRF': identity.csrf_token } });
      if (!response.ok) throw new Error('Sign-out could not complete. Please try again.');
      window.location.assign('/');
    } catch (reason) { setError((reason as Error).message); }
  }
  return <div className="entry-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="app-header"><a className="home-link" href="/" aria-label="Hearth home"><Brand /></a><span className="app-kind">{audience === 'admin' ? 'Administration' : 'Your workspace'}</span><ThemeControl />
      {identity && <button className="quiet-button" onClick={() => void logout()}>Sign out</button>}
    </header>
    {error && <p className="global-notice error-notice" role="alert">{error}</p>}
    {!loaded ? <main id="main" className="loading-page"><Status state="warming">Opening your Hearth…</Status></main> : identity ? <Dashboard audience={audience} identity={identity} /> : <Welcome audience={audience} />}
    <footer className="app-footer"><span>Hearth <span className="footer-dot">·</span> Agentic Cloud at Home</span><span>Local test build <span className="footer-dot">·</span> Accounts & private drafts</span></footer>
  </div>;
}

function Welcome({ audience }: { audience: Audience }) {
  const { state, retry } = useControlConnection();
  const [ownerCreated, setOwnerCreated] = useState(false);
  useEffect(() => { api<{ owner_created: boolean }>('/api/v1/setup').then(value => setOwnerCreated(value.owner_created)).catch(() => {}); }, [state]);
  const admin = audience === 'admin';
  return <main id="main" className="entry-main">
    <div className="welcome-copy"><p className="eyebrow"><Icon name="hearth" /> AGENTIC CLOUD AT HOME</p><h1>{admin ? <>Make yourself<br />at home.</> : <>A place for<br />your ideas.</>}</h1><p className="lead">{admin ? 'Bring your machines together. Keep your intelligence close.' : 'A private place to gather your thoughts, ready for what comes next.'}</p><div className="principles"><div><Icon name="lock" />Private by default</div><div><Icon name="nodes" />Your machines, working together</div><div><Icon name="settings" />You stay in control</div></div></div>
    <section className="entry-card" aria-labelledby="entry-title"><div className="card-mark"><Icon name={admin ? 'hearth' : 'writing'} /></div><p className="eyebrow">WELCOME HOME</p><h2 id="entry-title">{ownerCreated ? 'Your Hearth is here.' : 'Let’s light the first spark.'}</h2><p>{ownerCreated ? 'Sign in with your Hearth account. Your password and authenticator stay with the local identity service.' : 'Open the local Hearth setup tool to create the Owner account and prepare browser trust.'}</p>
      <div className="connection-panel" aria-live="polite"><div className="connection-label">Control plane</div><Status state={state === 'ready' ? 'ready' : state === 'checking' ? 'warming' : 'offline'}>{state === 'ready' ? 'Database connected' : state === 'checking' ? 'Checking connection' : 'Connection unavailable'}</Status><p>{state === 'ready' ? 'Local service connected. No provider is assigned yet.' : 'Checking the local service and its database.'}</p></div>
      {ownerCreated && state === 'ready' ? <a className="primary-button button-link" href="/auth/login"><Icon name="lock" />Sign in to {admin ? 'Administration' : 'your workspace'}</a> : <button className="primary-button" disabled={state === 'checking'} onClick={retry}>Check connection</button>}
      {ownerCreated && !admin && <p className="small-copy">New here? Choose <strong>Register</strong> on the sign-in page. Keep an authenticator app nearby for account setup.</p>}
    </section>
    <section className="capability-intro" aria-label="What you can try"><div><Icon name="security" /><h3>Accounts that belong to you</h3><p>Separate administration and personal sessions, with an authenticator and recovery codes.</p></div><div><Icon name="writing" /><h3>Keep a thought for later</h3><p>Create and edit private drafts. Your work stays on this Hearth when you close the browser.</p></div><div><Icon name="cube" /><h3>See what comes next</h3><p>Explore the capability catalog. Generation becomes available after a provider is connected in a later build.</p></div></section>
  </main>;
}

function Dashboard({ audience, identity }: { audience: Audience; identity: Identity }) {
  const admin = audience === 'admin';
  const allowed = identity.permissions.includes('farm.inspect');
  const [tab, setTab] = useState(admin ? 'overview' : 'drafts');
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [farm, setFarm] = useState<Farm | null>(null);
  const [draftDirty, setDraftDirty] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (admin && !allowed) return;
    api<{ items: Capability[] }>('/api/v1/capabilities').then(value => setCapabilities(value.items)).catch(reason => setError(reason.message));
    if (admin) api<Farm>('/api/v1/farm').then(setFarm).catch(reason => setError(reason.message));
  }, [admin, allowed]);
  if (admin && !allowed) return <main id="main" className="loading-page"><div className="entry-card"><Icon name="lock" /><h1 className="page-title">Your workspace is ready.</h1><p>This account is a Member. Administration requires a farm role.</p><a className="primary-button button-link" href={identity.user_origin}>Open your workspace</a></div></main>;
  return <div className="dashboard-layout"><aside className="sidebar"><div className="farm-label"><span className="farm-avatar"><Icon name="hearth" /></span><div><strong>{farm?.farm.name || 'Your Hearth'}</strong><span>Local · private by default</span></div></div>
    <nav aria-label={admin ? 'Administration' : 'Workspace'}>{(admin ? [['overview', 'activity', 'Overview'], ['capabilities', 'cube', 'Capabilities'], ['people', 'users', 'People']] : [['drafts', 'writing', 'Private drafts'], ['capabilities', 'cube', 'Capabilities']]).map(([id, icon, label]) => <button key={id} className={`nav-item ${tab === id ? 'selected' : ''}`} aria-current={tab === id ? 'page' : undefined} onClick={() => { if (tab === id || !draftDirty || window.confirm('Leave this draft without saving your changes?')) setTab(id); }}><Icon name={icon} />{label}</button>)}</nav>
    <div className="sidebar-bottom"><div className="privacy-label"><Icon name="lock" /><span>Cloud budget<br /><strong>$0 · Local only</strong></span></div><a className="nav-item" href={admin ? identity.user_origin : identity.admin_origin}><Icon name={admin ? 'writing' : 'settings'} />{admin ? 'Your workspace' : 'Administration'}<span aria-hidden="true">↗</span></a></div>
  </aside><main id="main" className="dashboard-main"><div className="page-heading"><div><p className="eyebrow">{admin ? 'YOUR HEARTH' : 'JUST FOR YOU'}</p><h1 className="page-title">{tab === 'overview' ? `Welcome home, ${identity.display_name}.` : tab === 'capabilities' ? 'Room for possibility.' : tab === 'people' ? 'The people at home.' : 'Keep the spark.'}</h1><p className="muted">{tab === 'overview' ? 'A clear view of your farm, from the first connection onward.' : tab === 'capabilities' ? 'Choose what you want to do. Hearth will bring the right machines together.' : tab === 'people' ? 'Farm roles govern administration. Personal drafts remain private.' : 'A quiet space for thoughts, plans, and the beginning of something.'}</p></div><span className="identity-chip">{identity.roles.includes('Owner') ? 'Owner' : 'Member'}<span className="avatar">{identity.display_name.slice(0, 1).toUpperCase()}</span></span></div>
    {error && <p className="error-notice" role="alert">{error}</p>}
    {tab === 'overview' && <><div className="stats-grid"><div className="stat-card"><span>Control plane</span><strong className="stat-word">Connected</strong><Status state="ready">Database & identity verified</Status></div><div className="stat-card"><span>Capability catalog</span><strong>{capabilities.length}</strong><span>Awaiting provider assignment</span></div><div className="stat-card"><span>People</span><strong>{farm?.members.length ?? '…'}</strong><span>Private personal workspaces</span></div></div><section className="provider-card"><div className="card-mark"><Icon name="hearth" /></div><div><p className="eyebrow">THE NEXT SPARK</p><h2>Give your Hearth a voice.</h2><p>Accounts and private drafts are ready to try. Provider installation and inference are the next build milestone.</p></div><Status state="unassigned">No provider assigned</Status></section><div className="provider-options">{[['node', 'This machine', 'Run an approved model on the Hearth head.'], ['nodes', 'Another machine', 'Join a capable member and assign a model.'], ['cloud', 'OpenAI', 'Connect a provider with an explicit spending budget.']].map(([icon, title, description]) => <div className="panel" key={title}><Icon name={icon} /><h3>{title}</h3><p>{description}</p><span className="small-copy">Provider setup is not available in this build.</span></div>)}</div><p className="subtle-note"><Icon name="lock" />No models downloaded. No cloud calls. Your budget starts at zero.</p></>}
    {tab === 'capabilities' && <><div className="info-banner"><Icon name="activity" /><p><strong>No provider is assigned yet.</strong> These definitions come from your Hearth’s catalog. A capability becomes ready only after its deployment passes a real probe.</p></div><div className="catalog-grid">{capabilities.map(item => <article className="capability-card" key={item.capability_id}><div className="capability-top"><span className="card-mark"><Icon name={item.icon} /></span><Status state="unassigned">Unassigned</Status></div><h2>{item.display_name}</h2><p>{item.description}</p><div className="modality-line">{item.input_modalities.join(' + ')} <span aria-hidden="true">→</span> {item.output_modalities.join(' + ')}</div></article>)}</div></>}
    {tab === 'people' && <section className="panel people-panel"><h2>Farm accounts</h2>{farm?.members.map(member => <div className="person-row" key={member.id}><span className="avatar">{member.display_name.slice(0, 1)}</span><div><strong>{member.display_name}</strong><span>{member.roles.join(' · ')}</span></div><Status state={member.state === 'active' ? 'ready' : 'offline'}>{member.state}</Status></div>)}<p className="small-copy">Role changes and account suspension controls are still in development. This view never exposes another person’s content.</p></section>}
    {tab === 'drafts' && <Drafts identity={identity} onDirty={setDraftDirty} />}
  </main></div>;
}

function Drafts({ identity, onDirty }: { identity: Identity; onDirty: (dirty: boolean) => void }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<Draft | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const dirty = title !== (selected?.title || '') || content !== (selected?.content || '');
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  async function refresh() { setWorkspace(await api<Workspace>('/api/v1/workspace')); }
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);
  async function open(item: Draft | null) {
    if (dirty && !window.confirm('Leave this draft without saving your changes?')) return;
    setError(''); setMessage(''); setBusy(true);
    try {
      const draft = item ? await api<Draft>(`/api/v1/drafts/${item.id}`) : null;
      setSelected(draft); setTitle(draft?.title || ''); setContent(draft?.content || '');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function save() {
    setError(''); setMessage(''); setBusy(true);
    try {
      const draft = await api<Draft>(selected ? `/api/v1/drafts/${selected.id}` : '/api/v1/drafts', { method: selected ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', 'X-Hearth-CSRF': identity.csrf_token }, body: JSON.stringify({ title, content, ...(selected ? { revision: selected.revision } : {}) }) });
      setSelected(draft); setTitle(draft.title); setContent(draft.content || ''); await refresh(); setMessage('Saved to your private workspace.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  async function archive() {
    if (!selected || !window.confirm('Archive this draft? It will be removed from your active list.')) return;
    setBusy(true); setError('');
    try {
      await api(`/api/v1/drafts/${selected.id}`, { method: 'DELETE', headers: { 'X-Hearth-CSRF': identity.csrf_token } });
      setSelected(null); setTitle(''); setContent(''); await refresh(); setMessage('Draft archived.');
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <><div className="draft-layout"><section className="draft-list panel" aria-label="Saved drafts"><div className="section-heading"><h2>Your drafts</h2><button className="quiet-button" onClick={() => void open(null)} disabled={busy}>+ New</button></div><p className="small-copy">{workspace ? `${workspace.drafts.length} saved · Personal workspace` : 'Opening workspace…'}</p>{workspace?.drafts.length === 0 && <div className="empty-drafts"><Icon name="writing" /><h3>Every idea starts somewhere.</h3><p>Write your first thought. Save it here and come back whenever you’re ready.</p></div>}{workspace?.drafts.map(item => <button className={`draft-item ${selected?.id === item.id ? 'selected' : ''}`} disabled={busy} onClick={() => void open(item)} key={item.id}><Icon name="writing" /><span>{item.title}</span></button>)}</section>
      <section className="editor panel" aria-label="Draft editor"><div className="section-heading"><span className="privacy-label"><Icon name="lock" />Only you</span><span className="small-copy">{dirty ? 'Unsaved changes' : selected ? 'Saved locally' : 'New draft'}</span></div><label className="sr-only" htmlFor="draft-title">Draft title</label><input id="draft-title" className="draft-title" maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="Give your idea a name" disabled={busy} /><label className="sr-only" htmlFor="draft-content">Your draft</label><textarea id="draft-content" value={content} onChange={event => setContent(event.target.value)} placeholder="What’s on your mind?" maxLength={32000} disabled={busy} /><div className="editor-actions"><span className="small-copy">{content.length.toLocaleString()} / 32,000</span>{selected && <button className="quiet-button" onClick={() => void archive()} disabled={busy}>Archive</button>}<button className="primary-button" disabled={busy || !title.trim() || !content.trim() || !dirty} onClick={() => void save()}>{busy ? 'Saving…' : 'Save draft'}</button></div><div aria-live="polite">{message && <p className="success-message">{message}</p>}{error && <p className="error-notice" role="alert">{error}</p>}</div></section></div><p className="subtle-note"><Icon name="hearth" />Your drafts are saved, without being sent to a model. Assistant replies will arrive with provider support.</p></>;
}
